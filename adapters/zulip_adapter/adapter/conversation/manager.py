import asyncio

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.conversation.message_builder import MessageBuilder
from adapters.zulip_adapter.adapter.conversation.reaction_handler import ReactionHandler
from adapters.zulip_adapter.adapter.conversation.thread_handler import ThreadHandler
from adapters.zulip_adapter.adapter.conversation.user_builder import UserBuilder

from core.conversation.base_data_classes import ConversationDelta, ThreadInfo, UserInfo
from core.conversation.base_manager import BaseManager
from core.cache.message_cache import CachedMessage
from core.utils.config import Config

class ZulipEventType(str, Enum):
    """Types of events that can be processed"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    REACTION = "reaction"

class Manager(BaseManager):
    """Tracks and manages information about Zulip conversations"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, start_maintenance)
        self.message_builder = MessageBuilder()
        self.thread_handler = ThreadHandler(self.message_cache)

    async def add_to_conversation(self, event: Any) -> Dict[str, Any]:
        """Creates a new conversation or adds a message to an existing one

        Args:
            event: Event object that should contain the following keys:
                - message: Zulip message object
                - attachments: Optional attachment information

        Returns:
            Dictionary with delta information
        """
        message = event.get("message", None)
        attachments = event.get("attachments", [])

        async with self._lock:
            if not message:
                return {}

            conversation_info = self._get_or_create_conversation_info(message)
            if not conversation_info:
                return {}

            delta = self._create_conversation_delta(conversation_info)
            attachments = await self._update_attachment(conversation_info, attachments)
            cached_msg = await self._create_message(
                message,
                conversation_info,
                UserBuilder.add_user_info_to_conversation(
                    self.config, message, conversation_info
                ),
                await self.thread_handler.add_thread_info(message, conversation_info)
            )

            delta.message_id = cached_msg.message_id
            await self._update_delta_list(
                conversation_id=conversation_info.conversation_id,
                delta=delta,
                list_to_update="added_messages",
                cached_msg=cached_msg,
                attachments=attachments
            )

            return delta.to_dict()

    async def update_conversation(self, event: Any) -> Dict[str, Any]:
        """Update conversation information based on a Zulip event

        Args:
            event: Event object that should contain the following keys:
                - event_type: Type of event
                - message: Zulip message object
                - attachments: Optional attachment information

        Returns:
            Dictionary with delta information
        """
        event_type = event.get("event_type", None)
        message = event.get("message", None)
        attachments = event.get("attachments", [])

        async with self._lock:
            if not message:
                return {}
            
            conversation_id = self._get_conversation_id_by_message(message)
            if not conversation_id or conversation_id not in self.conversations:
                return {}

            conversation_info = self.conversations[conversation_id]
            delta = self._create_conversation_delta(conversation_info)

            if event_type == ZulipEventType.UPDATE_MESSAGE:
                attachments = await self._update_attachment(conversation_info, attachments)
                threading_changed, thread_info = await self.thread_handler.update_thread_info(
                    message, conversation_info
                )
                cached_msg = await self._update_message(
                    message, conversation_info, threading_changed, thread_info
                )

                await self._update_delta_list(
                    conversation_id=conversation_info.conversation_id,
                    delta=delta,
                    list_to_update="updated_messages",
                    cached_msg=cached_msg,
                    attachments=attachments
                )
            elif event_type == ZulipEventType.REACTION:
                await self._update_reaction(message, conversation_info, delta)

            return delta.to_dict()

    async def delete_from_conversation(self,
                                       incoming_event: Any = None,
                                       outgoing_event: Any = None) -> Dict[str, Any]:
        """Handle deletion of messages from a conversation
        
        Args:
            incoming_event: Incoming event object
            outgoing_event: Outgoing event object
            
        Returns:
            Dictionary with delta information for deleted messages
        """

        message_id = (incoming_event or outgoing_event).get("message_id", None)
        conversation_id = (incoming_event or outgoing_event).get("conversation_id", None)

        if not message_id or not conversation_id or conversation_id not in self.conversations:
            return {}
        
        delta = self._create_conversation_delta(self.conversations[conversation_id])

        async with self._lock:
            if self.conversations[conversation_id]:
                cached_msg = await self.message_cache.get_message_by_id(
                    conversation_id=conversation_id,
                    message_id=message_id
                )
                if cached_msg:
                    self.thread_handler.remove_thread_info(
                        self.conversations[conversation_id], cached_msg.thread_id
                    )
                    await self.message_cache.delete_message(conversation_id, message_id)
                    self.conversations[conversation_id].message_count -= 1
                    delta.deleted_message_ids.append(str(message_id))

        return delta.to_dict()

    async def migrate_between_conversations(self, event: Any) -> Dict[str, Any]:
        """Handle a supergroup that was migrated from a regular group

        Args:
            event: Zulip event object

        Returns:
            Dictionary with delta information
        """
        event_copy = event.copy()
        event_copy.update({"type": "stream"})

        new_conversation = self._get_or_create_conversation_info(event_copy)
        if not new_conversation:
            return {}
   
        async with self._lock:
            delta = self._create_conversation_delta(new_conversation)

            old_conversation_id = f"{event.get('stream_id', '')}/{event.get('orig_subject', '')}"
            new_conversation_id = new_conversation.conversation_id

            if old_conversation_id in self.conversations:
                for message_id in event.get("message_ids", []):
                    delta.deleted_message_ids.append(str(message_id))

                    await self.message_cache.migrate_message(
                        old_conversation_id, str(message_id), new_conversation_id
                    )

                    self.conversations[new_conversation_id].messages.add(str(message_id))
                    self.conversations[new_conversation_id].message_count += 1
                    self.conversations[old_conversation_id].messages.discard(str(message_id))
                    self.conversations[old_conversation_id].message_count -= 1

                    if not delta.fetch_history:
                        await self._update_delta_list(
                            conversation_id=new_conversation_id,
                            delta=delta,
                            list_to_update="added_messages",
                            message_id=str(message_id)
                        )

            return delta.to_dict()

    def _get_conversation_id(self, message: Dict[str, Any]) -> Optional[str]:
        """Get the conversation ID from a Telethon message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as string, or None if not found
        """
        if message.get("type", None) == "private":
            return self._get_private_conversation_id(message)
        if message.get("type", None) == "stream" and message.get("stream_id", None):
            return self._get_stream_conversation_id(message)

        return None

    def _get_private_conversation_id(self, message: Dict[str, Any]) -> str:
        """Create a conversation ID for a private message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as a comma-separated list of user IDs
        """
        user_ids = sorted(
            [str(p.get("id")) for p in message.get("display_recipient", []) if "id" in p]
        )
        return "_".join(user_ids)

    def _get_stream_conversation_id(self, message: Dict[str, Any]) -> str:
        """Create a conversation ID for a stream message

        Args:
            message: Zulip message object   

        Returns:
            Conversation ID as a slash-separated combination of stream id and topic
        """
        stream_id = str(message.get("stream_id", ""))
        topic = message.get("subject", "")
        return f"{stream_id}/{topic}" if stream_id and topic else ""

    def _get_conversation_id_by_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Get the conversation ID from a Zulip message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as string, or None if not found
        """
        message_id = str(message.get("message_id", ""))

        if message_id:
            for conversation_id, conversation_info in self.conversations.items():
                if message_id in conversation_info.messages:
                    return conversation_id

        return None

    def _get_conversation_type(self, message: Any) -> Optional[str]:
        """Get the conversation type from a message

        Args:
            message: Zulip message object

        Returns:
            Conversation type as string, or None if not found
        """
        return message.get("type", None)

    def _get_conversation_name(self, message: Any) -> Optional[str]:
        """Get the conversation name from a message

        Args:
            message: Zulip message object

        Returns:
            Conversation name as string, or None if not found
        """
        if message.get("type", None) == "stream":
            return message.get("display_recipient", None)
        return None

    def _create_conversation_info(self,
                                  conversation_id: str,
                                  conversation_type: str,
                                  conversation_name: Optional[str] = None) -> ConversationInfo:
        """Create a conversation info object

        Args:
            conversation_id: Conversation ID
            conversation_type: Conversation type
            conversation_name: Conversation name

        Returns:
            Conversation info object
        """
        return ConversationInfo(
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            conversation_name=conversation_name,
            just_started=True
        )

    async def _create_message(self,
                              message: Dict[str, Any],
                              conversation_info: ConversationInfo,
                              user_info: UserInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a message in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            user_info: User info object
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        message_data = self.message_builder.reset() \
            .with_basic_info(message, conversation_info.conversation_id) \
            .with_sender_info(user_info) \
            .with_content(message) \
            .with_thread_info(thread_info) \
            .build()
        cached_msg = await self.message_cache.add_message(message_data)

        conversation_info.messages.add(cached_msg.message_id)
        conversation_info.message_count += 1

        return cached_msg

    async def _update_message(self,
                              message: Dict[str, Any],
                              conversation_info: ConversationInfo,
                              threading_changed: bool,
                              thread_info: Optional[ThreadInfo]) -> CachedMessage:
        """Update a message in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            threading_changed: Whether threading has changed
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            cached_msg.timestamp = message.get("edit_timestamp", int(datetime.now().timestamp() * 1e3))
            cached_msg.text = message.get("content", "")

            if threading_changed:
                if not thread_info:
                    self.thread_handler.remove_thread_info(conversation_info, cached_msg.thread_id)
                cached_msg.reply_to_message_id = thread_info.thread_id if thread_info else None
                cached_msg.thread_id = thread_info.thread_id if thread_info else None

        return cached_msg

    async def _update_reaction(self,
                               message: Dict[str, Any],
                               conversation_info: ConversationInfo,
                               delta: ConversationDelta) -> None:
        """Update a reaction in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            delta: Delta object to update

        Returns:
            List of reactions
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            delta.message_id = cached_msg.message_id
            delta = ReactionHandler.update_message_reactions(message, cached_msg, delta)

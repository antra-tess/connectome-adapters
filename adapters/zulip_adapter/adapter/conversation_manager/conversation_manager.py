import asyncio
import logging
import os

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from adapters.zulip_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, ThreadInfo, UpdateType, UserInfo
)
from adapters.zulip_adapter.adapter.conversation_manager.message_builder import MessageBuilder
from adapters.zulip_adapter.adapter.conversation_manager.reaction_handler import ReactionHandler
from adapters.zulip_adapter.adapter.conversation_manager.thread_handler import ThreadHandler
from adapters.zulip_adapter.adapter.conversation_manager.user_builder import UserBuilder

from core.cache.message_cache import MessageCache, CachedMessage
from core.cache.attachment_cache import AttachmentCache
from core.utils.config import Config

class EventType(str, Enum):
    """Types of events that can be processed"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    REACTION = "reaction"

class ConversationManager:
    """Tracks and manages information about Zulip conversations"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.conversations: Dict[str, ConversationInfo] = {}
        self._lock = asyncio.Lock()
        self.message_cache = MessageCache(config, start_maintenance)
        self.attachment_cache = AttachmentCache(config, start_maintenance)
        self.message_builder = MessageBuilder()
        self.user_builder = UserBuilder()

    async def add_to_conversation(self,
                                  message: Dict[str, Any],
                                  attachment_infos: Optional[List[Dict[str, Any]]] = []) -> Dict[str, Any]:
        """Creates a new conversation or adds a message to an existing one

        Args:
            message: Zulip message object
            attachment_infos: Optional attachment information

        Returns:
            Dictionary with delta information
        """
        async with self._lock:
            if not message:
                return {}

            conversation_info = self._get_or_create_conversation(message)
            if not conversation_info:
                return {}

            delta = self._create_conversation_delta(conversation_info)
            thread_info = await ThreadHandler.add_thread_info_to_conversation(
                self.message_cache, message, conversation_info
            )
            cached_msg = await self._create_message(
                message,
                conversation_info,
                self.user_builder.add_user_info_to_conversation(
                    message, conversation_info, self._from_adapter(message)
                ),
                thread_info
            )
            attachment_infos = await self._update_attachment_info(
                conversation_info, attachment_infos
            )

            await self._update_delta_list(
                conversation_id=conversation_info.conversation_id,
                delta=delta,
                list_to_update="added_messages",
                cached_msg=cached_msg,
                attachment_infos=attachment_infos
            )

            return delta.to_dict()

    async def update_conversation(self,
                                  event_type: str,
                                  message: Dict[str, Any],
                                  attachment_infos: Optional[List[Dict[str, Any]]] = []) -> Dict[str, Any]:
        """Update conversation information based on a Zulip event

        Args:
            event_type: Type of event
            message: Zulip message object
            attachment_infos: Optional attachment information

        Returns:
            Dictionary with delta information
        """
        async with self._lock:
            if not message:
                return {}
            
            conversation_id = self._get_conversation_id_by_message(message)
            if not conversation_id or conversation_id not in self.conversations:
                return {}

            conversation_info = self.conversations[conversation_id]
            delta = self._create_conversation_delta(conversation_info)

            if event_type == EventType.UPDATE_MESSAGE:
                attachment_infos=await self._update_attachment_info(
                    conversation_info, attachment_infos
                )
                threading_changed, thread_info = await ThreadHandler.update_thread_info(
                    self.message_cache, message, conversation_info
                )
                cached_msg = await self._update_message(
                    message, conversation_info, threading_changed, thread_info
                )

                await self._update_delta_list(
                    conversation_id=conversation_info.conversation_id,
                    delta=delta,
                    list_to_update="updated_messages",
                    cached_msg=cached_msg,
                    attachment_infos=attachment_infos
                )
            elif event_type == EventType.REACTION:
                await self._update_reaction(message, conversation_info, delta)

            return delta.to_dict()

    async def delete_from_conversation(self, message_id: str, conversation_id: str) -> None:
        """Handle deletion of messages from a conversation

        Args:
            message_id: Message ID to delete
            conversation_id: Conversation ID
        """
        if not message_id or not conversation_id or conversation_id not in self.conversations:
            return

        async with self._lock:
            if self.conversations[conversation_id]:
                cached_msg = await self.message_cache.get_message_by_id(
                    conversation_id=conversation_id,
                    message_id=message_id
                )
                if cached_msg:
                    ThreadHandler.remove_thread_info(self.conversations[conversation_id], cached_msg)
                    await self.message_cache.delete_message(conversation_id, message_id)
                    self.conversations[conversation_id].message_count -= 1

    async def migrate_between_conversations(self, message: Any) -> Dict[str, Any]:
        """Handle a supergroup that was migrated from a regular group

        Args:
            message: Zulip message object

        Returns:
            Dictionary with delta information
        """
        message_copy = message.copy()
        message_copy.update({"type": "stream"})

        new_conversation = self._get_or_create_conversation(message_copy)
        if not new_conversation:
            return {}
   
        async with self._lock:
            delta = self._create_conversation_delta(new_conversation)

            old_conversation_id = f"{message.get('stream_id', '')}/{message.get('orig_subject', '')}"
            new_conversation_id = new_conversation.conversation_id

            if old_conversation_id in self.conversations:
                for message_id in message.get("message_ids", []):
                    delta.deleted_message_ids.append(str(message_id))

                    await self.message_cache.migrate_message(
                        old_conversation_id, str(message_id), new_conversation_id
                    )

                    self.conversations[new_conversation_id].messages.add(str(message_id))
                    self.conversations[new_conversation_id].message_count += 1
                    self.conversations[old_conversation_id].messages.discard(str(message_id))
                    self.conversations[old_conversation_id].message_count -= 1

                    if UpdateType.CONVERSATION_STARTED not in delta.updates:
                        await self._update_delta_list(
                            conversation_id=new_conversation_id,
                            delta=delta,
                            list_to_update="added_messages",
                            message_id=str(message_id)
                        )

            return delta.to_dict()

    def _from_adapter(self, message: Dict[str, Any]) -> bool:
        """Check if the message is from the adapter

        Args:
            message: Zulip message object

        Returns:
            True if the message is from the adapter, False otherwise    
        """
        return (
            self.config.get_setting("adapter", "adapter_id") == str(message.get("sender_id", "")) and
            self.config.get_setting("adapter", "adapter_email") == str(message.get("sender_email", ""))
        )

    def _create_conversation_delta(self, conversation_info: ConversationInfo) -> ConversationDelta:
        """Create a conversation delta

        Args:
            conversation_info: Conversation info object

        Returns:
            Conversation delta object
        """
        delta = ConversationDelta(conversation_id=conversation_info.conversation_id)

        if conversation_info.just_started:
            delta.fetch_history = True
            conversation_info.just_started = False

        return delta

    def _get_or_create_conversation(self, message: Dict[str, Any]) -> Optional[ConversationInfo]:
        """Get existing conversation or create a new one from Telethon message

        Args:
            message: Zulip message object

        Returns:
            ConversationInfo object or None if conversation can't be determined
        """
        conversation_id = self._get_conversation_id(message)

        if not conversation_id:
            return None
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        self.conversations[conversation_id] = ConversationInfo(
            conversation_id=conversation_id,
            conversation_type=message.get("type", None),
            just_started=True
        )

        return self.conversations[conversation_id]

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

    async def _update_attachment_info(self,
                                      conversation_info: ConversationInfo,
                                      attachment_infos: List[Dict[str, Any]] = []) -> List[Dict[str, Any]]:
        """Update attachment info in conversation info

        Args:
            conversation_info: Conversation info object
            attachment_infos: List of attachment info dictionaries

        Returns:
            List of dictionaries with attachment information
        """
        result = []

        for attachment_info in attachment_infos:
            cached_attachment = await self.attachment_cache.add_attachment(
                conversation_info.conversation_id, attachment_info
            )
            conversation_info.attachments.add(cached_attachment.attachment_id)

            result.append({
                "attachment_id": cached_attachment.attachment_id,
                "attachment_type": cached_attachment.attachment_type,
                "file_extension": cached_attachment.file_extension,
                "file_path": os.path.join(
                self.config.get_setting("attachments", "storage_dir"),
                    cached_attachment.file_path
                ),
                "size": cached_attachment.size
            })

        return result

    async def _create_message(self,
                              message: Dict[str, Any],
                              conversation_info: ConversationInfo,
                              user_info: UserInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

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
                    ThreadHandler.remove_thread_info(conversation_info, cached_msg)
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

    async def _update_delta_list(self,
                                 conversation_id: str,
                                 delta: ConversationDelta,
                                 list_to_update: str,
                                 attachment_infos: Optional[List[Dict[str, Any]]] = [],
                                 message_id: Optional[str] = None,
                                 cached_msg: Optional[CachedMessage] = None) -> None:
        """Add a migrated message to the delta

        Args:
            conversation_id: Conversation ID
            delta: Delta object to update
            list_to_update: List to update
            attachment_infos: List of attachment info dictionaries
            message_id: Message ID
            cached_msg: Cached message object
        """
        if cached_msg and cached_msg.is_from_bot:
            return
        
        if not cached_msg:
            cached_msg = await self.message_cache.get_message_by_id(conversation_id, message_id)

        if cached_msg:
            getattr(delta, list_to_update).append({
                "message_id": cached_msg.message_id,
                "conversation_id": conversation_id,
                "sender":  {
                    "user_id": cached_msg.sender_id,
                    "display_name": cached_msg.sender_name
                },
                "text": cached_msg.text,
                "timestamp": cached_msg.timestamp,
                "thread_id": cached_msg.reply_to_message_id,
                "attachments": attachment_infos
            })

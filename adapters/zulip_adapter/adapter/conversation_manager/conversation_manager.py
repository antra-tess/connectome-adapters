import asyncio

from enum import Enum
from typing import Dict, Optional, Any

from adapters.zulip_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UpdateType
)
from adapters.zulip_adapter.adapter.conversation_manager.message_builder import MessageBuilder
from adapters.zulip_adapter.adapter.conversation_manager.reaction_handler import ReactionHandler
from adapters.zulip_adapter.adapter.conversation_manager.user_builder import UserBuilder

from core.cache.message_cache import MessageCache
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
                                  attachment_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Creates a new conversation or adds a message to an existing one

        Args:
            message: Zulip message object
            attachment_info: Optional attachment information

        Returns:
            Dictionary with delta information
        """
        async with self._lock:
            if not message:
                return {}

            conversation_info = self._get_or_create_conversation(message)
            if not conversation_info:
                return {}

            delta = ConversationDelta(
                conversation_id=conversation_info.conversation_id,
                conversation_type=conversation_info.conversation_type
            )

            if conversation_info.just_started:
                delta.updates.append(UpdateType.CONVERSATION_STARTED)
                conversation_info.just_started = False

            self.user_builder.add_user_info_to_conversation(message, conversation_info, delta)            
            await self._create_message(message, conversation_info, delta)

            return delta.to_dict()
        
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
            return str(message["stream_id"])

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

    async def _create_message(self,
                              message: Dict[str, Any],
                              conversation_info: ConversationInfo,
                              delta: ConversationDelta) -> None:
        """Create a new message in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        delta.message_id = str(message["id"]) if message.get("id", None) else None
        delta.timestamp = message.get("timestamp", None)

        message_data = self.message_builder.reset() \
            .with_basic_info(message, conversation_info.conversation_id) \
            .with_sender_info(delta.sender) \
            .with_thread_info(delta.thread_id, message) \
            .with_content(message) \
            .build()

        cached_msg = await self.message_cache.add_message(message_data)
        conversation_info.messages.add(cached_msg.message_id)
        conversation_info.message_count += 1

        delta.text = cached_msg.text
        delta.updates.append(UpdateType.MESSAGE_RECEIVED)

    async def update_conversation(self,
                                  event_type: str,
                                  message: Dict[str, Any]) -> Dict[str, Any]:
        """Update conversation information based on a Zulip event

        Args:
            event_type: Type of event
            message: Zulip message object

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
            delta = ConversationDelta(
                conversation_id=conversation_info.conversation_id,
                conversation_type=conversation_info.conversation_type
            )

            if event_type == EventType.UPDATE_MESSAGE:
                await self._update_message(message, conversation_info, delta)
            elif event_type == EventType.REACTION:
                await self._update_reaction(message, conversation_info, delta)

            return delta.to_dict()

    async def _update_message(self,
                              message: Dict[str, Any],
                              conversation_info: ConversationInfo,
                              delta: ConversationDelta) -> None:
        """Update a message in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            cached_msg.timestamp = message.get("edit_timestamp", None)
            cached_msg.text = message.get("content", "")

            delta.message_id = str(message["message_id"]) if message.get("message_id", None) else None
            delta.timestamp = cached_msg.timestamp
            delta.text = cached_msg.text

            delta.updates.append(UpdateType.MESSAGE_EDITED)

    async def _update_reaction(self,
                               message: Dict[str, Any],
                               conversation_info: ConversationInfo,
                               delta: ConversationDelta) -> None:
        """Update a reaction in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            delta.message_id = str(message["message_id"]) if message.get("message_id", None) else None
            delta = ReactionHandler.update_message_reactions(message, cached_msg, delta)

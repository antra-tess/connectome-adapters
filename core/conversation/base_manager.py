import asyncio
import os

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.conversation.base_data_classes import BaseConversationInfo, ConversationDelta

from core.cache.message_cache import MessageCache, CachedMessage
from core.cache.attachment_cache import AttachmentCache
from core.utils.config import Config

class BaseManager(ABC):
    """Tracks and manages information about a conversations"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.conversations: Dict[str, BaseConversationInfo] = {}
        self._lock = asyncio.Lock()
        self.message_cache = MessageCache(config, start_maintenance)
        self.attachment_cache = AttachmentCache(config, start_maintenance)

    @abstractmethod
    async def add_to_conversation(self, event: Any) -> Dict[str, Any]:
        """Creates a new conversation or adds a message to an existing one"""
        raise NotImplementedError("Child classes must implement add_to_conversation")

    @abstractmethod
    async def update_conversation(self, event: Any) -> Dict[str, Any]:
        """Update conversation information based on a client event"""
        raise NotImplementedError("Child classes must implement update_conversation")

    @abstractmethod
    async def delete_from_conversation(self,
                                       incoming_event: Any = None,
                                       outgoing_event: Any = None) -> Dict[str, Any]:
        """Handle deletion of messages from a conversation"""
        raise NotImplementedError("Child classes must implement delete_from_conversation")

    @abstractmethod
    async def migrate_between_conversations(self, event: Any) -> Dict[str, Any]:
        """Handle messages migration between conversations"""
        raise NotImplementedError("Child classes must implement migrate_between_conversations")

    def get_conversation(self, conversation_id: str) -> Optional[BaseConversationInfo]:
        """Get the conversation info for a given conversation ID

        Args:
            conversation_id: The ID of the conversation to get info for

        Returns:
            The conversation info for the given conversation ID, or None if it doesn't exist
        """
        return self.conversations.get(conversation_id, None)

    def _get_or_create_conversation_info(self, message: Any) -> Optional[BaseConversationInfo]:
        """Get existing conversation info or create a new one

        Args:
            message: Message object

        Returns:
           Conversation info object or None if conversation can't be determined
        """
        conversation_id = self._get_conversation_id(message)

        if not conversation_id:
            return None
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        self.conversations[conversation_id] = self._create_conversation_info(
            conversation_id,
            self._get_conversation_type(message),
            self._get_conversation_name(message)
        )

        return self.conversations[conversation_id]
    
    @abstractmethod
    def _get_conversation_id(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a message"""
        raise NotImplementedError("Child classes must implement get_conversation_id")

    @abstractmethod
    def _get_conversation_type(self, message: Any) -> Optional[str]:
        """Get the conversation type from a message"""
        raise NotImplementedError("Child classes must implement get_conversation_type")
    
    @abstractmethod
    def _get_conversation_name(self, message: Any) -> Optional[str]:
        """Get the conversation name from a message"""
        raise NotImplementedError("Child classes must implement get_conversation_name")

    @abstractmethod
    def _create_conversation_info(self,
                                  conversation_id: str,
                                  conversation_type: str,
                                  conversation_name: Optional[str] = None) -> BaseConversationInfo:
        """Create a conversation info object"""
        raise NotImplementedError("Child classes must implement create_conversation_info")

    def _create_conversation_delta(self, conversation_info: BaseConversationInfo) -> ConversationDelta:
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

    async def _update_attachment(self,
                                 conversation_info: BaseConversationInfo,
                                 attachments: List[Dict[str, Any]] = []) -> List[Dict[str, Any]]:
        """Update attachment info in conversation info

        Args:
            conversation_info: Conversation info object
            attachments: List of attachment dictionaries

        Returns:
            List of dictionaries with attachment information
        """
        result = []

        for attachment in attachments:
            cached_attachment = await self.attachment_cache.add_attachment(
                conversation_info.conversation_id, attachment
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

    async def _update_delta_list(self,
                                 conversation_id: str,
                                 delta: ConversationDelta,
                                 list_to_update: str,
                                 attachments: Optional[List[Dict[str, Any]]] = [],
                                 message_id: Optional[str] = None,
                                 cached_msg: Optional[CachedMessage] = None) -> None:
        """Add a migrated message to the delta

        Args:
            conversation_id: Conversation ID
            delta: Delta object to update
            list_to_update: List to update
            attachments: List of attachment dictionaries
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
                "thread_id": cached_msg.thread_id,
                "attachments": attachments
            })

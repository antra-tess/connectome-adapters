import asyncio
import os

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List, Any, Union
from contextlib import contextmanager

from adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UpdateType
)
from adapter.conversation_manager.message_builder import MessageBuilder
from adapter.conversation_manager.reaction_handler import ReactionHandler
from adapter.conversation_manager.thread_builder import ThreadBuilder
from adapter.conversation_manager.user_builder import UserBuilder

from cache.message_cache import MessageCache
from cache.attachment_cache import AttachmentCache

class EventType(str, Enum):
    """Types of events that can be processed"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    CHAT_ACTION = "chat_action"
    PINNED_MESSAGE = "pinned_message"
    UNPINNED_MESSAGE = "unpinned_message"

class ConversationManager:
    """Tracks and manages information about Telegram conversations"""

    def __init__(self, start_maintenance=False):
        """Initialize the conversation manager"""
        self.conversations: Dict[str, ConversationInfo] = {}
        self.migrations: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self.message_cache = MessageCache(start_maintenance)
        self.attachment_cache = AttachmentCache(start_maintenance)
        self.reaction_handler = ReactionHandler()
        self.message_builder = MessageBuilder()
        self.thread_builder = ThreadBuilder()
        self.user_builder = UserBuilder()

    @contextmanager
    def _get_conversation(self, conversation_id: str):
        """Context manager for getting a conversation

        Args:
            conversation_id: ID of the conversation

        Yields:
            ConversationInfo object
        """
        conversation = self.conversations.get(conversation_id)
        yield conversation
        if conversation:
            conversation.last_activity = datetime.now()

    async def create_or_update_conversation(self,
                                            event_type: str,
                                            message: Any,
                                            user: Optional[Any] = None,
                                            attachment_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update conversation information based on a Telethon event

        Args:
            event_type: Type of event (new_message, edited_message, etc.)
            message: Telethon message object
            user: Optional user object
            attachment_info: Optional attachment information

        Returns:
            Dictionary with delta information
        """
        async with self._lock:
            if not message:
                return {}

            conversation_info = await self._get_or_create_conversation(message)
            if not conversation_info:
                return {}

            delta = ConversationDelta(
                conversation_id=conversation_info.conversation_id
            )

            if conversation_info.just_started:
                delta.updates.append(UpdateType.CONVERSATION_STARTED)
                conversation_info.just_started = False
            if user:
                self.user_builder.add_user_info_to_conversation(
                    user, conversation_info, delta
                )
            if attachment_info:
                attachment_data = await self._update_attachment_info(
                    conversation_info, attachment_info
                )
                delta.attachments = attachment_data["attachments"]

            if event_type in [EventType.NEW_MESSAGE, EventType.EDITED_MESSAGE]:
                await self.thread_builder.add_thread_info_to_conversation(
                    self.message_cache, message, conversation_info, delta
                )

            await self._process_event(event_type, message, conversation_info, delta)

            return delta.to_dict()

    async def _get_or_create_conversation(self, message: Any) -> Optional[ConversationInfo]:
        """Get existing conversation or create a new one from Telethon message

        Args:
            message: Telethon message object

        Returns:
            ConversationInfo object or None if conversation can't be determined
        """
        if not hasattr(message, "peer_id") and not hasattr(message, "peer"):
            return None
        
        peer = getattr(message, "peer_id", None) or getattr(message, "peer")
        conversation_id = await self._get_conversation_id(peer)

        if not conversation_id:
            return None
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        self.conversations[conversation_id] = ConversationInfo(
            conversation_id=conversation_id,
            conversation_type=await self._get_conversation_type(peer),
            just_started=True
        )

        return self.conversations[conversation_id]

    async def _get_conversation_id(self, peer: Any) -> Optional[str]:
        """Get the conversation ID from a Telethon message

        Args:
            peer: Telethon peer (user, chat or channel) object

        Returns:
            Conversation ID as string, or None if not found
        """
        if hasattr(peer, "user_id"):
            return str(peer.user_id)
        if hasattr(peer, "chat_id"):
            return str(peer.chat_id)
        if hasattr(peer, "channel_id"):
            return str(peer.channel_id)

        return None

    async def _get_conversation_type(self, peer: Any) -> Optional[str]:
        """Get the conversation type from a Telethon peer

        Args:
            peer: Telethon peer (user, chat or channel) object

        Returns:
            Conversation type as string, or None if not found
        """
        if hasattr(peer, "user_id"):
            return "private"
        if hasattr(peer, "chat_id"):
            return "group"
        if hasattr(peer, "channel_id"):
            return "channel"

        return None

    async def _update_attachment_info(self,
                                     conversation_info: ConversationInfo,
                                     attachment_info: Dict[str, Any]) -> Dict[str, Any]:
        """Update attachment info in conversation info

        Args:
            conversation_info: Conversation info object
            attachment_info: Attachment info dictionary

        Returns:
            Dictionary with attachment information
        """
        cached_attachment = await self.attachment_cache.add_attachment(
            conversation_info.conversation_id, attachment_info
        )
        conversation_info.attachments.add(cached_attachment.attachment_id)

        return {
            "attachments": [
                {
                    "attachment_id": cached_attachment.attachment_id,
                    "attachment_type": cached_attachment.attachment_type,
                    "file_extension": cached_attachment.file_extension,
                    "file_path": cached_attachment.file_path,
                    "size": cached_attachment.size
                }
            ]
        }

    async def _process_event(self,
                             event_type: str,
                             message: Any,
                             conversation_info: ConversationInfo,
                             delta: ConversationDelta) -> None:
        """Process an event based on event type

        Args:
            event_type: Type of event
            message: Telethon message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        if event_type in [EventType.NEW_MESSAGE, EventType.EDITED_MESSAGE]:
            await self._process_regular_message(event_type, message, conversation_info, delta)
            return

        if event_type == EventType.PINNED_MESSAGE:
            await self._pin_message(message, conversation_info, delta)
            return
        
        if event_type == EventType.UNPINNED_MESSAGE:
            await self._unpin_message(message, conversation_info, delta)

    async def _process_regular_message(self,
                                       event_type: str,
                                       message: Any,
                                       conversation_info: ConversationInfo,
                                       delta: ConversationDelta) -> None:
        """Process a message based on event type

        Args:
            event_type: Type of event
            message: Telethon message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        delta.message_id = str(message.id)
        delta.timestamp = int(getattr(message, "date", datetime.now()).timestamp() * 1000)

        reactions = await self.reaction_handler.extract_reactions(message.reactions)
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=delta.message_id
        )

        if event_type == EventType.EDITED_MESSAGE and cached_msg:
            if message.message is not None and message.message != cached_msg.text:
                cached_msg.text = message.message
                delta.text = cached_msg.text
                delta.updates.append(UpdateType.MESSAGE_EDITED)
            elif message.message == cached_msg.text:
                self.reaction_handler.update_message_reactions(
                    message, cached_msg, reactions, delta
                )
        else:
            await self._create_new_message(
                event_type, message, reactions, conversation_info, delta
            )

    async def _create_new_message(self,
                                  event_type: str,
                                  message: Any,
                                  reactions: Dict[str, int],
                                  conversation_info: ConversationInfo,
                                  delta: ConversationDelta) -> None:
        """Create a new message in the cache

        Args:
            event_type: Type of event
            message: Telethon message object
            reactions: Extracted reactions
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        message_data = self.message_builder.reset() \
            .with_basic_info(message, conversation_info.conversation_id) \
            .with_sender_info(delta.sender) \
            .with_thread_info(delta.thread_id, message) \
            .with_content(message) \
            .build()

        cached_msg = await self.message_cache.add_message(message_data)
        conversation_info.message_count += 1
        cached_msg.reactions = reactions

        delta.text = cached_msg.text

        if event_type == EventType.NEW_MESSAGE:
            delta.updates.append(UpdateType.MESSAGE_RECEIVED)
        else:
            delta.updates.append(UpdateType.MESSAGE_EDITED)

    async def _pin_message(self,
                           message: Any,
                           conversation_info: ConversationInfo,
                           delta: ConversationDelta) -> None:
        """Process a pinned message event

        Args:
            message: Telethon message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        if hasattr(message, 'reply_to') and message.reply_to:
            delta.message_id = str(message.reply_to.reply_to_msg_id)
            delta.timestamp = int(getattr(message, "date", datetime.now()).timestamp() * 1000)
            
            await self._update_pin_status(
                delta.message_id, conversation_info, delta, True
            )

    async def _unpin_message(self,
                             message: Any,
                             conversation_info: ConversationInfo,
                             delta: ConversationDelta) -> None:
        """Process an unpinned message event

        Args:
            message: Telethon message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        if hasattr(message, 'messages') and message.messages:
            delta.message_id = str(message.messages[0])
            delta.timestamp = int(datetime.now().timestamp() * 1000)
            
            await self._update_pin_status(
                delta.message_id, conversation_info, delta, False
            )

    async def _update_pin_status(self, 
                                message_id: str,
                                conversation_info: ConversationInfo,
                                delta: ConversationDelta,
                                is_pinned: bool) -> None:
        """Update the pin status of a message

        Args:
            message_id: ID of the message
            conversation_info: Conversation info object
            delta: Delta object to update
            is_pinned: Whether the message is pinned
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=message_id
        )

        print(cached_msg)
        print(self.message_cache.messages)
        print(conversation_info.conversation_id)
        print(message_id)

        if not cached_msg:
            return

        cached_msg.is_pinned = is_pinned
        
        if is_pinned:
            conversation_info.pinned_messages.add(message_id)
            delta.updates.append(UpdateType.MESSAGE_PINNED)
        else:
            conversation_info.pinned_messages.discard(message_id)
            delta.updates.append(UpdateType.MESSAGE_UNPINNED)

    async def delete_from_conversation(self,
                                       deleted_ids: List[Union[str, int]],
                                       conversation_id: Optional[Union[str, int]] = None) -> Optional[str]:
        """Handle deletion of messages from a conversation

        Args:
            deleted_ids: List of message IDs to delete
            conversation_id: Optional conversation ID

        Returns:
            Conversation ID if successful, None otherwise
        """
        if not deleted_ids:
            return None

        async with self._lock:
            deleted_ids = [str(msg_id) for msg_id in deleted_ids]
            conversation_info = self._find_conversation_info_to_delete_from(
                deleted_ids, str(conversation_id)
            )

            if conversation_info:
                for msg_id in deleted_ids:
                    if await self.message_cache.delete_message(
                        conversation_info.conversation_id, msg_id
                    ):
                        conversation_info.message_count -= 1

                return conversation_info.conversation_id

            return None

    def _find_conversation_info_to_delete_from(self,
                                             deleted_ids: List[str],
                                             conversation_id: Optional[str]) -> Optional[ConversationInfo]:
        """Find the conversation to delete from

        Args:
            deleted_ids: List of message IDs to delete
            conversation_id: Optional conversation ID

        Returns:
            ConversationInfo object if found, None otherwise
        """
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]

        best_match = None
        best_match_count = 0

        for id, messages in self.message_cache.messages.items():
            matching_ids = set(deleted_ids).intersection(set(messages.keys()))
            if not matching_ids:
                continue

            match_count = len(matching_ids)
            if match_count > best_match_count:
                best_match = self.conversations[id]
                best_match_count = match_count

        return best_match

    async def migrate_conversation(self,
                                   old_conversation_id: Optional[Union[str, int]],
                                   new_conversation_id: Optional[Union[str, int]]) -> None:
        """Handle a supergroup that was migrated from a regular group

        Args:
            old_conversation_id: Old conversation ID
            new_conversation_id: New conversation ID
        """
        if not old_conversation_id or not new_conversation_id:
            return

        old_conversation_id = str(old_conversation_id)
        new_conversation_id = str(new_conversation_id)

        async with self._lock:
            self.migrations[old_conversation_id] = new_conversation_id

            if old_conversation_id in self.conversations:
                self.conversations[old_conversation_id].migrated_to_conversation_id = new_conversation_id
            if new_conversation_id not in self.conversations:
                self.conversations[new_conversation_id] = ConversationInfo(
                    conversation_id=new_conversation_id,
                    conversation_type='supergroup'
                )

            self.conversations[new_conversation_id].migrated_from_conversation_id = old_conversation_id

            if old_conversation_id in self.conversations:
                old_conv = self.conversations[old_conversation_id]
                new_conv = self.conversations[new_conversation_id]
                old_conv.migrated_to_conversation_id = new_conversation_id
                new_conv.known_members.update(old_conv.known_members)

            await self.message_cache.migrate_messages(old_conversation_id, new_conversation_id)

    def attachment_download_required(self, message: Any) -> bool:
        """Check if attachment download or upload is required for a message

        Args:
            message: Telethon message object

        Returns:
            True if download is required, False otherwise
        """
        if not message or not hasattr(message, "media") or not message.media:
            return False

        attachment_id = None
        if hasattr(message, "photo") and message.photo:
            attachment_id = str(message.photo.id)
        elif hasattr(message, "document") and message.document:
            attachment_id = str(message.document.id)

        if attachment_id:
            return (
                attachment_id not in self.attachment_cache.attachments or
                not os.path.exists(self.attachment_cache.attachments[attachment_id].file_path)
            )

        return False

import asyncio
import json
import logging
import os
import telethon

from enum import Enum
from typing import List, Dict, Any, Optional, Union

from core.utils.config import Config
from adapters.telegram_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader

class EventType(str, Enum):
    """Event types supported by the TelegramEventsProcessor"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    CHAT_ACTION = "chat_action"

class TelegramEventsProcessor:
    """Telegram events processor"""

    def __init__(self,
                 config: Config,
                 telethon_client,
                 conversation_manager: ConversationManager,
                 adapter_name: str):
        """Initialize the Telegram events processor

        Args:
            config: Config instance
            telethon_client: Telethon client instance
            conversation_manager: Conversation manager for tracking message history
            adapter_name: Name of the adapter (typically bot username)
        """
        self.config = config
        self.telethon_client = telethon_client
        self.conversation_manager = conversation_manager
        self.adapter_name = adapter_name
        self.adapter_type = self.config.get_setting("adapter", "type")
        self.downloader = Downloader(self.config, self.telethon_client)

    async def process_event(self, event_type: str, event: Any) -> List[Dict[str, Any]]:
        """Process events from Telethon client

        Args:
            event_type: Type of event (new_message, edited_message, deleted_message, chat_action)
            event: Telethon event object

        Returns:
            List of standardized event dictionaries to emit
        """
        try:
            event_handlers = {
                EventType.NEW_MESSAGE: self._handle_new_message,
                EventType.EDITED_MESSAGE: self._handle_edited_message,
                EventType.DELETED_MESSAGE: self._handle_deleted_message,
                EventType.CHAT_ACTION: self._handle_chat_action
            }

            print(event)
            print()

            handler = event_handlers.get(event_type)
            if handler:
                return await handler(event)

            logging.debug(f"Unhandled event type: {event_type}")
            return []
        except Exception as e:
            logging.error(f"Error processing Telethon event: {e}", exc_info=True)
            return []

    async def _handle_new_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a new message event from Telegram

        Args:
            event: Telethon event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            message = event.message
            attachment_info = await self.downloader.download_attachment(
                message,
                self.conversation_manager.attachment_download_required(message)
            )
            delta = await self.conversation_manager.create_or_update_conversation(
                "new_message",
                message,
                await self._get_user(message),
                attachment_info
            )

            if delta:
                if "conversation_started" in delta["updates"]:
                    events.append(await self._conversation_started_event_info(delta))
                if "message_received" in delta["updates"]:
                    events.append(await self._new_message_event_info(delta))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

    async def _get_user(self, message: Any) -> Optional[Any]:
        """Get user information from Telegram

        Args:
            message: Telethon message object

        Returns:
            Telethon user object or None if not found
        """
        try:
            if message and hasattr(message, "from_id") and hasattr(message.from_id, "user_id"):
                return await self.telethon_client.get_entity(int(message.from_id.user_id))
            if message and hasattr(message, "peer_id") and hasattr(message.peer_id, "user_id"):
                return await self.telethon_client.get_entity(int(message.peer_id.user_id))
        except Exception as e:
            logging.error(f"Error getting user: {e}")

        return None

    async def _conversation_started_event_info(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create a conversation started event

        Args:
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "conversation_started",
            "data" : {
                "conversation_id": delta["conversation_id"],
                "history": []
            }
        }

    async def _new_message_event_info(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new message event

        Args:
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_received",
            "data" : {
                "adapter_name": self.adapter_name,
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "sender": {
                    "user_id": delta["sender"]["user_id"] if "sender" in delta else "Unknown",
                    "display_name": delta["sender"]["display_name"] if "sender" in delta else "Unknown User"
                },
                "text": delta["text"] if "text" in delta else "",
                "thread_id": delta["thread_id"] if "thread_id" in delta else None,
                "attachments": delta["attachments"] if "attachments" in delta else [],
                "timestamp": delta["timestamp"]  # in milliseconds
            }
        }

    async def _handle_edited_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle an edited message event from Telethon

        Args:
            event: Telethon event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.create_or_update_conversation(
                "edited_message", event.message
            )

            if delta:
                if "message_edited" in delta["updates"]:
                    events.append(await self._edited_message_event_info(delta))
                if "reaction_added" in delta["updates"]:
                    for reaction in delta["added_reactions"]:
                        events.append(
                            await self._reaction_update_event_info(
                                "reaction_added", delta, reaction
                            )
                        )
                if "reaction_removed" in delta["updates"]:
                    for reaction in delta["removed_reactions"]:
                        events.append(
                            await self._reaction_update_event_info(
                                "reaction_removed", delta, reaction
                            )
                        )
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return events

    async def _edited_message_event_info(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create an edited message event

        Args:
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_updated",
            "data" : {
                "adapter_name": self.adapter_name,
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "new_text": delta["text"] if "text" in delta else '',
                "timestamp": delta["timestamp"]
            }
        }

    async def _reaction_update_event_info(self,
                                          event_type: str,
                                          delta: Dict[str, Any],
                                          reaction: str) -> Dict[str, Any]:
        """Create a reaction event

        Args:
            event_type: Type of reaction event (added/removed)
            delta: Event change information
            reaction: Emoji reaction

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": event_type,
            "data" : {
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "emoji": reaction
            }
        }

    async def _handle_deleted_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a deleted message event from Telethon

        Args:
            event: Telethon event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            conversation_id = await self.conversation_manager.delete_from_conversation(
                getattr(event, "deleted_ids", []),
                getattr(event, "channel_id", None)
            )

            if conversation_id:
                for deleted_id in event.deleted_ids:
                    events.append(
                        await self._deleted_message_event_info(deleted_id, conversation_id)
                    )
        except Exception as e:
            logging.error(f"Error handling deleted message: {e}", exc_info=True)

        return events

    async def _deleted_message_event_info(self,
                                          message_id: Union[int, str],
                                          conversation_id: Union[int, str]) -> Dict[str, Any]:
        """Create a message deleted event

        Args:
            message_id: ID of the deleted message
            conversation_id: ID of the conversation

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_deleted",
            "data" : {
                "message_id": str(message_id),
                "conversation_id": str(conversation_id)
            }
        }

    async def _handle_chat_action(self, event: Any) -> List[Dict[str, Any]]:
        """Handle chat action events like user joins, leaves, or group migrations

        Args:
            event: Telethon event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        try:
            message = event.action_message

            if message and hasattr(message, "action"):
                action = message.action
                action_type = type(action).__name__

                if action_type in [
                    "MessageActionChatMigrateTo",
                    "MessageActionChannelMigrateFrom"
                ]:
                    await self.conversation_manager.migrate_conversation(
                        getattr(message.peer_id, "chat_id", None),
                        getattr(action, "channel_id", None)
                    )
                    return []
                
                if action_type == "MessageActionPinMessage":
                    delta = await self.conversation_manager.create_or_update_conversation("pinned_message", message)    
                    if delta and "message_pinned" in delta["updates"]:
                        return [await self._pinned_status_change_event_info("message_pinned", delta)]

            elif not message and hasattr(event, "original_update"):
                delta = await self.conversation_manager.create_or_update_conversation(
                    "unpinned_message",
                    event.original_update
                )
                if delta and "message_unpinned" in delta["updates"]:
                    return [await self._pinned_status_change_event_info("message_unpinned", delta)]
        except Exception as e:
            logging.error(f"Error handling chat action: {e}", exc_info=True)

        return []
    
    async def _pinned_status_change_event_info(self,
                                               event_type: str,
                                               delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create a pinned message status change event

        Args:
            event_type: Type of change (pinned/unpinned)
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": event_type,
            "data" : {
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"]
            }
        }

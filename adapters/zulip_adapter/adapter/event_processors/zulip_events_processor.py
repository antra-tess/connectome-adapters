import asyncio
import json
import logging
import os

from enum import Enum
from typing import List, Dict, Any, Optional, Union

from core.utils.config import Config
from adapters.zulip_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from adapters.zulip_adapter.adapter.attachment_loaders.downloader import Downloader

class EventType(str, Enum):
    """Event types supported by the ZulipEventsProcessor"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    CHAT_ACTION = "chat_action"

class ZulipEventsProcessor:
    """Zulip events processor"""

    def __init__(self,
                 config: Config,
                 conversation_manager: ConversationManager,
                 adapter_name: str):
        """Initialize the Zulip events processor

        Args:
            config: Config instance
            conversation_manager: Conversation manager for tracking message history
            adapter_name: Name of the adapter (typically bot username)
        """
        self.config = config
        self.conversation_manager = conversation_manager
        self.adapter_name = adapter_name
        self.adapter_type = self.config.get_setting("adapter", "type")
        self.downloader = Downloader(self.config)

    async def process_event(self, event_type: str, event: Any) -> List[Dict[str, Any]]:
        """Process events from Zulip client

        Args:
            event_type: Type of event (new_message, edited_message, deleted_message, chat_action)
            event: Zulip event object

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
            logging.error(f"Error processing Zulip event: {e}", exc_info=True)
            return []

    async def _handle_new_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a new message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            pass
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

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
        """Handle an edited message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            pass
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
        """Handle a deleted message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            pass
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
            event: Zulip event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        try:
            pass
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

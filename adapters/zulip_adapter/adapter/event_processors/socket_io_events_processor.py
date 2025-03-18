import asyncio
import json
import logging
import os

from enum import Enum
from typing import Dict, Any, List, Optional, Union

from adapters.zulip_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader
from core.utils.config import Config

class EventType(str, Enum):
    """Event types supported by the SocketIoEventsProcessor"""
    SEND_MESSAGE = "send_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    ADD_REACTION = "add_reaction"
    REMOVE_REACTION = "remove_reaction"

class SocketIoEventsProcessor:
    """Processes events from socket.io and sends them to Zulip"""

    def __init__(self, config: Config, conversation_manager: ConversationManager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            conversation_manager: Conversation manager for tracking message history
        """
        self.config = config
        self.conversation_manager = conversation_manager
        self.adapter_type = "zulip"
        self.uploader = Uploader(self.config)

    async def process_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Process an event based on its type

        Args:
            event_type: The type of event to process
            data: The event data

        Returns:
            bool: True if successful, False otherwise
        """
        event_handlers = {
            EventType.SEND_MESSAGE: self._send_message,
            EventType.EDIT_MESSAGE: self._edit_message,
            EventType.DELETE_MESSAGE: self._delete_message,
            EventType.ADD_REACTION: self._add_reaction,
            EventType.REMOVE_REACTION: self._remove_reaction
        }

        handler = event_handlers.get(event_type)
        if handler:
            return await handler(data)

        logging.error(f"Unknown event type: {event_type}")
        return False

    async def _send_message(self, data: Dict[str, Any]) -> bool:
        """Send a message to a chat

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._validate_required_fields(
            data, ["conversation_id", "text"], "send_message"
        ):
            return False

        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        message_text = data.get("text")
        reply_to_message_id = data.get("thread_id", None)
        attachments = data.get("attachments", [])

        try:
            logging.info(f"Message sent to conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to send message to conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    async def _edit_message(self, data: Dict[str, Any]) -> bool:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._validate_required_fields(
            data, ["conversation_id", "message_id", "text"], "edit_message"
        ):
            return False

        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        message_id = int(data.get("message_id"))
        message_text = data.get("text")

        try:
            logging.info(f"Message edited in conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to edit message {message_id} in conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    async def _delete_message(self, data: Dict[str, Any]) -> bool:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._validate_required_fields(
            data, ["conversation_id", "message_id"], "delete_message"
        ):
            return False

        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        message_id = int(data.get("message_id"))

        try:
            logging.info(f"Message deleted in conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to delete message {message_id} in conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    async def _add_reaction(self, data: Dict[str, Any]) -> bool:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._validate_required_fields(
            data, ["conversation_id", "message_id", "emoji"], "add_reaction"
        ):
            return False

        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        message_id = int(data.get("message_id"))
        emoji = data.get("emoji")

        try:
            logging.info(f"Reaction added to message {message_id} in conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to add reaction to message {message_id} in conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    async def _remove_reaction(self, data: Dict[str, Any]) -> bool:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            bool: True if successful, False otherwise
        """
        if not self._validate_required_fields(
            data, ["conversation_id", "message_id", "emoji"], "remove_reaction"
        ):
            return False

        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        message_id = int(data.get("message_id"))
        emoji = data.get("emoji")

        try:
            logging.info(f"Reaction removed from message {message_id} in conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to remove reaction from message {message_id} in conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    def _validate_required_fields(self,
                                  data: Dict[str, Any],
                                  required_fields: List[str],
                                  operation: str) -> bool:
        """Validate that required fields are present in the data

        Args:
            data: The data to validate
            required_fields: List of required field names
            operation: Name of the operation for error logging

        Returns:
            bool: True if all required fields are present, False otherwise
        """
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            logging.error(f"{', '.join(missing_fields)} are required for {operation}")
            return False

        return True

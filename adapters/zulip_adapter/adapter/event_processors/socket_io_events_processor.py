import asyncio
import emoji
import json
import logging
import os

from enum import Enum
from typing import Dict, Any, List, Optional, Union

from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.zulip_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from adapters.zulip_adapter.adapter.zulip_client import ZulipClient

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

    def __init__(self,
                 config: Config,
                 client: ZulipClient,
                 conversation_manager: ConversationManager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Zulip client instance
            conversation_manager: Conversation manager for tracking message history
        """
        self.config = config
        self.client = client
        self.conversation_manager = conversation_manager
        self.adapter_type = "zulip"
        self.uploader = Uploader(self.config, self.client)

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

        try:
            conversation_id = data["conversation_id"]
            messages = self._split_long_message(data["text"])

            for attachment in data.get("attachments", []):
                uri = await self.uploader.upload_attachment(attachment)
                file_name = uri.split("/")[-1]
                messages[-1] += f"\n[{file_name}]({uri})"

            if self._is_conversation_private(conversation_id):
                message_type = "private"
                to_field = self._get_private_to_field(conversation_id)
                subject = None
            else:
                message_type = "stream"
                stream_details = conversation_id.split("/")
                to_field = self._get_stream_to_field(stream_details[0])
                subject = stream_details[1]

            for message in messages:
                if not self._check_api_request_success(
                    self.client.send_message({
                        "type": message_type,
                        "to": to_field,
                        "content": message,
                        "subject": subject
                    }),
                    f"send message to {conversation_id}"
                ):
                    return False

                if len(messages) > 1:
                    await asyncio.sleep(1)
                    
            logging.info(f"Message sent to {conversation_id}")
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
        
        try:
            if not self._check_api_request_success(
                self.client.update_message({
                    "message_id": int(data["message_id"]),
                    "content": data["text"]
                }),
                f"edit message {data['message_id']}"
            ):
                return False

            logging.info(f"Message {data['message_id']} edited successfully")
            return True
        except Exception as e:
            logging.error(
                f"Failed to edit message {data['message_id']}: {e}",
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

        try:
            if not self._check_api_request_success(
                self.client.call_endpoint(
                    f"messages/{int(data['message_id'])}",
                    method="DELETE"
                ),
                f"delete message {data['message_id']}"
            ):
                return False

            await self.conversation_manager.delete_from_conversation(
                data["message_id"], data["conversation_id"]
            )
            logging.info(f"Message {data['message_id']} deleted successfully")
            return True
        except Exception as e:
            logging.error(
                f"Failed to delete message {data['message_id']}: {e}",
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

        try:
            if not self._check_api_request_success(
                self.client.add_reaction({
                    "message_id": int(data["message_id"]),
                    "emoji_name": self._get_emoji_name(data["emoji"])
                }),
                f"add reaction to {data['message_id']}"
            ):
                return False
            
            logging.info(f"Reaction {data['emoji']} added to message {data['message_id']}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to add reaction to message {data['message_id']}: {e}",
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

        try:
            if not self._check_api_request_success(
                self.client.remove_reaction({
                    "message_id": int(data["message_id"]),
                    "emoji_name": self._get_emoji_name(data["emoji"])
                }),
                f"remove reaction from {data['message_id']}"
            ):
                return False

            logging.info(f"Reaction {data['emoji']} removed from message {data['message_id']}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to remove reaction from message {data['message_id']}: {e}",
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

    def _check_api_request_success(self,
                                   result: Optional[Dict[str, Any]],
                                   operation: str) -> bool:
        """Check if a Zulip API result was successful
        
        Args:
            result: API response dictionary
            operation: Description of operation for logging
            
        Returns:
            bool: True if successful, False otherwise
        """
        if result and result.get("result", None) == "success":
            return True
        
        error_msg = result.get("msg", "Unknown error") if result else "No response"
        logging.error(f"Failed to {operation}: {error_msg}")
        return False

    def _is_conversation_private(self, conversation_id: str) -> bool:
        """Check if a conversation is private

        Args:
            conversation_id: Conversation ID

        Returns:
            bool: True if private, False otherwise
        """
        return "_" in conversation_id

    def _get_private_to_field(self, conversation_id: str) -> Any:
        """Get the private to field based on the conversation ID

        Args:
            conversation_id: Conversation ID in our format

        Returns:
            str: To field for Zulip
        """
        emails = []
        user_ids = conversation_id.split("_")

        for user_id in user_ids:
            user_info = self.client.get_user_by_id(int(user_id))

            if user_info and user_info.get("result", None) == "success":
                email = user_info.get("user", {}).get("email", None)
                if email:
                    emails.append(email)

        return emails

    def _get_stream_to_field(self, stream_id: str) -> Any:
        """Get the stream to field based on the stream ID

        Args:
            stream_id: Stream ID

        Returns:
            str: To field for Zulip
        """
        result = self.client.get_streams()

        if result and result.get("result", None) == "success":
            for stream in result.get("streams", []):
                if stream.get("stream_id", None) == int(stream_id):
                    return stream.get("name", None)
        
        return None

    def _split_long_message(self, text: str) -> List[str]:
        """Split a long message at sentence boundaries to fit within Zulip's message length limits.
        
        Args:
            text: The message text to split
            
        Returns:
            List of message parts, each under the maximum length
        """
        max_length = self.config.get_setting("adapter", "max_message_length")

        if len(text) <= max_length:
            return [text]

        sentence_endings = [".", "!", "?", ".\n", "!\n", "?\n", ".\t", "!\t", "?\t"]
        message_parts = []
        remaining_text = text
        
        while len(remaining_text) > max_length:
            cut_point = max_length

            for i in range(max_length - 1, max(0, max_length - 200), -1):
                for ending in sentence_endings:
                    end_pos = i - len(ending) + 1
                    if end_pos >= 0 and remaining_text[end_pos:i+1] == ending:
                        cut_point = i + 1  # Include the ending punctuation and space
                        break                
                if cut_point < max_length:
                    break
            if cut_point == max_length:
                last_newline = remaining_text.rfind("\n", 0, max_length)
                if last_newline > max_length // 2:
                    cut_point = last_newline + 1
                else:
                    last_space = remaining_text.rfind(" ", max_length // 2, max_length)
                    if last_space > 0:
                        cut_point = last_space + 1
                    else:
                        cut_point = max_length
            
            message_parts.append(remaining_text[:cut_point])
            remaining_text = remaining_text[cut_point:]
        
        if remaining_text:
            message_parts.append(remaining_text)
        
        return message_parts

    def _get_emoji_name(self, unicode_emoji: str) -> str:
        """Convert Unicode emoji to its name for Zulip

        Args:
            unicode_emoji: Unicode emoji

        Returns:
            str: Zulip emoji name
        """
        emoji_name = emoji.demojize(unicode_emoji).strip(":")

        # Handle special cases for Zulip
        if emoji_name == "+1":
            emoji_name = "thumbs_up"
        elif emoji_name == "-1":
            emoji_name = "thumbs_down"
            
        return emoji_name

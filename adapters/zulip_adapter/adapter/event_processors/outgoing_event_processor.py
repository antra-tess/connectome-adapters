import asyncio
import emoji
import json
import logging
import os

from enum import Enum
from typing import Dict, Any, List, Optional, Union

from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.zulip_adapter.adapter.conversation.manager import Manager

from core.event_processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from core.utils.config import Config

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Zulip"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Zulip client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.uploader = Uploader(self.config, self.client)

    async def _send_message(self, data: Dict[str, Any]) -> bool:
        """Send a message to a chat

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            bool: True if successful, False otherwise
        """
        conversation_info = self.conversation_manager.get_conversation(data["conversation_id"])
        if not conversation_info:
            logging.error(f"Conversation {data['conversation_id']} not found")
            return False

        messages = self._split_long_message(data["text"])
        for attachment in data.get("attachments", []):
            await self.rate_limiter.limit_request("upload_attachment", conversation_info.conversation_id)
            uri = await self.uploader.upload_attachment(attachment)
            file_name = uri.split("/")[-1]
            messages[-1] += f"\n[{file_name}]({uri})"

        to_field = conversation_info.to_fields()
        message_type = conversation_info.conversation_type
        subject = None

        if conversation_info.conversation_type == "stream":
            subject = conversation_info.conversation_id.split("/")[1]

        for message in messages:
            await self.rate_limiter.limit_request("message", conversation_info.conversation_id)

            message_data = {
                "type": message_type,
                "to": to_field,
                "content": message,
                "subject": subject
            }

            if not self._check_api_request_success(
                self.client.send_message(message_data),
                f"send message to {conversation_info.conversation_id}"
            ):
                return False

        logging.info(f"Message sent to {conversation_info.conversation_id}")
        return True

    async def _edit_message(self, data: Dict[str, Any]) -> bool:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            bool: True if successful, False otherwise
        """
        await self.rate_limiter.limit_request("update_message", data["conversation_id"])

        message_data = {
            "message_id": int(data["message_id"]),
            "content": data["text"]
        }

        if not self._check_api_request_success(
            self.client.update_message(message_data),
            f"edit message {data['message_id']}"
        ):
            return False

        logging.info(f"Message {data['message_id']} edited successfully")
        return True

    async def _delete_message(self, data: Dict[str, Any]) -> bool:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            bool: True if successful, False otherwise
        """
        await self.rate_limiter.limit_request("delete_message", data["conversation_id"])

        if not self._check_api_request_success(
            self.client.call_endpoint(
                f"messages/{int(data['message_id'])}",
                method="DELETE"
            ),
            f"delete message {data['message_id']}"
        ):
            return False

        await self.conversation_manager.delete_from_conversation(
            outgoing_event={
                "message_id": data["message_id"],
                "conversation_id": data["conversation_id"]
            }
        )

        logging.info(f"Message {data['message_id']} deleted successfully")
        return True

    async def _add_reaction(self, data: Dict[str, Any]) -> bool:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            bool: True if successful, False otherwise
        """
        await self.rate_limiter.limit_request("add_reaction", data["conversation_id"])

        reaction_data = {
            "message_id": int(data["message_id"]),
            "emoji_name": self._get_emoji_name(data["emoji"])
        }

        if not self._check_api_request_success(
            self.client.add_reaction(reaction_data),
            f"add reaction to {data['message_id']}"
        ):
            return False

        logging.info(f"Reaction {data['emoji']} added to message {data['message_id']}")
        return True

    async def _remove_reaction(self, data: Dict[str, Any]) -> bool:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            bool: True if successful, False otherwise
        """
        await self.rate_limiter.limit_request("remove_reaction", data["conversation_id"])

        reaction_data = {
            "message_id": int(data["message_id"]),
            "emoji_name": self._get_emoji_name(data["emoji"])
        }

        if not self._check_api_request_success(
            self.client.remove_reaction(reaction_data),
            f"remove reaction from {data['message_id']}"
        ):
            return False

        logging.info(f"Reaction {data['emoji']} removed from message {data['message_id']}")
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

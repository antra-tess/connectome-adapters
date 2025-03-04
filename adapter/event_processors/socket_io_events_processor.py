import asyncio
import json
import logging
import os
import telethon

from enum import Enum
from telethon import functions
from telethon.tl.types import ReactionEmoji
from typing import Dict, Any, List, Optional, Union

from adapter.conversation_manager.conversation_manager import ConversationManager
from adapter.attachment_loaders.uploader import Uploader

class EventType(str, Enum):
    """Event types supported by the SocketIoEventsProcessor"""
    SEND_MESSAGE = "send_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    ADD_REACTION = "add_reaction"
    REMOVE_REACTION = "remove_reaction"

class SocketIoEventsProcessor:
    """Processes events from socket.io and sends them to Telegram"""

    def __init__(self, telethon_client, conversation_manager: ConversationManager):
        """Initialize the socket.io events processor

        Args:
            telethon_client: Telethon client instance
            conversation_manager: Conversation manager for tracking message history
        """
        self.telethon_client = telethon_client
        self.conversation_manager = conversation_manager
        self.adapter_type = "telegram"
        self.uploader = Uploader(self.telethon_client)

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
            entity = await self._get_entity(conversation_id)
            if not entity:
                return False

            await self.conversation_manager.create_or_update_conversation(
                "new_message",
                await self.telethon_client.send_message(
                    entity=entity,
                    message=message_text,
                    reply_to=reply_to_message_id
                )
            )

            for attachment in attachments:
                await asyncio.sleep(3)

                attachment_info = await self.uploader.upload_attachment(entity, attachment)
                if attachment_info and attachment_info.get("message"):
                    message = attachment_info["message"]
                    del attachment_info["message"]
                    await self.conversation_manager.create_or_update_conversation(
                        "new_message", message, attachment_info=attachment_info
                    )

            logging.info(f"Message sent to conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to send message to conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    def _format_conversation_id(self, conversation_id: Union[str, int]) -> Union[str, int]:
        """Format a conversation ID based on conversation type

        Args:
            conversation_id: The conversation ID to format

        Returns:
            The formatted conversation ID
        """
        if conversation_id in self.conversation_manager.conversations:
            conversation_info = self.conversation_manager.conversations[conversation_id]

            if conversation_info.conversation_type == "private":
                return int(conversation_id)
            if conversation_info.conversation_type == "group":
                return int(conversation_id) * -1
            if conversation_info.conversation_type == "channel":
                return int(f"-100{conversation_id}")

        try:
            return int(conversation_id)
        except (ValueError, TypeError):
            return conversation_id

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
            entity = await self._get_entity(conversation_id)
            if not entity:
                return False

            await self.conversation_manager.create_or_update_conversation(
                "edited_message",
                await self.telethon_client.edit_message(
                    entity=entity,
                    message=message_id,
                    text=message_text
                )
            )

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
            entity = await self._get_entity(conversation_id)
            if not entity:
                return False

            messages = await self.telethon_client.delete_messages(
                entity=entity,
                message_ids=[message_id]
            )
            if messages:
                await self.conversation_manager.delete_from_conversation(
                    [message_id], conversation_id
                )

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
            entity = await self._get_entity(conversation_id)
            if not entity:
                return False

            await self.conversation_manager.create_or_update_conversation(
                "edited_message",
                await self.telethon_client(functions.messages.SendReactionRequest(
                    peer=entity,
                    msg_id=message_id,
                    reaction=[ReactionEmoji(emoticon=emoji)]
                ))
            )

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
            entity = await self._get_entity(conversation_id)
            if not entity:
                return False

            old_message = await self.telethon_client.get_messages(entity, ids=message_id)
            old_reactions = getattr(old_message, "reactions", None) if old_message else None
            new_reactions = self._update_reactions_list(old_reactions, emoji)

            await self.conversation_manager.create_or_update_conversation(
                "edited_message",
                await self.telethon_client(functions.messages.SendReactionRequest(
                    peer=entity,
                    msg_id=message_id,
                    reaction=new_reactions
                ))
            )

            logging.info(f"Reaction removed from message {message_id} in conversation {conversation_id}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to remove reaction from message {message_id} in conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False

    def _update_reactions_list(self, reactions, emoji_to_remove: str) -> List[Any]:
        """Remove a specific reaction from a message's reactions

        Args:
            reactions: Current reactions on the message
            emoji_to_remove: Emoji to remove

        Returns:
            List of reactions to keep
        """
        reaction_counts = {}
        reactions_to_add = []

        if reactions:
            for reaction in getattr(reactions, "results", []):
                emoticon = reaction.reaction.emoticon
                reaction_counts[emoticon] = reaction_counts.get(emoticon, 0) + 1

            if emoji_to_remove in reaction_counts:
                reaction_counts[emoji_to_remove] -= 1
                if reaction_counts[emoji_to_remove] <= 0:
                    del reaction_counts[emoji_to_remove]

        for emoji_type, count in reaction_counts.items():
            for _ in range(count):
                reactions_to_add.append(ReactionEmoji(emoticon=emoji_type))

        return reactions_to_add

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

    async def _get_entity(self, conversation_id: Union[str, int]) -> Optional[Any]:
        """Get an entity from a conversation ID

        Args:
            conversation_id: The conversation ID

        Returns:
            The entity or None if not found
        """
        try:
            return await self.telethon_client.get_entity(conversation_id)
        except Exception as e:
            logging.error(f"Failed to get entity for conversation {conversation_id}: {e}")
            return None

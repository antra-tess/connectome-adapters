import asyncio
import json
import logging
import os

from enum import Enum
from typing import List, Dict, Any, Optional, Union

from adapters.zulip_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.zulip_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from adapters.zulip_adapter.adapter.zulip_client import ZulipClient

from core.utils.config import Config

class EventType(str, Enum):
    """Event types supported by the ZulipEventsProcessor"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    REACTION = "reaction"

class ZulipEventsProcessor:
    """Zulip events processor"""

    def __init__(self,
                 config: Config,
                 client: ZulipClient,
                 conversation_manager: ConversationManager):
        """Initialize the Zulip events processor

        Args:
            config: Config instance
            client: Zulip client instance
            conversation_manager: Conversation manager for tracking message history
        """
        self.config = config
        self.client = client
        self.conversation_manager = conversation_manager
        self.adapter_name = self.config.get_setting("adapter", "adapter_name")
        self.adapter_type = self.config.get_setting("adapter", "adapter_type")
        self.downloader = Downloader(self.config, self.client)

    async def process_event(self, event: Any) -> List[Dict[str, Any]]:
        """Process events from Zulip client

        Args:
            event: Zulip event object

        Returns:
            List of standardized event dictionaries to emit
        """
        try:
            event_handlers = {
                EventType.MESSAGE: self._handle_message,
                EventType.UPDATE_MESSAGE: self._handle_update_message,  
                EventType.REACTION: self._handle_reaction
            }

            handler = event_handlers.get(event["type"])
            if handler:
                return await handler(event)

            logging.debug(f"Unhandled event type: {event['type']}")
            return []
        except Exception as e:
            logging.error(f"Error processing Zulip event: {e}", exc_info=True)
            return []

    async def _handle_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a new message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.add_to_conversation(
                event.get("message", None),
                await self.downloader.download_attachment(event.get("message", None))
            )

            if delta:
                if delta.get("fetch_history", False):
                    history = await self._fetch_conversation_history()
                    events.append(await self._conversation_started_event_info(delta, history))

                for message in delta.get("added_messages", []):
                    events.append(await self._new_message_event_info(message))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

    async def _fetch_conversation_history(self) -> List[Dict[str, Any]]:
        """Fetch conversation history"""
        return []

    async def _conversation_started_event_info(self,
                                               delta: Dict[str, Any],
                                               history: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            delta: Message data (either from a new message or a migrated message)

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

    async def _handle_update_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle an update message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        try:
            if self._is_topic_change(event):
                return await self._handle_topic_change(event)
            else:
                return await self._handle_message_change(event)
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return []
    
    def _is_topic_change(self, event: Dict[str, Any]) -> bool:
        """Check if the event is a topic change

        Args:
            event: Zulip event object

        Returns:
            True if the event is a topic change, False otherwise
        """
        subject = event.get("subject", None)
        orig_subject = event.get("orig_subject", None)

        return subject and orig_subject and subject != orig_subject
    
    async def _handle_topic_change(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a topic change event

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []
        delta = await self.conversation_manager.migrate_between_conversations(event)

        if delta:
            if delta.get("fetch_history", False):
                history = await self._fetch_conversation_history()
                events.append(await self._conversation_started_event_info(delta, history))

            old_conversation_id = f"{event.get('stream_id', '')}/{event.get('orig_subject', '')}"
            for message_id in delta.get("deleted_message_ids", []):
                events.append(
                    await self._deleted_message_event_info(message_id, old_conversation_id)
                )
            for migrated_message in delta.get("added_messages", []):
                events.append(
                    await self._new_message_event_info(migrated_message)
                )
        
        return events
    
    async def _handle_message_change(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a message change event

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []
        delta = await self.conversation_manager.update_conversation(
            "update_message",
            event,
            await self.downloader.download_attachment(event)
        )

        if delta:
            for message in delta.get("updated_messages", []):
                events.append(await self._edited_message_event_info(message))

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
                "new_text": delta["text"] if "text" in delta else "",
                "timestamp": delta["timestamp"],
                "attachments": delta["attachments"] if "attachments" in delta else []
            }
        }

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

    async def _handle_reaction(self, event: Any) -> List[Dict[str, Any]]:
        """Handle chat action events like user joins, leaves, or group migrations

        Args:
            event: Zulip event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation("reaction", event)

            if delta:
                for reaction in delta.get("added_reactions", []):
                    events.append(
                        await self._reaction_update_event_info("reaction_added", delta, reaction)
                    )
                for reaction in delta.get("removed_reactions", []):
                    events.append(
                        await self._reaction_update_event_info("reaction_removed", delta, reaction)
                    )

                conversation_id = delta["conversation_id"]
                text = "response w/out attachment"

                if self._is_conversation_private(conversation_id):
                    message_type = "private"
                    to_field = self._get_private_to_field(conversation_id)
                    subject = None
                else:
                    message_type = "stream"
                    stream_details = conversation_id.split("/")
                    to_field = self._get_stream_to_field(stream_details[0])
                    subject = stream_details[1]


                self.client.send_message({
                    "type": message_type,
                    "to": to_field,
                    "content": text,
                    "subject": subject
                })


        except Exception as e:
            logging.error(f"Error handling reaction event: {e}", exc_info=True)

        return events

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

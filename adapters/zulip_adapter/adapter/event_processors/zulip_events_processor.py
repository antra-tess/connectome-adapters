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
                 conversation_manager: ConversationManager,
                 adapter_name: str):
        """Initialize the Zulip events processor

        Args:
            config: Config instance
            client: Zulip client instance
            conversation_manager: Conversation manager for tracking message history
            adapter_name: Name of the adapter (typically bot username)
        """
        self.config = config
        self.client = client
        self.conversation_manager = conversation_manager
        self.adapter_name = adapter_name
        self.adapter_type = self.config.get_setting("adapter", "type")
        self.downloader = Downloader(self.config)

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
                event.get("message", None), None
            )

            if delta:
                if "conversation_started" in delta["updates"]:
                    history = await self._fetch_conversation_history()
                    events.append(await self._conversation_started_event_info(delta, history))
                if "message_received" in delta["updates"]:
                    events.append(await self._new_message_event_info(delta))
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

    async def _handle_update_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle an update message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation(
                "update_message", event
            )

            if delta and "message_edited" in delta["updates"]:
                events.append(await self._edited_message_event_info(delta))
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
                if "reaction_added" in delta["updates"]:
                    for reaction in delta["added_reactions"]:
                        events.append(
                            await self._reaction_update_event_info("reaction_added", delta, reaction)
                        )

                if "reaction_removed" in delta["updates"]:
                    for reaction in delta["removed_reactions"]:
                        events.append(
                            await self._reaction_update_event_info("reaction_removed", delta, reaction)
                        )
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

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

import asyncio
import discord
import logging

from enum import Enum
from typing import Any, Callable, Dict, List, Union

from adapters.slack_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.slack_adapter.adapter.conversation.manager import Manager
from adapters.slack_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.utils.config import Config
from core.event_processors.base_incoming_event_processor import BaseIncomingEventProcessor

class SlackIncomingEventType(str, Enum):
    """Event types supported by the SlackIncomingEventProcessor"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    ADDED_REACTION = "added_reaction"
    REMOVED_REACTION = "removed_reaction"

class IncomingEventProcessor(BaseIncomingEventProcessor):
    """Slack events processor"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the Slack incoming event processor

        Args:
            config: Config instance
            client: Slack client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.downloader = Downloader(self.config)

    def _get_event_handlers(self) -> Dict[str, Callable]:
        """Get event handlers for incoming events

        Returns:
            Dictionary of event handlers
        """
        return {
            SlackIncomingEventType.NEW_MESSAGE: self._handle_message,
            SlackIncomingEventType.EDITED_MESSAGE: self._handle_edited_message,
            SlackIncomingEventType.DELETED_MESSAGE: self._handle_deleted_message,
            SlackIncomingEventType.ADDED_REACTION: self._handle_reaction,
            SlackIncomingEventType.REMOVED_REACTION: self._handle_reaction
        }

    async def _handle_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a new message event from Slack

        Args:
            event: Discord event object

        Returns:
            List of events to emit
        """
        event = event.get("event", None)
        events = []

        try:
            delta = await self.conversation_manager.add_to_conversation({
                "message": event,
                "attachments": await self.downloader.download_attachment(event)
            })

            if delta:
                if delta.get("fetch_history", False):
                    history = await self._fetch_conversation_history(delta)
                    events.append(await self._conversation_started_event_info(delta, history))

                for message in delta.get("added_messages", []):
                    events.append(await self._new_message_event_info(message))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

    async def _fetch_conversation_history(self, delta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Args:
            delta: Event change information containing conversation ID

        Returns:
            List of formatted message history
        """
        try:
            return await HistoryFetcher(
                self.config,
                self.client,
                self.conversation_manager,
                delta["conversation_id"],
                anchor="newest"
            ).fetch()
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _handle_edited_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle an edited message event from Slack

        Args:
            event: Slack event object

        Returns:
            List of events to emit
        """
        try:
            events = []
            delta = await self.conversation_manager.update_conversation({
                "event_type": "edited_message",
                "message": event["event"]
            })

            if delta:
                for message in delta.get("updated_messages", []):
                    events.append(await self._edited_message_event_info(message))
                for message_id in delta.get("pinned_message_ids", []):
                    events.append(
                        await self._pinned_status_change_event_info(
                            "message_pinned",
                            {
                                "message_id": message_id,
                                "conversation_id": delta["conversation_id"]
                            }
                        )
                    )
                for message_id in delta.get("unpinned_message_ids", []):
                    events.append(
                        await self._pinned_status_change_event_info(
                            "message_unpinned",
                            {
                                "message_id": message_id,
                                "conversation_id": delta["conversation_id"]
                            }
                        )
                    )

            return events
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return []

    async def _handle_deleted_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a deleted message event from Slack

        Args:
            event: Slack event object

        Returns:
            List of events to emit
        """
        try:
            events = []
            delta = await self.conversation_manager.delete_from_conversation(
                incoming_event=event["event"]
            )

            if delta:
                for message_id in delta.get("deleted_message_ids", []):
                    events.append(
                        await self._deleted_message_event_info(
                            message_id, delta["conversation_id"]
                        )
                    )

            return events
        except Exception as e:
            logging.error(f"Error handling deleted message: {e}", exc_info=True)

        return []

    async def _handle_reaction(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle chat action events like user joins, leaves, or group migrations

        Args:
            event: Slack event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation({
                "event_type": event["type"],
                "message": event["event"]
            })

            if delta:
                for reaction in delta.get("added_reactions", []):
                    events.append(
                        await self._reaction_update_event_info("reaction_added", delta, reaction)
                    )
                for reaction in delta.get("removed_reactions", []):
                    events.append(
                        await self._reaction_update_event_info("reaction_removed", delta, reaction)
                    )
        except Exception as e:
            logging.error(f"Error handling reaction event: {e}", exc_info=True)

        return events

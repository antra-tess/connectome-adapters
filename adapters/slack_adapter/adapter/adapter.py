import asyncio
import logging

from typing import Any, Optional

from adapters.slack_adapter.adapter.conversation.manager import Manager
from adapters.slack_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from adapters.slack_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.slack_adapter.adapter.slack_client import SlackClient

from core.adapter.base_adapter import BaseAdapter
from core.utils.config import Config

class Adapter(BaseAdapter):
    """Slack adapter implementation using Slack"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "v1"     # Slack API version we have tested with

    def __init__(self, config: Config, socketio_server, start_maintenance=False):
        """Initialize the Slack adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, socketio_server, start_maintenance)
        self.conversation_manager = Manager(config, start_maintenance)

    async def _setup_client(self) -> None:
        """Connect to client"""
        self.client = SlackClient(self.config, self.process_incoming_event)
        self.connected = await self.client.connect()

    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        adapter_info = self.client.bot.user
        self.config.add_setting(
            "adapter", "adapter_id", str(getattr(adapter_info, "id", ""))
        )
        self.config.add_setting(
            "adapter", "adapter_name", str(getattr(adapter_info, "name", ""))
        )

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Slack")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        #logging.info(f"Slack library version: {slack.__version__}")

    def _setup_processors(self) -> None:
        """Setup processors"""
        self.incoming_events_processor = IncomingEventProcessor(
            self.config,
            self.client.bot,
            self.conversation_manager
        )
        self.outgoing_events_processor = OutgoingEventProcessor(
            self.config,
            self.client.bot,
            self.conversation_manager
        )

    async def _perform_post_setup_tasks(self) -> None:
        """Perform post setup tasks"""
        pass

    async def _connection_exists(self) -> Optional[Any]:
        """Check connection

        Returns:
            Object: User object if connection exists, None otherwise
        """
        return await self.client.bot.fetch_user(
            self.config.get_setting("adapter", "adapter_id")
        )

    async def _teardown_client(self) -> None:
        """Teardown client"""
        if self.client:
            await self.client.disconnect()

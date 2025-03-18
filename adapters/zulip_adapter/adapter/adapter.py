import asyncio
import json
import logging
import os

from typing import Any

from adapters.zulip_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from adapters.zulip_adapter.adapter.event_processors.zulip_events_processor import ZulipEventsProcessor
from adapters.zulip_adapter.adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

from core.utils.config import Config

class ZulipAdapter:
    """Zulip ZulipAdapter implementation using Zulip"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "8.3"    # Zulip API version we've tested with

    def __init__(self, config: Config, socketio_server, start_maintenance=False):
        """Initialize the Zulip adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
            start_maintenance: Whether to start the maintenance loop
        """
        self.socketio_server = socketio_server
        self.config = config
        self.adapter_type = config.get_setting("adapter", "type")
        self.conversation_manager = ConversationManager(config, start_maintenance)
        self.zulip_client = None
        self.running = False
        self.initialized = False
        self.adapter_name = None
        self.zulip_events_processor = None
        self.monitoring_task = None

    async def start(self) -> None:
        """Start the adapter"""
        logging.info("Starting Zulip adapter...")

        self.running = True

        try:
            #self.zulip_client = ZulipClient(
            #    config=self.config, event_callback=self.process_zulip_event
            #)
            #connected = await self.zulip_client.connect()

            if False: #connected:
                self.initialized = True

                await self._get_adapter_info()
                self._print_api_compatibility()

                self.zulip_events_processor = ZulipEventsProcessor(
                    self.config,
                    self.zulip_client.client,
                    self.conversation_manager,
                    self.adapter_name,
                    self.adapter_type
                )
                self.socket_io_events_processor = SocketIoEventsProcessor(
                    self.config,
                    self.zulip_client.client,
                    self.conversation_manager
                )
                self.monitoring_task = asyncio.create_task(self._monitor_connection())

                await self.socketio_server.emit_event(
                    "connect", {"adapter_type": self.adapter_type}
                )
                logging.info("Zulip adapter started successfully")
                return
        except Exception as e:
            logging.error(f"Error starting adapter: {e}", exc_info=True)
            await self.socketio_server.emit_event(
                "disconnect", {"adapter_type": self.adapter_type}
            )

        self.running = False

    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        adapter_info = None
        self.adapter_name = getattr(adapter_info, "username", None)

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Zulip")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        #logging.info(f"Zulip library version: {zulip.__version__}")

    async def _monitor_connection(self) -> None:
        """Monitor connection to Zulip"""
        check_interval = self.config.get_setting("adapter", "connection_check_interval")
        retry_delay = self.config.get_setting("adapter", "retry_delay")

        while self.running:
            try:
                await asyncio.sleep(check_interval)
                if not self.initialized or not self.running:
                    continue

                me = None
                if not me:
                    raise RuntimeError("Connection check failed - could not get user info")

                await self.socketio_server.emit_event(
                    "connect", {"adapter_type": self.adapter_type}
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in connection monitor: {e}")
                await self.socketio_server.emit_event(
                    "disconnect", {"adapter_type": self.adapter_type}
                )
                await asyncio.sleep(retry_delay)

    async def stop(self) -> None:
        """Stop the adapter"""
        if not self.running:
            return

        self.running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()

        try:
            logging.info("Disconnected from Zulip")
        except Exception as e:
            logging.error(f"Error disconnecting from Zulip: {e}")

        logging.info("Adapter stopped")
        await self.socketio_server.emit_event(
            "disconnect", {"adapter_type": self.adapter_type}
        )

    async def process_zulip_event(self, event_type: str, event: Any) -> None:
        """Process events from Zulip client

        Args:
            event_type: event type (new_message, edited_message, deleted_message, chat_action)
            event: Zulip event object
        """
        for event_info in await self.zulip_events_processor.process_event(event_type, event):
            await self.socketio_server.emit_event("bot_request", event_info)

    async def process_socket_io_event(self, event_type: str, data: Any) -> bool:
        """Process events from socket_io.client

        Args:
            event_type: event type (send_message, edit_message, delete_message, add_reaction, remove_reaction)
            data: data for event

        Returns:
            bool: True if event was processed successfully, False otherwise
        """
        if not self.zulip_client:
            logging.error("Not connected to Zulip")
            return False

        return await self.socket_io_events_processor.process_event(event_type, data)

import asyncio
import json
import logging
import os
import telethon

from typing import Any

from config import Config
from adapter.conversation_manager.conversation_manager import ConversationManager
from adapter.telethon_client import TelethonClient
from adapter.event_processors.telegram_events_processor import TelegramEventsProcessor
from adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

class TelegramAdapter:
    """Telegram TelegramAdapter implementation using Telethon"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "8.3"    # Telegram API version we've tested with

    def __init__(self, socketio_server, start_maintenance=False):
        """Initialize the Telegram adapter

        Args:
            socketio_server: socket_io.server for event broadcasting
        """
        self.socketio_server = socketio_server
        self.config = Config.get_instance()
        self.conversation_manager = ConversationManager(start_maintenance)
        self.telethon_client = None
        self.running = False
        self.initialized = False
        self.adapter_name = None
        self.telegram_events_processor = None
        self.monitoring_task = None

    async def start(self) -> None:
        """Start the adapter"""
        logging.info("Starting Telegram adapter...")

        self.running = True

        try:
            self.telethon_client = TelethonClient(self.process_telegram_event)
            connected = await self.telethon_client.connect()

            if connected:
                self.initialized = True

                await self._get_adapter_info()
                self._print_api_compatibility()

                self.telegram_events_processor = TelegramEventsProcessor(
                    self.telethon_client.client, self.conversation_manager, self.adapter_name
                )
                self.socket_io_events_processor = SocketIoEventsProcessor(
                    self.telethon_client.client, self.conversation_manager
                )
                self.monitoring_task = asyncio.create_task(self._monitor_connection())

                await self.socketio_server.emit_event(
                    "connect", {"adapter_type": self.config.get_setting("adapter", "type")}
                )
                logging.info("Telegram adapter started successfully")
                return
        except Exception as e:
            logging.error(f"Error starting adapter: {e}", exc_info=True)
            await self.socketio_server.emit_event(
                "disconnect", {"adapter_type": self.config.get_setting("adapter", "type")}
            )

        self.running = False

    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        adapter_info = await self.telethon_client.client.get_me()
        self.adapter_name = getattr(adapter_info, "username", None)

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Telegram")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        logging.info(f"Telethon library version: {telethon.__version__}")

    async def _monitor_connection(self) -> None:
        """Monitor connection to Telegram"""
        check_interval = self.config.get_setting("adapter", "connection_check_interval")
        retry_delay = self.config.get_setting("adapter", "retry_delay")

        while self.running:
            try:
                await asyncio.sleep(check_interval)
                if not self.initialized or not self.running:
                    continue

                me = await self.telethon_client.client.get_me()
                if not me:
                    raise RuntimeError("Connection check failed - could not get user info")

                await self.socketio_server.emit_event(
                    "connect", {"adapter_type": self.config.get_setting("adapter", "type")}
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in connection monitor: {e}")
                await self.socketio_server.emit_event(
                    "disconnect", {"adapter_type": self.config.get_setting("adapter", "type")}
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
            await self.telethon_client.disconnect()
            logging.info("Disconnected from Telegram")
        except Exception as e:
            logging.error(f"Error disconnecting from Telegram: {e}")

        logging.info("Adapter stopped")
        await self.socketio_server.emit_event(
            "disconnect", {"adapter_type": self.config.get_setting("adapter", "type")}
        )

    async def process_telegram_event(self, event_type: str, event: Any) -> None:
        """Process events from Telethon client

        Args:
            event_type: event type (new_message, edited_message, deleted_message, chat_action)
            event: Telethon event object
        """
        for event_info in await self.telegram_events_processor.process_event(event_type, event):
            await self.socketio_server.emit_event("bot_request", event_info)

    async def process_socket_io_event(self, event_type: str, data: Any) -> bool:
        """Process events from socket_io.client

        Args:
            event_type: event type (send_message, edit_message, delete_message, add_reaction, remove_reaction)
            data: data for event

        Returns:
            bool: True if event was processed successfully, False otherwise
        """
        if not self.telethon_client:
            logging.error("Not connected to Telegram")
            return False

        return await self.socket_io_events_processor.process_event(event_type, data)

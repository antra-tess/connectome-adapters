import asyncio
import logging
import time

from typing import Optional
from telethon import TelegramClient, events
from telethon.sessions import MemorySession

from config import Config

class TelethonClient:
    """Handles Telegram connection using Telethon"""

    def __init__(self, event_callback=None):
        """Initialize the Telethon client

        Args:
            config: The application configuration
            event_callback: Optional callback for processing events
        """
        self.config = Config().get_instance()
        self.event_callback = event_callback
        self.client: Optional[TelegramClient] = None
        self.connected = False
        self.me = None

        self.api_id = self.config.get_setting("adapter", "api_id")
        self.api_hash = self.config.get_setting("adapter", "api_hash")
        self.bot_token = self.config.get_setting("adapter", "bot_token")
        self.phone = self.config.get_setting("adapter", "phone")

        self.connection_retries = self.config.get_setting("adapter", "connection_retries")
        self.retry_delay = self.config.get_setting("adapter", "retry_delay")
        self.flood_sleep_threshold = self.config.get_setting("adapter", "flood_sleep_threshold")

        if not self.api_id or not self.api_hash:
            raise ValueError("Telegram API ID and hash are required in configuration")

    async def connect(self) -> bool:
        """Connect to Telegram and set up event handlers

        Returns:
            bool: True if connection was successful, False otherwise
        """
        self.client = TelegramClient(
            MemorySession(),
            self.api_id,
            self.api_hash
        )

        await self.client.connect()

        if not await self.client.is_user_authorized():
            if self.bot_token:
                logging.info("Signing in with bot token")
                await self.client.sign_in(bot_token=self.bot_token)
            elif self.phone:
                await self.client.send_code_request(self.phone)
                code = input("Enter the code you received: ")
                await self.client.sign_in(self.phone, code)
            else:
                raise ValueError("Neither bot token nor phone number provided for authentication")

        self.me = await self.client.get_me()
        self.connected = True
        logging.info(f"Connected to Telegram as {self.me.username or self.me.first_name}")

        self._setup_event_handlers()

        return self.connected

    def _setup_event_handlers(self) -> None:
        """Set up comprehensive event handlers for Telegram events"""
        logging.info("Setting up Telethon event handlers")

        @self.client.on(events.NewMessage())
        async def on_new_message(event):
            if self.event_callback:
                await self.event_callback("new_message", event)

        @self.client.on(events.MessageEdited())
        async def on_edited_message(event):
            if self.event_callback:
                await self.event_callback("edited_message", event)

        @self.client.on(events.MessageDeleted())
        async def on_deleted_message(event):
            if self.event_callback:
                await self.event_callback("deleted_message", event)

        @self.client.on(events.ChatAction())
        async def on_chat_action(event):
            if self.event_callback:
                await self.event_callback("chat_action", event)

    async def disconnect(self) -> None:
        """Disconnect from Telegram"""
        if self.client:
            await self.client.disconnect()
            self.connected = False

        logging.info("Disconnected from Telegram")

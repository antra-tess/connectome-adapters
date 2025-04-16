import asyncio
import logging

from typing import Callable, Optional

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class SlackClient:
    """Slack client implementation"""

    def __init__(self, config: Config, process_event: Callable):
        """Initialize the Slack client

        Args:
            config (Config): The configuration for the Slack client
            process_event (Callable): The function to process events
        """
        self.config = config
        self.process_event = process_event
        self.rate_limiter = RateLimiter.get_instance(self.config)

        self.running = False
        self._connection_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Connect to Slack"""
        try:
            self._connection_task = asyncio.create_task(
                self.bot.start(self.config.get_setting("adapter", "bot_token"))
            )
            await asyncio.sleep(1)

            if self._connection_task.done():
                raise Exception(self._connection_task.exception())

            logging.info("Discord connection initiated successfully")
            return True
        except Exception as e:
            logging.error(f"Error initiating Discord connection: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Discord"""
        self.running = False

        try:
            await self.bot.close()

            if self._connection_task and not self._connection_task.done():
                self._connection_task.cancel()
                try:
                    await self._connection_task
                except asyncio.CancelledError:
                    pass  # Expected

            logging.info("Disconnected from Discord")
        except Exception as e:
            logging.error(f"Error disconnecting from Discord: {e}")

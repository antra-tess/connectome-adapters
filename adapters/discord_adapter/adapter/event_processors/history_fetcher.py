import asyncio
import discord
import logging

from typing import Any, Dict, List, Optional

from adapters.discord_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.event_processors.discord_utils import (
    get_discord_channel, is_discord_service_message
)

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class HistoryFetcher:
    """Fetches and formats history from Discord"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 downloader: Downloader,
                 conversation: ConversationInfo):
        """Initialize the DiscordHistoryFetcher

        Args:
            config: Config instance
            client: Discord client
            downloader: Downloader instance
            conversation: ConversationInfo instance
        """
        self.config = config
        self.client = client
        self.downloader = downloader
        self.conversation = conversation
        self.rate_limiter = RateLimiter.get_instance(self.config)
        self.history_limit = self.config.get_setting("adapter", "max_history_limit")

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch history from Discord

        Returns:
            List of formatted message history
        """
        return await self._parse_fetched_history(
            await (await self._get_channel()).history(**{"limit": self.history_limit})
        )

    async def _get_channel(self) -> Optional[Any]:
        """Get a Discord channel object

        Args:
            channel_id: Channel ID to fetch

        Returns:
            Discord channel object or None if not found
        """
        await self.rate_limiter.limit_request("fetch_channel")

        return await get_discord_channel(
            self.client, self.conversation.conversation_id
        )

    async def _parse_fetched_history(self, history: Any) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: List of message history

        Returns:
            List of formatted message history
        """
        formatted_history = []
        download_tasks = []
        message_map = {}  # To associate download tasks with messages

        for i, message in enumerate(history):
            if is_discord_service_message(message):
                continue

            thread_id = None
            if message.reference and message.reference.message_id:
               thread_id = str(message.reference.message_id)

            formatted_history.append({
                "message_id": str(message.id),
                "conversation_id": self.conversation.conversation_id,
                "sender": {
                    "user_id": str(message.author.id),
                    "display_name": message.author.display_name or message.author.name
                },
                "text": message.content,
                "thread_id": thread_id,
                "timestamp": int(message.created_at.timestamp() * 1e3),
                "attachments": []
            })

            if message.attachments:
                task = self.downloader.download_attachment(message)
                download_tasks.append(task)
                message_map[task] = i

        if download_tasks:
            for task, result in zip(
                download_tasks,
                await asyncio.gather(*download_tasks, return_exceptions=True)
            ):
                if isinstance(result, Exception):
                    logging.error(f"Error downloading attachment: {result}")
                    continue

                formatted_history[message_map[task]]["attachments"] = result

        formatted_history.sort(key=lambda msg: msg.get("timestamp", 0))
        return formatted_history

import json
import logging
import re

from typing import Any, Dict, List
from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.attachment_loaders.downloader import Downloader
from core.utils.config import Config

class HistoryFetcher:
    """Fetches and formats history from Discord"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 downloader: Downloader,
                 conversation: ConversationInfo,
                 anchor: str):
        """Initialize the DiscordHistoryFetcher

        Args:
            config: Config instance
            client: Discord client
            downloader: Downloader instance
            conversation: ConversationInfo instance
            anchor: Anchor message ID
        """
        self.config = config
        self.client = client
        self.downloader = downloader
        self.conversation = conversation
        self.anchor = anchor
        self.history_limit = self.config.get_setting("adapter", "max_history_limit")

    async def fetch(self) -> List[Dict[str, Any]]:
            return []

    async def _parse_fetched_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: List of message history

        Returns:
            List of formatted message history
        """
        formatted_history = []

        for msg in history:
            attachments = []
            for attachment in await self.downloader.download_attachment(msg):
                attachments.append({
                    "attachment_id": attachment.get("attachment_id"),
                    "attachment_type": attachment.get("attachment_type"),
                    "file_extension": attachment.get("file_extension"),
                    "file_path": attachment.get("file_path"),
                    "size": attachment.get("size"),
                })

            formatted_history.append({
                "message_id": str(msg.get("id", "")),
                "conversation_id": self.conversation.conversation_id,
                "sender": {
                    "user_id": str(msg.get("sender_id", "")),
                    "display_name": msg.get("sender_full_name", "")
                },
                "text": msg.get("content", ""),
                "thread_id": self._extract_reply_to_id(msg.get("content", "")),
                "timestamp": msg.get("timestamp", None),
                "attachments": attachments
            })

        formatted_history.sort(key=lambda msg: msg.get("timestamp", 0))
        return formatted_history

import json
import logging
import re

from typing import Any, Dict, List
from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.attachment_loaders.downloader import Downloader

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class HistoryFetcher:
    """Fetches and formats history from Zulip"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 downloader: Downloader,
                 conversation: ConversationInfo,
                 anchor: str):
        """Initialize the ZulipHistoryFetcher

        Args:
            config: Config instance
            client: Zulip client
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
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Returns:
            List of formatted message history
        """
        if not self.conversation or not self.anchor:
            return []

        try:
            await self.rate_limiter.limit_request("get_messages", self.conversation.conversation_id)

            result = self.client.get_messages({
                "narrow": json.dumps(self._get_narrow_for_conversation()),
                "anchor": self.anchor,
                "num_before": self.history_limit,
                "num_after": 0,  # No messages after anchor
                "include_anchor": False,  # Exclude anchor since we already have it
                "apply_markdown": False  # Get raw message content
            })

            if result.get("result", None) != "success":
                return []

            return await self._parse_fetched_history(result.get("messages", []))
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    def _get_narrow_for_conversation(self) -> List[Dict[str, Any]]:
        """Get the narrow parameter for a conversation

        Returns:
            Narrow parameter for API call or empty list if info is not found
        """
        if self.conversation.conversation_type == "private":
            emails = self.conversation.to_fields()
            if emails:
                return [{"operator": "pm-with", "operand": ",".join(emails)}]
            return []

        return [
            {"operator": "stream", "operand": self.conversation.conversation_name},
            {"operator": "topic", "operand": self.conversation.conversation_id.split("/", 1)[1]}
        ]

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

    def _extract_reply_to_id(self, content: str) -> str:
        """Get the reply to ID from a message

        Args:
            content: The message to extract the reply to ID from

        Returns:
            The reply to ID from the message
        """
        pattern = r'\[said\]\([^\)]+/near/(\d+)\)'
        match = re.search(pattern, content)

        if match:
            return match.group(1)

        return None

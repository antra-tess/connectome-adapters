"""Telegram adapter implementation."""

from adapter.adapter import TelegramAdapter
from adapter.telethon_client import TelethonClient
from adapter.conversation_manager import ConversationManager, ConversationInfo, ThreadInfo

__all__ = [
    "TelegramAdapter",
    "TelethonClient",
    "ConversationManager",
    "ConversationInfo",
    "ThreadInfo"
]

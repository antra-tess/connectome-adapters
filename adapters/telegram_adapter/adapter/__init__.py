"""Telegram adapter implementation."""

from adapters.telegram_adapter.adapter.adapter import TelegramAdapter
from adapters.telegram_adapter.adapter.telethon_client import TelethonClient
from adapters.telegram_adapter.adapter.conversation_manager import ConversationManager, ConversationInfo, ThreadInfo

__all__ = [
    "TelegramAdapter",
    "TelethonClient",
    "ConversationManager",
    "ConversationInfo",
    "ThreadInfo"
]

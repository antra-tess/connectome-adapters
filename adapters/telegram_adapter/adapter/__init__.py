"""Telegram adapter implementation."""

from adapters.telegram_adapter.adapter.adapter import TelegramAdapter
from adapters.telegram_adapter.adapter.telethon_client import TelethonClient

__all__ = [
    "TelegramAdapter",
    "TelethonClient"
]

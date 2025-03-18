"""Adapter event handlers implementation."""

from adapters.telegram_adapter.adapter.event_processors.telegram_events_processor import TelegramEventsProcessor    
from adapters.telegram_adapter.adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

__all__ = [
    "TelegramEventsProcessor",
    "SocketIoEventsProcessor"
]

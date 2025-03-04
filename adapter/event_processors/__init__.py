"""Adapter event handlers implementation."""

from adapter.event_processors.telegram_events_processor import TelegramEventsProcessor    
from adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

__all__ = [
    "TelegramEventsProcessor",
    "SocketIoEventsProcessor"
]

"""Telegram loaders implementation."""

from adapter.attachment_loaders.base_loader import BaseLoader
from adapter.attachment_loaders.uploader import Uploader
from adapter.attachment_loaders.downloader import Downloader

__all__ = [
    "BaseLoader",
    "Uploader",
    "Downloader"
]

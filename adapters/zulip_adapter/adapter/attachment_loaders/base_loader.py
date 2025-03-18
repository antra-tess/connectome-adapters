import json
import logging
import os

from typing import Optional, Dict, Any
from datetime import datetime

from core.utils.config import Config

class BaseLoader:
    """Basic attachment loader"""
    EXTENSION_TYPE_MAPPING = {}

    def __init__(self, config: Config):
        """Constructor

        Args:
            config: Config instance
        """
        self.config = config
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.large_file_threshold = self.config.get_setting(
            "attachments", "large_file_threshold_mb"
        ) * 1024 * 1024  # Convert to bytes
        self.max_file_size = self.config.get_setting(
            "attachments", "max_file_size_mb"
        ) * 1024 * 1024  # Convert to bytes

    async def _get_attachment_metadata(self) -> Dict[str, Any]:
        """Determine attachment metadata

        Returns: Dictionary with attachment metadata or {} if no attachment
        """
        return {}

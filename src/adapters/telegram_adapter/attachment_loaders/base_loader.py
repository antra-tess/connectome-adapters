import os

from typing import Optional, Dict, Any
from datetime import datetime
from src.core.utils.attachment_loading import get_attachment_type_by_extension
from src.core.utils.config import Config

class BaseLoader:
    """Basic attachment loader"""
    def __init__(self, config: Config, client):
        """Initialize with a Telethon client

        Args:
            config: Config instance
            client: Telethon client instance
        """
        self.client = client
        self.config = config
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.max_file_size = self.config.get_setting(
            "attachments", "max_file_size_mb"
        ) * 1024 * 1024  # Convert to bytes

    async def _get_attachment_metadata(self, message: Any) -> Dict[str, Any]:
        """Determine attachment type, ID, and file extension from a message

        Args:
            message: Telethon message object

        Returns: Dictionary with attachment metadata or {} if no attachment
        """
        if not message or not hasattr(message, "media") or not message.media:
            return {}

        metadata = {
            "attachment_id": None,
            "attachment_type": None,
            "filename": None,
            "size": int(self._get_file_size(message)),
            "content_type": None,
            "content": None,
            "url": None,
            "created_at": datetime.now(),
            "processable": False
        }

        if hasattr(message, "photo") and message.photo:
            metadata["attachment_type"] = "photo"
            metadata["attachment_id"] = str(message.photo.id)
            metadata["filename"] = f"{metadata['attachment_id']}.jpg"
        elif hasattr(message, "document") and message.document:
            document = message.document
            file_extension = None

            if hasattr(document, "attributes"):
                for attr in document.attributes:
                    if hasattr(attr, "file_name") and attr.file_name and "." in attr.file_name:
                        file_extension = attr.file_name.split(".")[-1].lower()
                        break

            metadata["attachment_type"] = get_attachment_type_by_extension(file_extension)
            metadata["attachment_id"] = str(document.id)
            metadata["filename"] = f"{metadata['attachment_id']}"

            if file_extension:
                metadata["filename"] += f".{file_extension}"

        return metadata

    def _get_file_size(self, message: Any) -> Optional[int]:
        """Get file size from message if available

        Args:
            message: Telethon message object

        Returns: File size in bytes or None if not available
        """
        try:
            if hasattr(message, "document") and message.document:
                return message.document.size
            if hasattr(message, "photo") and message.photo:
                sizes = message.photo.sizes
                if sizes:
                    largest = max(sizes, key=lambda s: getattr(s, "size", 0) if hasattr(s, "size") else 0)
                    return getattr(largest, "size", None)
            return None
        except Exception:
            return None

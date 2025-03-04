import json
import logging
import os

from typing import Optional, Dict, Any
from datetime import datetime

from config import Config



class BaseLoader:
    """Basic attachment loader"""
    EXTENSION_TYPE_MAPPING = {
        "image": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif", "svg", "heic", "heif"],
        "video": ["mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "3gp", "m4v", "mpeg", "mpg", "ts"],
        "audio": ["mp3", "wav", "ogg", "flac", "m4a", "aac", "wma", "opus", "aiff"],
        "document": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "txt", "rtf", "csv"],
        "archive": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"],
        "code": ["py", "js", "html", "css", "java", "c", "cpp", "h", "php", "rb", "json", "xml", "sql", "sh", "bat"],
        "ebook": ["epub", "mobi", "azw", "azw3", "fb2"],
        "font": ["ttf", "otf", "woff", "woff2", "eot"],
        "3d_model": ["obj", "stl", "fbx", "3ds", "blend"],
        "executable": ["exe", "dll", "app", "msi", "apk", "deb", "rpm"],
        "sticker": ["tgs"]
    }

    def __init__(self, client):
        """Initialize with a Telethon client"""
        self.client = client
        self.config = Config().get_instance()
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.large_file_threshold = self.config.get_setting(
            "attachments", "large_file_threshold_mb"
        ) * 1024 * 1024  # Convert to bytes
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
            "attachment_type": None,
            "attachment_id": None,
            "file_extension": None,
            "created_at": datetime.now(),
            "size": self._get_file_size(message)
        }

        if hasattr(message, "photo") and message.photo:
            metadata["attachment_type"] = "photo"
            metadata["attachment_id"] = str(message.photo.id)
            metadata["file_extension"] = "jpg"
        elif hasattr(message, "document") and message.document:
            document = message.document
            file_extension = None

            if hasattr(document, "attributes"):
                for attr in document.attributes:
                    if hasattr(attr, "file_name") and attr.file_name and "." in attr.file_name:
                        file_extension = attr.file_name.split(".")[-1].lower()
                        break

            metadata["attachment_type"] = self._get_attachment_type_by_extension(file_extension)
            metadata["attachment_id"] = str(document.id)
            metadata["file_extension"] = file_extension

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

    def _get_attachment_type_by_extension(self, file_extension: Optional[str]) -> str:
        """Determine the specific attachment type based on file extension

        Args:
            file_extension: File extension (without the dot), can be None

        Returns:
            Specific attachment type category
        """
        if not file_extension:
            return "document"

        for type_name, extensions in self.EXTENSION_TYPE_MAPPING.items():
            if file_extension.lower() in extensions:
                return type_name

        return "document"

    def _create_attachment_dir(self, attachment_type: str, attachment_id: str) -> str:
        """Create a directory for an attachment

        Args:
            attachment_type: Type of attachment
            attachment_id: ID of attachment

        Returns: Path to the attachment directory
        """
        attachment_dir = os.path.join(
            self.download_dir, f"{attachment_type}", str(attachment_id)
        )

        try:
            os.makedirs(attachment_dir, exist_ok=True)
            return attachment_dir
        except Exception as e:
            logging.error(f"Error creating attachment directory: {e}")
            return None

    def _create_metadata_file(self, metadata: Dict[str, Any], attachment_dir: str) -> None:
        """Store metadata in a JSON file

        Args:
            metadata: Metadata dictionary
            attachment_dir: Path to the attachment directory
        """
        metadata_path = os.path.join(
            attachment_dir, f"{metadata['attachment_id']}.json"
        )
        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Error saving attachment metadata: {e}")

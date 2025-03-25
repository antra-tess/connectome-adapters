import json
import logging
import os
import aiohttp
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from urllib.parse import urlparse

from core.utils.config import Config

class BaseLoader:
    """Basic attachment loader for Zulip"""
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

    def __init__(self, config: Config, client: Any):
        """Initialize with a Zulip client

        Args:
            config: Config instance
            client: Zulip client instance
        """
        self.config = config
        self.client = client
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.large_file_threshold = self.config.get_setting(
            "attachments", "large_file_threshold_mb"
        ) * 1024 * 1024  # Convert to bytes
        self.max_file_size = self.config.get_setting(
            "attachments", "max_file_size_mb"
        ) * 1024 * 1024  # Convert to bytes
        self.zulip_site = self.config.get_setting("adapter", "site", "").rstrip("/")

    def _generate_attachment_id(self, file_path: str) -> str:
        """Generate a unique ID for an attachment based on its path
        
        Args:
            file_path: The file path from the Zulip message
            
        Returns:
            A unique identifier for the attachment
        """
        path_parts = file_path.split("/")
        if len(path_parts) >= 5:
            return path_parts[-2]
        return hashlib.md5(file_path.encode()).hexdigest()

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

    def _create_attachment_dir(self, attachment_dir: str) -> None:
        """Create a directory for an attachment

        Args:
            attachment_dir: Path to the attachment directory
        """
        try:
            os.makedirs(attachment_dir, exist_ok=True)
        except Exception as e:
            logging.error(f"Error creating attachment directory: {e}")

    def _create_metadata_file(self, metadata: Dict[str, Any], attachment_dir: str) -> None:
        """Store metadata in a JSON file

        Args:
            metadata: Metadata dictionary
            attachment_dir: Path to the attachment directory
        """
        try:
            metadata_path = os.path.join(
                attachment_dir, f"{metadata['attachment_id']}.json"
            )
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Error saving attachment metadata: {e}")

    def _get_api_key(self) -> str:
        """Get the API key from the client or config
        
        Returns:
            API key string
        """
        if hasattr(self.client, "api_key"):
            return self.client.api_key
        return self.config.get_setting("adapter", "api_key", "")

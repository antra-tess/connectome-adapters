import logging
import os

from typing import Any, Dict, List
from core.utils.attachment_loading import delete_empty_directory
from core.utils.config import Config

class Uploader():
    """Prepares files for upload to Slack"""

    def __init__(self, config: Config):
        """Initialize with a Slack client

        Args:
            config: Config instance
        """
        self.config = config
        self.max_file_size = self.config.get_setting(
            "attachments", "max_file_size_mb"
        ) * 1024 * 1024  # Convert to bytes

    def upload_attachment(self, attachments: List[Dict[str, Any]]) -> List[str]:
        """Upload a file to Slack

        Args:
            attachments: List of attachment details (json)

        Returns:
            List of slack.File objects or [] if error
        """
        files = []

        try:
            for attachment in attachments:
                if not os.path.exists(attachment["file_path"]):
                    logging.error(f"File not found: {attachment['file_path']}")
                    continue

                if attachment["size"] > self.max_file_size:
                    logging.error(f"File exceeds Slack's size limit: {attachment['size']/1024/1024:.2f} MB "
                                f"(max {self.max_file_size/1024/1024:.2f} MB)")
                    continue

                #files.append(slack.File(attachment["file_path"]))

            return files
        except Exception as e:
            logging.error(f"Error uploading file: {str(e)}", exc_info=True)
            return []

    def clean_up_uploaded_files(self, attachments: List[Dict[str, Any]]) -> None:
        """Clean up files after they have been uploaded to Slack

        Args:
            attachments: List of attachment details (json)
        """
        for attachment in attachments:
            os.remove(attachment["file_path"])
            delete_empty_directory(attachment["file_path"])

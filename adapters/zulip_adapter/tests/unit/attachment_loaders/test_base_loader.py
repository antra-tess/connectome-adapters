import pytest
import os
import json
import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from adapters.zulip_adapter.adapter.attachment_loaders.base_loader import BaseLoader

class TestZulipBaseLoader:
    """Tests for the Zulip BaseLoader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        return client

    @pytest.fixture
    def base_loader(self, patch_config, client_mock):
        """Create a BaseLoader with mocked dependencies"""
        return BaseLoader(patch_config, client_mock)

    class TestAttachmentIdGeneration:
        """Tests for attachment ID generation"""

        @pytest.mark.parametrize("file_path,expected_id", [
            ("/user_uploads/1/ab/cdn7uXpQWsr1v5hInlSCU8PL/test.jpg", "cdn7uXpQWsr1v5hInlSCU8PL"),
            ("/simple/path/file.jpg", hashlib.md5(b"/simple/path/file.jpg").hexdigest()),
            ("", hashlib.md5(b"").hexdigest()),
        ])
        def test_generate_attachment_id(self, base_loader, file_path, expected_id):
            """Test generating attachment IDs from file paths"""
            assert base_loader._generate_attachment_id(file_path) == expected_id

    class TestAttachmentTypeDetection:
        """Tests for attachment type detection"""

        @pytest.mark.parametrize("extension,expected_type", [
            ("jpg", "image"),
            ("png", "image"),
            ("gif", "image"),
            ("mp4", "video"),
            ("mov", "video"),
            ("mp3", "audio"),
            ("wav", "audio"),
            ("pdf", "document"),
            ("docx", "document"),
            ("zip", "archive"),
            ("rar", "archive"),
            ("py", "code"),
            ("js", "code"),
            ("epub", "ebook"),
            ("ttf", "font"),
            ("obj", "3d_model"),
            ("exe", "executable"),
            ("tgs", "sticker"),
            ("unknown", "document"),  # Default for unknown extensions
            (None, "document")  # Default for no extension
        ])
        def test_get_attachment_type_by_extension(self, base_loader, extension, expected_type):
            """Test attachment type detection by file extension"""
            assert base_loader._get_attachment_type_by_extension(extension) == expected_type

    class TestDirectoryCreation:
        """Tests for directory creation"""

        def test_create_attachment_dir(self, base_loader):
            """Test creating an attachment directory"""
            test_dir = "/path/to/attachments"
            
            with patch("os.makedirs") as mock_makedirs:
                base_loader._create_attachment_dir(test_dir)
                mock_makedirs.assert_called_once_with(test_dir, exist_ok=True)

    class TestMetadataFileCreation:
        """Tests for metadata file creation"""

        def test_create_metadata_file(self, base_loader):
            """Test creating a metadata file"""
            metadata = {
                "attachment_id": "test123",
                "attachment_type": "photo",
                "file_extension": "jpg",
                "created_at": datetime.now(),
                "size": 12345
            }
            attachment_dir = "/fake/path"

            with patch("builtins.open", mock_open()) as mock_file:
                with patch("json.dump") as mock_json_dump:
                    base_loader._create_metadata_file(metadata, attachment_dir)

                    expected_path = os.path.join(attachment_dir, "test123.json")
                    mock_file.assert_called_once_with(expected_path, "w")
                    mock_json_dump.assert_called_once()

                    args, kwargs = mock_json_dump.call_args
                    assert args[0] == metadata  # First arg is the metadata
                    assert kwargs.get("indent") == 2
                    assert "default" in kwargs  # Should have a default serializer for datetime

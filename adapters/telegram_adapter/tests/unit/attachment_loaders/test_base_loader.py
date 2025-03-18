import pytest
import os
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from adapters.telegram_adapter.adapter.attachment_loaders.base_loader import BaseLoader

class TestBaseLoader:
    """Tests for the BaseLoader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Telethon client"""
        return AsyncMock()

    @pytest.fixture
    def base_loader(self, client_mock, patch_config):
        """Create a BaseLoader with mocked dependencies"""
        yield BaseLoader(patch_config, client_mock)

    @pytest.fixture
    def mock_photo_message(self):
        """Create a mock message with a photo attachment"""
        message = MagicMock()
        message.id = "123"
        photo = MagicMock()
        photo.id = "photo789"
        size = MagicMock()
        size.size = 12345
        photo.sizes = [size]
        message.photo = photo
        message.media = MagicMock()
        message.document = None
        return message

    @pytest.fixture
    def mock_document_message(self):
        """Create a mock message with a document attachment"""
        message = MagicMock()
        message.id = "456"
        document = MagicMock()
        document.id = "doc789"
        document.size = 98765
        attr = MagicMock()
        attr.file_name = "test.pdf"
        document.attributes = [attr]
        message.document = document
        message.photo = None
        message.media = MagicMock()
        return message

    @pytest.fixture
    def mock_message_without_media(self):
        """Create a mock message without media"""
        message = MagicMock()
        message.id = "789"
        message.media = None
        message.document = None
        message.photo = None
        return message

    class TestAttachmentMetadataDetection:
        """Tests for attachment metadata extraction"""

        @pytest.mark.asyncio
        async def test_get_attachment_metadata_photo(self, base_loader, mock_photo_message):
            """Test extracting metadata from a photo message"""
            metadata = await base_loader._get_attachment_metadata(mock_photo_message)

            assert metadata["attachment_type"] == "photo"
            assert metadata["attachment_id"] == "photo789"
            assert metadata["file_extension"] == "jpg"
            assert metadata["size"] == 12345
            assert "created_at" in metadata

        @pytest.mark.asyncio
        async def test_get_attachment_metadata_document(self, base_loader, mock_document_message):
            """Test extracting metadata from a document message"""
            metadata = await base_loader._get_attachment_metadata(mock_document_message)

            assert metadata["attachment_type"] == "document"  # pdf -> document type
            assert metadata["attachment_id"] == "doc789"
            assert metadata["file_extension"] == "pdf"
            assert metadata["size"] == 98765
            assert "created_at" in metadata

        @pytest.mark.asyncio
        async def test_get_attachment_metadata_no_media(self, base_loader, mock_message_without_media):
            """Test handling a message without media"""
            metadata = await base_loader._get_attachment_metadata(mock_message_without_media)

            assert metadata == {}  # Should return empty dict

        def test_get_file_size_photo(self, base_loader, mock_photo_message):
            """Test getting file size from a photo message"""
            size = base_loader._get_file_size(mock_photo_message)
            assert size == 12345

        def test_get_file_size_document(self, base_loader, mock_document_message):
            """Test getting file size from a document message"""
            size = base_loader._get_file_size(mock_document_message)
            assert size == 98765

        def test_get_file_size_no_media(self, base_loader, mock_message_without_media):
            """Test getting file size from a message without media"""
            size = base_loader._get_file_size(mock_message_without_media)
            assert size is None

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
            result = base_loader._get_attachment_type_by_extension(extension)
            assert result == expected_type

    class TestMetadataFileCreation:
        """Tests for metadata file creation"""

        def test_create_attachment_dir(self, base_loader):
            """Test creating an attachment directory"""
            with patch("os.makedirs") as mock_makedirs:
                dir_path = base_loader._create_attachment_dir("photo", "123")
                expected_path = os.path.join("test_attachments", "photo", "123")

                mock_makedirs.assert_called_once_with(expected_path, exist_ok=True)
                assert dir_path == expected_path

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

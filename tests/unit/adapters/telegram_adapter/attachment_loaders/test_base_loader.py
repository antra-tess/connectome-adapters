import json
import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open

from src.adapters.telegram_adapter.attachment_loaders.base_loader import BaseLoader

class TestBaseLoader:
    """Tests for the BaseLoader class"""

    @pytest.fixture
    def base_loader(self, telegram_config):
        """Create a BaseLoader with mocked dependencies"""
        yield BaseLoader(telegram_config, AsyncMock())

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

    @pytest.mark.asyncio
    async def test_get_attachment_metadata_photo(self, base_loader, mock_photo_message):
        """Test extracting metadata from a photo message"""
        metadata = await base_loader._get_attachment_metadata(mock_photo_message)

        assert metadata["attachment_type"] == "photo"
        assert metadata["attachment_id"] == "photo789"
        assert metadata["filename"] == "photo789.jpg"
        assert metadata["size"] == 12345
        assert "created_at" in metadata

    @pytest.mark.asyncio
    async def test_get_attachment_metadata_document(self, base_loader, mock_document_message):
        """Test extracting metadata from a document message"""
        metadata = await base_loader._get_attachment_metadata(mock_document_message)

        assert metadata["attachment_type"] == "document"  # pdf -> document type
        assert metadata["attachment_id"] == "doc789"
        assert metadata["filename"] == "doc789.pdf"
        assert metadata["size"] == 98765
        assert "created_at" in metadata

    @pytest.mark.asyncio
    async def test_get_attachment_metadata_no_media(self, base_loader, mock_message_without_media):
        """Test handling a message without media"""
        assert await base_loader._get_attachment_metadata(mock_message_without_media) == {}

    def test_get_file_size_photo(self, base_loader, mock_photo_message):
        """Test getting file size from a photo message"""
        assert base_loader._get_file_size(mock_photo_message) == 12345

    def test_get_file_size_document(self, base_loader, mock_document_message):
        """Test getting file size from a document message"""
        assert base_loader._get_file_size(mock_document_message) == 98765

    def test_get_file_size_no_media(self, base_loader, mock_message_without_media):
        """Test getting file size from a message without media"""
        assert base_loader._get_file_size(mock_message_without_media) is None

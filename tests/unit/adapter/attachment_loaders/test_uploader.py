import pytest
import os
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from adapter.attachment_loaders.uploader import Uploader

class TestUploader:
    """Tests for the Uploader class"""

    @pytest.fixture
    def config_mock(self):
        """Create a mocked Config instance"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key, default=None: {
            "attachments": {
                "storage_dir": "test_storage_dir",
                "large_file_threshold_mb": 50,
                "max_file_size_mb": 1000
            }
        }.get(section, {}).get(key, default)
        return config

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Telethon client"""
        client = AsyncMock()
        client.send_file = AsyncMock()
        return client

    @pytest.fixture
    def uploader(self, client_mock, config_mock):
        """Create an Uploader with mocked dependencies"""
        with patch("adapter.attachment_loaders.base_loader.Config") as ConfigMock:
            ConfigMock.return_value.get_instance.return_value = config_mock
            uploader = Uploader(client_mock)
            yield uploader

    @pytest.fixture
    def sample_standard_attachment(self):
        """Create sample photo attachment info"""
        return {
            "attachment_type": "photo",
            "file_path": "/test/path/photo123.jpg",
            "size": 12345
        }

    @pytest.fixture
    def sample_large_attachment(self):
        """Create sample large attachment info"""
        return {
            "attachment_type": "video",
            "file_path": "/test/path/large789.mp4",
            "size": 60 * 1024 * 1024  # 60MB
        }

    @pytest.fixture
    def mock_telegram_message(self):
        """Create a mock Telegram message returned after sending a file"""
        message = MagicMock()
        message.id = "msg123"
        photo = MagicMock()
        photo.id = "uploaded_media_id"
        message.photo = photo
        return message

    class TestUploadAttachment:
        """Tests for the upload_attachment method"""

        @pytest.mark.asyncio
        async def test_file_not_found(self, uploader, sample_standard_attachment):
            """Test handling missing file"""
            with patch("os.path.exists", return_value=False):
                result = await uploader.upload_attachment("conversation", sample_standard_attachment)

                assert result == {}
                uploader.client.send_file.assert_not_called()

        @pytest.mark.asyncio
        async def test_file_too_large(self, uploader):
            """Test handling file that exceeds size limit"""
            oversized_attachment = {
                "attachment_type": "video",
                "file_path": "/test/path/huge123.mp4",
                "size": 3000 * 1024 * 1024
            }

            with patch("os.path.exists", return_value=True):
                result = await uploader.upload_attachment("conversation", oversized_attachment)

                assert result == {}
                uploader.client.send_file.assert_not_called()

        @pytest.mark.asyncio
        async def test_no_conversation(self, uploader, sample_standard_attachment):
            """Test handling missing conversation"""
            with patch("os.path.exists", return_value=True):
                result = await uploader.upload_attachment(None, sample_standard_attachment)

                assert result == {}
                uploader.client.send_file.assert_not_called()

        @pytest.mark.asyncio
        async def test_upload_standard_file(self, uploader, sample_standard_attachment, mock_telegram_message):
            """Test uploading a standard photo"""
            with patch("os.path.exists", return_value=True):
                with patch.object(uploader, "_upload_standard_file") as mock_upload:
                    mock_upload.return_value = mock_telegram_message

                    with patch.object(uploader, "_get_attachment_metadata") as mock_get_metadata:
                        mock_get_metadata.return_value = {
                            "attachment_id": "uploaded_media_id",
                            "attachment_type": "photo",
                            "file_extension": "jpg",
                            "created_at": datetime.now(),
                            "size": 12345
                        }

                        with patch.object(uploader, "_create_attachment_dir") as mock_create_dir:
                            mock_create_dir.return_value = "/test/output/path"

                            with patch.object(uploader, "_create_metadata_file") as mock_create_metadata:
                                with patch.object(uploader, "_move_attachment") as mock_move:
                                    with patch.object(uploader, "_delete_empty_directory") as mock_delete_dir:
                                        result = await uploader.upload_attachment("conversation", sample_standard_attachment)

                                        mock_upload.assert_called_once()
                                        mock_get_metadata.assert_called_once_with(mock_telegram_message)
                                        mock_create_dir.assert_called_once()
                                        mock_create_metadata.assert_called_once()
                                        mock_move.assert_called_once()
                                        mock_delete_dir.assert_called_once()

                                        assert result["attachment_id"] == "uploaded_media_id"
                                        assert result["attachment_type"] == "photo"
                                        assert "message" in result

        @pytest.mark.asyncio
        async def test_upload_large_file(self, uploader, sample_large_attachment, mock_telegram_message):
            """Test uploading a large file"""
            with patch("os.path.exists", return_value=True):
                with patch.object(uploader, "_upload_large_file") as mock_upload:
                    mock_upload.return_value = mock_telegram_message

                    with patch.object(uploader, "_get_attachment_metadata") as mock_get_metadata:
                        mock_get_metadata.return_value = {
                            "attachment_id": "uploaded_media_id",
                            "attachment_type": "document",
                            "file_extension": "mp4",
                            "created_at": datetime.now(),
                            "size": 60 * 1024 * 1024
                        }

                        with patch.object(uploader, "_create_attachment_dir") as _:
                            with patch.object(uploader, "_create_metadata_file") as _:
                                with patch.object(uploader, "_move_attachment") as _:
                                    with patch.object(uploader, "_delete_empty_directory") as _:
                                        result = await uploader.upload_attachment("conversation", sample_large_attachment)

                                        mock_upload.assert_called_once()
                                        args, _ = mock_upload.call_args
                                        assert args[0] == "conversation"
                                        assert result["attachment_id"] == "uploaded_media_id"

        @pytest.mark.asyncio
        async def test_upload_error_handling(self, uploader, sample_standard_attachment):
            """Test error handling during upload"""
            with patch("os.path.exists", return_value=True):
                with patch.object(uploader, "_upload_standard_file",
                                  side_effect=Exception("Test upload error")):

                    result = await uploader.upload_attachment("conversation", sample_standard_attachment)
                    assert result == {}

    class TestUploadMethods:
        """Tests for specific upload methods"""

        @pytest.mark.asyncio
        async def test_upload_standard_file(self, uploader, sample_standard_attachment):
            """Test standard file upload method"""
            conversation = "test_conversation"
            upload_kwargs = {
                "file": sample_standard_attachment["file_path"],
                "force_document": False
            }

            uploader.client.send_file.return_value = "test_result"

            with patch("os.path.getsize", return_value=12345):
                result = await uploader._upload_standard_file(conversation, upload_kwargs)
                uploader.client.send_file.assert_called_once_with(
                    entity=conversation, **upload_kwargs
                )
                assert result == "test_result"

        @pytest.mark.asyncio
        async def test_upload_large_file(self, uploader, sample_large_attachment):
            """Test large file upload method"""
            conversation = "test_conversation"
            upload_kwargs = {
                "file": sample_large_attachment["file_path"],
                "force_document": True
            }

            uploader.client.send_file.return_value = "test_result"

            with patch("os.path.getsize", return_value=60 * 1024 * 1024):
                with patch("os.path.basename", return_value="large789.mp4"):
                    result = await uploader._upload_large_file(conversation, upload_kwargs)
                    uploader.client.send_file.assert_called_once()

                    call_args = uploader.client.send_file.call_args
                    assert call_args[1]["entity"] == conversation
                    assert call_args[1]["file"] == sample_large_attachment["file_path"]
                    assert call_args[1]["force_document"] is True
                    assert "progress_callback" in call_args[1]
                    assert call_args[1]["part_size_kb"] == 512
                    assert call_args[1]["use_cache"] is False
                    assert result == "test_result"

    class TestHelperMethods:
        """Tests for helper methods"""

        def test_move_attachment(self, uploader):
            """Test moving an attachment file"""
            src_path = "/test/source/file.jpg"
            dest_path = "/test/dest/file.jpg"

            with patch("shutil.move") as mock_move:
                uploader._move_attachment(src_path, dest_path)

                mock_move.assert_called_once_with(src_path, dest_path)

        def test_delete_empty_directory(self, uploader):
            """Test deleting an empty directory"""
            file_path = "/test/dir/file.jpg"

            with patch("os.path.dirname", return_value="/test/dir"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.listdir", return_value=[]):
                        with patch("os.rmdir") as mock_rmdir:
                            uploader._delete_empty_directory(file_path)

                            mock_rmdir.assert_called_once_with("/test/dir")

        def test_delete_empty_directory_not_empty(self, uploader):
            """Test not deleting a non-empty directory"""
            file_path = "/test/dir/file.jpg"

            with patch("os.path.dirname", return_value="/test/dir"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.listdir", return_value=["other_file.txt"]):
                        with patch("os.rmdir") as mock_rmdir:
                            uploader._delete_empty_directory(file_path)

                            mock_rmdir.assert_not_called()

import pytest
import aiohttp
import os
import shutil
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader

class TestZulipUploader:
    """Tests for the Zulip Uploader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        return client

    @pytest.fixture
    def uploader(self, patch_config, client_mock):
        """Create an Uploader with mocked dependencies"""
        return Uploader(patch_config, client_mock)

    @pytest.fixture
    def sample_standard_attachment(self):
        """Create sample document attachment info"""
        return {
            "attachment_type": "document",
            "file_path": "/test/path/document123.pdf",
            "size": 12345
        }

    @pytest.fixture
    def zulip_upload_response(self):
        """Create a mock Zulip upload response"""
        return {
            "uri": "/user_uploads/1/ab/xyz123/test.pdf",
            "id": 12345
        }

    class TestUploadAttachment:
        """Tests for the upload_attachment method"""

        @pytest.mark.asyncio
        async def test_file_not_found(self, uploader, sample_standard_attachment):
            """Test handling missing file"""
            with patch("os.path.exists", return_value=False):
                with patch("logging.error") as mock_log:
                    result = await uploader.upload_attachment(sample_standard_attachment)

                    assert result is None
                    assert mock_log.called
                    assert "File not found" in mock_log.call_args[0][0]

        @pytest.mark.asyncio
        async def test_file_too_large(self, uploader):
            """Test handling file that exceeds size limit"""
            oversized_attachment = {
                "attachment_type": "video",
                "file_path": "/test/path/huge123.mp4",
                "size": 50 * 1024 * 1024  # 50MB, above 25MB limit
            }

            with patch("os.path.exists", return_value=True):
                with patch("logging.error") as mock_log:
                    result = await uploader.upload_attachment(oversized_attachment)

                    assert result is None
                    assert mock_log.called
                    assert "exceeds Zulip's size limit" in mock_log.call_args[0][0]

    class TestUploadFile:
        """Tests for the _upload_file method"""

        @pytest.fixture
        def mock_upload_response(self, expected_uri="/user_uploads/1/ab/xyz123/document.pdf"):
            """Create a mock Zulip upload response"""
            class MockResponse:
                status = 200                
                async def json(self):
                    return {"uri": expected_uri}                    
                async def text(self):
                    return "Test response text"                    
                async def __aenter__(self):
                    return self                    
                async def __aexit__(self, *args):
                    pass
            return MockResponse()

        @pytest.fixture
        def session_mock(self, mock_upload_response):
            """Create a mocked Zulip session"""
            class MockSession:
                def __init__(self):
                    self.post_called = False
                    self.post_args = None
                    self.post_kwargs = None                
                async def __aenter__(self):
                    return self                    
                async def __aexit__(self, *args):
                    pass
                def post(self, *args, **kwargs):
                    self.post_called = True
                    self.post_args = args
                    self.post_kwargs = kwargs
                    return mock_upload_response                
            return MockSession()

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_upload_file_success(self, uploader, session_mock):
            """Test successful file upload"""
            file_path = "/test/path/document.pdf"

            with patch("aiohttp.ClientSession", return_value=session_mock):
                with patch("builtins.open", mock_open(read_data=b"test file content")):
                    with patch("aiohttp.FormData", return_value=MagicMock()):
                        with patch("aiohttp.BasicAuth", return_value=MagicMock()):
                            result = await uploader._upload_file(file_path)

                            assert "uri" in result
                            assert "document.pdf" in result["uri"]

                            assert session_mock.post_called, "session.post was not called"
                            assert session_mock.post_args[0].endswith("/api/v1/user_uploads"), \
                                f"Unexpected URL: {session_mock.post_args[0]}"
                            assert "auth" in session_mock.post_kwargs, "auth parameter missing"
                            assert "data" in session_mock.post_kwargs, "data parameter missing"

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_upload_file_exception(self, uploader):
            """Test handling exception during upload"""
            file_path = "/test/path/document.pdf"

            session_mock = AsyncMock()
            session_mock.__aenter__.return_value = session_mock
            session_mock.post.side_effect = Exception("Connection error")
            
            with patch("aiohttp.ClientSession", return_value=session_mock):
                with patch("builtins.open", mock_open(read_data=b'test file content')):
                    with patch.object(uploader, "_get_mime_type", return_value="application/pdf"):
                        with patch("logging.error") as mock_log:
                            assert await uploader._upload_file(file_path) == {}
                            assert mock_log.called
                            assert "Error in manual upload" in mock_log.call_args[0][0]

    class TestMimeType:
        """Tests for MIME type detection"""

        def test_get_mime_type_known(self, uploader):
            """Test getting MIME type for known file extensions"""
            test_cases = [
                ("/path/to/file.pdf", "application/pdf"),
                ("/path/to/image.jpg", "image/jpeg"),
                ("/path/to/text.txt", "text/plain")
            ]
            
            for file_path, expected_mime in test_cases:
                with patch("mimetypes.guess_type", return_value=(expected_mime, None)):
                    result = uploader._get_mime_type(file_path)
                    assert result == expected_mime

        def test_get_mime_type_unknown(self, uploader):
            """Test getting MIME type for unknown file extensions"""
            with patch("mimetypes.guess_type", return_value=(None, None)):
                result = uploader._get_mime_type("/path/to/unknown.xyz")
                assert result == "application/octet-stream"

    class TestCleanUp:
        """Tests for file cleanup after upload"""

        def test_clean_up_uploaded_file(self, uploader):
            """Test cleaning up file after upload"""
            old_path = "/test/path/document.pdf"
            zulip_uri = "/user_uploads/1/ab/xyz123/test.pdf"
            
            with patch.object(uploader, "_generate_attachment_id", return_value="xyz123"):
                with patch.object(uploader, "_get_attachment_type_by_extension", return_value="document"):
                    with patch.object(uploader, "_create_attachment_dir") as mock_create_dir:
                        with patch.object(uploader, "_move_attachment") as mock_move:
                            with patch.object(uploader, "_delete_empty_directory") as mock_delete_dir:
                                uploader._clean_up_uploaded_file(old_path, zulip_uri)
                                
                                mock_create_dir.assert_called_once()
                                mock_move.assert_called_once()
                                mock_delete_dir.assert_called_once_with(old_path)

        def test_move_attachment(self, uploader):
            """Test moving an attachment file"""
            src_path = "/test/source/file.pdf"
            dest_path = "/test/dest/file.pdf"

            with patch("shutil.move") as mock_move:
                uploader._move_attachment(src_path, dest_path)
                mock_move.assert_called_once_with(src_path, dest_path)

        def test_delete_empty_directory(self, uploader):
            """Test deleting an empty directory"""
            file_path = "/test/dir/file.pdf"

            with patch("os.path.dirname", return_value="/test/dir"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.listdir", return_value=[]):
                        with patch("os.rmdir") as mock_rmdir:
                            with patch("logging.info") as mock_log:
                                uploader._delete_empty_directory(file_path)
                                
                                mock_rmdir.assert_called_once_with("/test/dir")
                                assert mock_log.called
                                assert "Removed directory" in mock_log.call_args[0][0]

        def test_delete_empty_directory_not_empty(self, uploader):
            """Test not deleting a non-empty directory"""
            file_path = "/test/dir/file.pdf"

            with patch("os.path.dirname", return_value="/test/dir"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.listdir", return_value=["other_file.txt"]):
                        with patch("os.rmdir") as mock_rmdir:
                            uploader._delete_empty_directory(file_path)
                            mock_rmdir.assert_not_called()

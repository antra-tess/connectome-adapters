import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
from core.conversation.base_data_classes import UserInfo
from core.utils.config import Config

class TestHistoryFetcher:
    """Tests for the HistoryFetcher class"""

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.get_messages = MagicMock()
        return client

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock()
        return downloader

    @pytest.fixture
    def private_conversation(self):
        """Create a private conversation fixture"""
        conversation = MagicMock(spec=ConversationInfo)
        conversation.conversation_id = "123_456"
        conversation.conversation_type = "private"
        conversation.to_fields = MagicMock(return_value=["user1@example.com", "user2@example.com"])
        conversation.known_members = {
            "123": UserInfo(user_id="123", username="User One", email="user1@example.com"),
            "456": UserInfo(user_id="456", username="User Two", email="user2@example.com")
        }
        
        return conversation

    @pytest.fixture
    def stream_conversation(self):
        """Create a stream conversation fixture"""
        conversation = MagicMock(spec=ConversationInfo)
        conversation.conversation_id = "789/Test Topic"
        conversation.conversation_type = "stream"
        conversation.conversation_name = "Test Stream"
        conversation.to_fields = MagicMock(return_value="Test Stream")
        
        return conversation

    @pytest.fixture
    def mock_messages(self):
        """Create mock message data"""
        return [
            {
                "id": 1001,
                "sender_id": 123,
                "sender_full_name": "User One",
                "content": "Hello world",
                "timestamp": 1627984000,  # Example timestamp
                "subject": "Test Topic"
            },
            {
                "id": 1002,
                "sender_id": 456,
                "sender_full_name": "User Two",
                "content": "@_**User One|123** [said](https://zulip.example.com/#narrow/stream/123-general/topic/test/near/1001):\n```quote\nHello world\n```\nReply to message",
                "timestamp": 1627984100,  # Example timestamp
                "subject": "Test Topic"
            }
        ]

    @pytest.fixture
    def mock_attachments(self):
        """Create mock attachment data"""
        return [
            {
                "attachment_id": "attachment1",
                "attachment_type": "image",
                "file_extension": "jpg",
                "file_path": "/path/to/image.jpg",
                "size": 12345
            }
        ]

    @pytest.fixture
    def history_fetcher(self, patch_config, zulip_client_mock, downloader_mock):
        """Create a message with a reply to ID"""
        def _create(conversation):
            return HistoryFetcher(
                config=patch_config,
                client=zulip_client_mock,
                downloader=downloader_mock,
                conversation=conversation,
                anchor="2000"  # Some anchor message ID
            )
        return _create

    @pytest.mark.asyncio
    async def test_fetch_private_conversation(self,
                                              history_fetcher,
                                              mock_messages,
                                              mock_attachments,
                                              private_conversation):
        """Test fetching history for a private conversation"""
        fetcher = history_fetcher(private_conversation)
        fetcher.downloader.download_attachment.return_value = mock_attachments
        fetcher.client.get_messages.return_value = {
            "result": "success",
            "messages": mock_messages
        }
        history = await fetcher.fetch()

        fetcher.client.get_messages.assert_called_once()
        call_args = fetcher.client.get_messages.call_args[0][0]
        
        assert json.loads(call_args["narrow"]) == [{"operator": "pm-with", "operand": "user1@example.com,user2@example.com"}]
        assert call_args["anchor"] == "2000"
        assert call_args["num_before"] == 100
        assert call_args["num_after"] == 0
        assert call_args["include_anchor"] is False
        assert fetcher.downloader.download_attachment.call_count == 2

        assert len(history) == 2
        assert history[0]["message_id"] == "1001"
        assert history[0]["conversation_id"] == "123_456"
        assert history[0]["sender"]["user_id"] == "123"
        assert history[0]["sender"]["display_name"] == "User One"
        assert history[0]["text"] == "Hello world"
        assert history[0]["thread_id"] is None
        assert history[0]["timestamp"] == 1627984000
        assert history[0]["attachments"] == mock_attachments

        assert history[1]["message_id"] == "1002"
        assert history[1]["thread_id"] == "1001"  # Should detect it's a reply to message 1001
        assert history[1]["timestamp"] == 1627984100

    @pytest.mark.asyncio
    async def test_fetch_stream_conversation(self,
                                             history_fetcher,
                                             mock_messages,
                                             stream_conversation):
        """Test fetching history for a stream conversation"""
        fetcher = history_fetcher(stream_conversation)
        fetcher.downloader.download_attachment.return_value = []
        fetcher.client.get_messages.return_value = {
            "result": "success",
            "messages": mock_messages
        }
        history = await fetcher.fetch()

        fetcher.client.get_messages.assert_called_once()
        call_args = fetcher.client.get_messages.call_args[0][0]
        
        assert json.loads(call_args["narrow"]) == [
            {"operator": "stream", "operand": "Test Stream"},
            {"operator": "topic", "operand": "Test Topic"}
        ]

        assert len(history) == 2
        assert history[0]["conversation_id"] == "789/Test Topic"
        assert len(history[0]["attachments"]) == 0  # No attachments

    @pytest.mark.asyncio
    async def test_fetch_no_conversation(self, history_fetcher):
        """Test fetching history with no conversation"""
        fetcher = history_fetcher(None)

        assert await fetcher.fetch() == []
        fetcher.client.get_messages.assert_not_called()

    def test_get_narrow_for_private_conversation(self, history_fetcher, private_conversation):
        """Test generating narrow for private conversation"""
        fetcher = history_fetcher(private_conversation)
        
        narrow = fetcher._get_narrow_for_conversation()
        assert narrow == [{"operator": "pm-with", "operand": "user1@example.com,user2@example.com"}]

    def test_get_narrow_for_stream_conversation(self, history_fetcher, stream_conversation):
        """Test generating narrow for stream conversation"""
        fetcher = history_fetcher(stream_conversation)
        
        narrow = fetcher._get_narrow_for_conversation()
        assert narrow == [
            {"operator": "stream", "operand": "Test Stream"},
            {"operator": "topic", "operand": "Test Topic"}
        ]

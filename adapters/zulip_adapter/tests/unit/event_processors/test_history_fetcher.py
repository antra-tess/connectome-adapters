import json
import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.conversation.manager import Manager
from adapters.zulip_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
from core.conversation.base_data_classes import UserInfo

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

    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        limiter = AsyncMock()
        limiter.limit_request = AsyncMock()
        return limiter

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock(spec=Manager)
        manager.get_conversation = MagicMock()
        manager.get_conversation_cache = MagicMock(return_value=[])
        manager.add_to_conversation = AsyncMock()
        return manager

    @pytest.fixture
    def conversation(self):
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
    def mock_messages(self):
        """Create mock message data"""
        return [
            {
                "id": 1001,
                "sender_id": 123,
                "sender_full_name": "User One",
                "content": "Hello world",
                "timestamp": 1627984000,
                "subject": "Test Topic"
            },
            {
                "id": 1002,
                "sender_id": 456,
                "sender_full_name": "User Two",
                "content": "@_**User One|123** [said](https://zulip.example.com/123-general/near/1001):\n```quote\nHello world\n```\nReply to message",
                "timestamp": 1627984100,
                "subject": "Test Topic"
            }
        ]

    @pytest.fixture
    def mock_cached_messages(self):
        """Create mock cached message data"""
        return [
            {
                "message_id": "1001",
                "conversation_id": "123_456",
                "sender": {
                    "user_id": "123",
                    "display_name": "User One"
                },
                "text": "Hello world",
                "thread_id": None,
                "timestamp": 1627984000,
                "attachments": []
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
    def history_fetcher(self,
                        patch_config,
                        zulip_client_mock,
                        conversation_manager_mock,
                        rate_limiter_mock,
                        downloader_mock,
                        conversation):
        """Create a HistoryFetcher instance"""
        def _create(conversation_id, anchor=None, before=None, after=None, history_limit=None):
            if conversation_id == "123_456":
                conversation_manager_mock.get_conversation.return_value = conversation
            else:
                conversation_manager_mock.get_conversation.return_value = None

            fetcher = HistoryFetcher(
                config=patch_config,
                client=zulip_client_mock,
                conversation_manager=conversation_manager_mock,
                conversation_id=conversation_id,
                anchor=anchor,
                before=before,
                after=after,
                history_limit=history_limit
            )
            fetcher.downloader = downloader_mock
            fetcher.rate_limiter = rate_limiter_mock

            return fetcher
        return _create

    @pytest.mark.asyncio
    async def test_fetch_with_anchor(self,
                                     history_fetcher,
                                     mock_messages,
                                     mock_attachments):
        """Test fetching history with an anchor"""
        fetcher = history_fetcher("123_456", anchor="2000")
        fetcher.downloader.download_attachment.return_value = mock_attachments
        fetcher.client.get_messages.return_value = {
            "result": "success",
            "messages": mock_messages
        }
        fetcher.conversation_manager.add_to_conversation.side_effect = [
            {
                "added_messages": [{
                    "message_id": str(mock_messages[0]["id"]),
                    "conversation_id": "123_456",
                    "sender": {
                        "user_id": str(mock_messages[0]["sender_id"]),
                        "display_name": mock_messages[0]["sender_full_name"]
                    },
                    "text": mock_messages[0]["content"],
                    "thread_id": None,
                    "timestamp": mock_messages[0]["timestamp"],
                    "attachments": mock_attachments
                }]
            },
            {
                "added_messages": [{
                    "message_id": str(mock_messages[1]["id"]),
                    "conversation_id": "123_456",
                    "sender": {
                        "user_id": str(mock_messages[1]["sender_id"]),
                        "display_name": mock_messages[1]["sender_full_name"]
                    },
                    "text": mock_messages[1]["content"],
                    "thread_id": "1001",
                    "timestamp": mock_messages[1]["timestamp"],
                    "attachments": mock_attachments
                }]
            }
        ]

        history = await fetcher.fetch()

        fetcher.rate_limiter.limit_request.assert_called_once()
        fetcher.client.get_messages.assert_called_once()
        call_args = fetcher.client.get_messages.call_args[0][0]

        assert json.loads(call_args["narrow"]) == [
            {"operator": "pm-with", "operand": "user1@example.com,user2@example.com"}
        ]
        assert call_args["anchor"] == "2000"
        assert call_args["num_before"] == 100
        assert call_args["num_after"] == 0
        assert call_args["include_anchor"] is False

        assert fetcher.downloader.download_attachment.call_count == 2
        assert fetcher.conversation_manager.add_to_conversation.call_count == 2

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
    async def test_fetch_with_before(self,
                                     history_fetcher,
                                     mock_messages,
                                     mock_attachments):
        """Test fetching history with before timestamp"""
        fetcher = history_fetcher("123_456", before=1627984200)
        fetcher.downloader.download_attachment.return_value = mock_attachments
        fetcher.client.get_messages.return_value = {
            "result": "success",
            "messages": mock_messages
        }

        formatted_messages = []
        for msg in mock_messages:
            formatted_messages.append({
                "message_id": str(msg["id"]),
                "conversation_id": "123_456",
                "sender": {
                    "user_id": str(msg["sender_id"]),
                    "display_name": msg["sender_full_name"]
                },
                "text": msg["content"],
                "thread_id": None,
                "timestamp": msg["timestamp"],
                "attachments": mock_attachments
            })
        fetcher.conversation_manager.add_to_conversation.side_effect = [
            {"added_messages": [formatted_messages[0]]},
            {"added_messages": [formatted_messages[1]]}
        ]

        history = await fetcher.fetch()

        fetcher.rate_limiter.limit_request.assert_called_once()
        fetcher.client.get_messages.assert_called_once()
        call_args = fetcher.client.get_messages.call_args[0][0]

        assert call_args["anchor"] == "newest"
        assert call_args["num_before"] == 300  # 3x limit for better filtering
        assert call_args["num_after"] == 0

        fetcher.conversation_manager.get_conversation_cache.assert_called_once()
        assert len(history) == 2  # Both messages are before the timestamp

    @pytest.mark.asyncio
    async def test_fetch_with_after(self,
                                    history_fetcher,
                                    mock_messages,
                                    mock_attachments):
        """Test fetching history with after timestamp"""
        fetcher = history_fetcher("123_456", after=1627983900)
        fetcher.downloader.download_attachment.return_value = mock_attachments
        fetcher.client.get_messages.return_value = {
            "result": "success",
            "messages": mock_messages
        }

        formatted_messages = []
        for msg in mock_messages:
            formatted_messages.append({
                "message_id": str(msg["id"]),
                "conversation_id": "123_456",
                "sender": {
                    "user_id": str(msg["sender_id"]),
                    "display_name": msg["sender_full_name"]
                },
                "text": msg["content"],
                "thread_id": None,
                "timestamp": msg["timestamp"],
                "attachments": mock_attachments
            })
        fetcher.conversation_manager.add_to_conversation.side_effect = [
            {"added_messages": [formatted_messages[0]]},
            {"added_messages": [formatted_messages[1]]}
        ]

        history = await fetcher.fetch()
        fetcher.client.get_messages.assert_called_once()
        call_args = fetcher.client.get_messages.call_args[0][0]

        assert call_args["anchor"] == "oldest"
        assert call_args["num_before"] == 0
        assert call_args["num_after"] == 300  # 3x limit for better filtering
        assert len(history) == 2  # Both messages are after the timestamp

    @pytest.mark.asyncio
    async def test_cache_plus_api_fetch(self,
                                        history_fetcher,
                                        mock_cached_messages,
                                        mock_attachments):
        """Test fetching history with partial cache and API call"""
        fetcher = history_fetcher("123_456", after=1627983000, history_limit=3)
        fetcher.conversation_manager.get_conversation_cache.return_value = mock_cached_messages
        fetcher.client.get_messages.return_value = {
            "result": "success",
            "messages": [{"id": 1002}]
        }
        fetcher.downloader.download_attachment.return_value = mock_attachments
        fetcher.conversation_manager.add_to_conversation.return_value = {
            "added_messages": [
                {
                    "message_id": "1002",  # This should be different from cache message
                    "conversation_id": "123_456",
                    "sender": {
                        "user_id": "456",
                        "display_name": "User Two"
                    },
                    "text": "Reply to message",
                    "thread_id": None,
                    "timestamp": 1627984100,
                    "attachments": mock_attachments
                }
            ]
        }

        history = await fetcher.fetch()

        assert len(history) == 2
        assert history[0]["message_id"] == "1001"  # From cache
        assert history[1]["message_id"] == "1002"  # From API

    @pytest.mark.asyncio
    async def test_fetch_no_conversation(self, history_fetcher):
        """Test fetching history with no conversation"""
        fetcher = history_fetcher("nonexistent_id")
        assert await fetcher.fetch() == []

    def test_update_limits(self, history_fetcher, mock_cached_messages):
        """Test _update_limits method"""
        fetcher = history_fetcher("123_456", before=1627984200, history_limit=10)
        original_limit = fetcher.history_limit
        fetcher._update_limits(mock_cached_messages)

        assert fetcher.anchor == "1001"  # First message ID from cache
        assert fetcher.history_limit == original_limit - 1  # Reduced by cache size

        fetcher = history_fetcher("123_456", after=1627983900, history_limit=10)
        original_limit = fetcher.history_limit
        fetcher._update_limits(mock_cached_messages)

        assert fetcher.anchor == "1001"  # Last message ID from cache (only one in this case)
        assert fetcher.history_limit == original_limit - 1  # Reduced by cache size

    def test_extract_reply_to_id(self, history_fetcher):
        """Test extracting reply to ID from content"""
        fetcher = history_fetcher("123_456")
        content = "@_**User One|123** [said](https://zulip.example.com/123-general/near/1001):\n```quote\nHello world\n```\nReply to message"
        assert fetcher._extract_reply_to_id(content) == "1001"
        assert fetcher._extract_reply_to_id("Regular message") is None

import pytest
import asyncio
import discord

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

class TestHistoryFetcher:
    """Tests for the Discord HistoryFetcher class"""

    @pytest.fixture
    def discord_client_mock(self):
        """Create a mocked Discord client"""
        client = MagicMock()
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        limiter = AsyncMock()
        limiter.limit_request = AsyncMock()
        return limiter

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock(return_value=[])
        return downloader

    @pytest.fixture
    def channel_mock(self):
        """Create a mocked Discord channel"""
        channel = AsyncMock()
        return channel

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info fixture"""
        return ConversationInfo(
            conversation_id="987654321/123456789",
            conversation_type="channel",
            conversation_name="general"
        )

    @pytest.fixture
    def mock_message_with_attachment(self):
        """Create a mock Discord message with attachment"""
        message = MagicMock(spec=discord.Message)
        message.id = 111222333
        message.content = "Message with attachment"
        message.created_at = datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message.type = discord.MessageType.default

        # Create author
        author = MagicMock()
        author.id = 444555666
        author.name = "User One"
        author.display_name = "Cool User"
        message.author = author

        # Create attachment
        attachment = MagicMock(spec=discord.Attachment)
        attachment.id = 987654
        attachment.filename = "test.jpg"
        attachment.url = "https://example.com/test.jpg"
        attachment.size = 12345
        message.attachments = [attachment]

        # Create reference (reply)
        message.reference = None

        return message

    @pytest.fixture
    def mock_message_reply(self):
        """Create a mock Discord message that's a reply"""
        message = MagicMock(spec=discord.Message)
        message.id = 444555666
        message.content = "This is a reply"
        message.created_at = datetime(2021, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
        message.type = discord.MessageType.default

        # Create author
        author = MagicMock()
        author.id = 777888999
        author.name = "User Two"
        author.display_name = "User 2"
        message.author = author

        # No attachments
        message.attachments = []

        # Create reference (reply)
        reference = MagicMock()
        reference.message_id = 111222333  # Referring to the first message
        message.reference = reference

        return message

    @pytest.fixture
    def mock_service_message(self):
        """Create a mock Discord service message"""
        message = MagicMock(spec=discord.Message)
        message.id = 999888777
        message.content = "User joined the channel"
        message.created_at = datetime(2021, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        message.type = discord.MessageType.new_member  # Service message type

        # Create author
        author = MagicMock()
        author.id = 444555666
        author.name = "User One"
        author.display_name = "Cool User"
        message.author = author

        # No attachments
        message.attachments = []

        # No reference
        message.reference = None

        return message

    @pytest.fixture
    def history_fetcher(self,
                        patch_config,
                        discord_client_mock,
                        downloader_mock,
                        conversation_info,
                        rate_limiter_mock):
        """Create a HistoryFetcher instance"""
        history_fetcher = HistoryFetcher(
            config=patch_config,
            client=discord_client_mock,
            downloader=downloader_mock,
            conversation=conversation_info
        )
        history_fetcher.rate_limiter = rate_limiter_mock
        return history_fetcher

    @pytest.mark.asyncio
    async def test_fetch(self, history_fetcher, channel_mock):
        """Test fetching history"""
        history_mock = MagicMock()
        channel_mock.history.return_value = history_mock
        history_fetcher._get_channel = AsyncMock(return_value=channel_mock)
        history_fetcher._parse_fetched_history = AsyncMock(return_value=[])

        await history_fetcher.fetch()

        history_fetcher._get_channel.assert_called_once()
        channel_mock.history.assert_called_once_with(limit=10)
        history_fetcher._parse_fetched_history.assert_called_once_with(history_mock)

    @pytest.mark.asyncio
    async def test_parse_fetched_history(self,
                                         history_fetcher,
                                         mock_message_with_attachment,
                                         mock_message_reply,
                                         mock_service_message):
        """Test parsing fetched history"""
        history = [mock_message_with_attachment, mock_message_reply, mock_service_message]
        attachment_result = [{"attachment_type": "image", "file_path": "test.jpg", "size": 23}]
        history_fetcher.downloader.download_attachment.return_value = attachment_result

        result = await history_fetcher._parse_fetched_history(history)
        assert len(result) == 2  # Service message should be filtered out

        # First message assertions
        assert result[0]["message_id"] == "111222333"
        assert result[0]["conversation_id"] == "987654321/123456789"
        assert result[0]["text"] == "Message with attachment"
        assert result[0]["sender"]["user_id"] == "444555666"
        assert result[0]["sender"]["display_name"] == "Cool User"
        assert result[0]["thread_id"] is None
        assert result[0]["timestamp"] == 1609502400000  # 2021-01-01 12:00:00 in ms
        assert result[0]["attachments"] == attachment_result

        # Second message assertions
        assert result[1]["message_id"] == "444555666"
        assert result[1]["text"] == "This is a reply"
        assert result[1]["sender"]["user_id"] == "777888999"
        assert result[1]["sender"]["display_name"] == "User 2"
        assert result[1]["thread_id"] == "111222333"  # Should be the id of the message it's replying to
        assert result[1]["timestamp"] == 1609504200000  # 2021-01-01 12:30:00 in ms
        assert result[1]["attachments"] == []  # No attachments

    @pytest.mark.asyncio
    async def test_parse_fetched_history_with_parallel_downloads(self, history_fetcher):
        """Test parsing history with parallel attachment downloads"""
        messages = []
        for i in range(3):
            message = MagicMock(spec=discord.Message)
            message.id = 1000 + i
            message.content = f"Message {i}"
            message.created_at = datetime(2021, 1, 1, 12, i, 0, tzinfo=timezone.utc)
            message.type = discord.MessageType.default

            author = MagicMock()
            author.id = 2000 + i
            author.name = f"User {i}"
            author.display_name = f"User {i}"
            message.author = author

            if i % 2 == 0:
                attachment = MagicMock(spec=discord.Attachment)
                attachment.id = 3000 + i
                attachment.filename = f"file{i}.jpg"
                message.attachments = [attachment]
            else:
                message.attachments = []

            message.reference = None
            messages.append(message)

        async def mock_download(message):
            # Return a list with one attachment info dict
            message_id = message.id
            return [{"id": f"attachment-{message_id}", "filename": f"file-{message_id}.jpg"}]
        history_fetcher.downloader.download_attachment.side_effect = mock_download

        result = await history_fetcher._parse_fetched_history(messages)
        assert len(result) == 3

        assert result[0]["message_id"] == "1000"
        assert result[0]["attachments"] == [{"id": "attachment-1000", "filename": "file-1000.jpg"}]

        assert result[1]["message_id"] == "1001"
        assert result[1]["attachments"] == []  # No attachments

        assert result[2]["message_id"] == "1002"
        assert result[2]["attachments"] == [{"id": "attachment-1002", "filename": "file-1002.jpg"}]

        assert history_fetcher.downloader.download_attachment.call_count == 2  # Only messages 0 and 2

    @pytest.mark.asyncio
    async def test_parse_fetched_history_empty(self, history_fetcher):
        """Test parsing empty history"""
        assert await history_fetcher._parse_fetched_history([]) == []
        history_fetcher.downloader.download_attachment.assert_not_called()

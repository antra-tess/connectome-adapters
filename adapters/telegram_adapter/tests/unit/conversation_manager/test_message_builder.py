import pytest
from unittest.mock import MagicMock
from datetime import datetime

from adapters.telegram_adapter.adapter.conversation_manager.message_builder import MessageBuilder

class TestMessageBuilder:
    """Tests for the MessageBuilder class"""

    @pytest.fixture
    def builder(self):
        """Create a fresh MessageBuilder for each test"""
        return MessageBuilder()

    @pytest.fixture
    def mock_message(self):
        """Create a mock Telethon message"""
        message = MagicMock()
        message.id = 123
        message.message = "Test message content"
        message.date = datetime(2023, 1, 1, 12, 0, 0)
        reply_to = MagicMock()
        reply_to.reply_to_msg_id = 456
        message.reply_to = reply_to
        return message

    @pytest.fixture
    def mock_sender(self):
        """Create a mock sender info"""
        return {
            "user_id": 789,
            "display_name": "Test User",
            "is_bot": False
        }

    def test_initialization(self, builder):
        """Test that the builder initializes with empty message data"""
        assert isinstance(builder.message_data, dict)
        assert len(builder.message_data) == 0

    def test_reset(self, builder):
        """Test that the reset method clears message data"""
        builder.message_data["test"] = "value"
        builder.reset()

        assert len(builder.message_data) == 0
        assert builder.reset() is builder

    def test_with_basic_info(self, builder, mock_message):
        """Test adding basic message info"""
        result = builder.with_basic_info(mock_message, "conversation123")

        assert builder.message_data["message_id"] == "123"
        assert builder.message_data["conversation_id"] == "conversation123"
        assert builder.message_data["timestamp"] == mock_message.date
        assert result is builder

    def test_with_sender_info(self, builder, mock_sender):
        """Test adding sender information"""
        result = builder.with_sender_info(mock_sender)

        assert builder.message_data["sender_id"] == 789
        assert builder.message_data["sender_name"] == "Test User"
        assert builder.message_data["is_from_bot"] is False
        assert result is builder

    def test_with_sender_info_none(self, builder):
        """Test adding sender information when sender is None"""
        result = builder.with_sender_info(None)

        assert builder.message_data["is_from_bot"] is True
        assert result is builder

    def test_with_thread_info(self, builder, mock_message):
        """Test adding thread information"""
        result = builder.with_thread_info("thread123", mock_message)

        assert builder.message_data["thread_id"] == "thread123"
        assert builder.message_data["reply_to_message_id"] == 456
        assert result is builder

    def test_with_thread_info_no_thread(self, builder, mock_message):
        """Test adding thread info when thread_id is None"""
        result = builder.with_thread_info(None, mock_message)

        assert builder.message_data["thread_id"] is None
        assert "reply_to_message_id" not in builder.message_data
        assert result is builder

    def test_with_content(self, builder, mock_message):
        """Test adding message content"""
        result = builder.with_content(mock_message)

        assert builder.message_data["text"] == "Test message content"
        assert result is builder

    def test_with_content_no_message(self, builder):
        """Test adding content when message has no message attribute"""
        message = MagicMock()
        message.id = 123
        message = None

        result = builder.with_content(message)
        assert builder.message_data["text"] == ""
        assert result is builder

    def test_build(self, builder):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "123",
            "conversation_id": "conversation123",
            "text": "Test message"
        }

        result = builder.build()

        assert result is not builder.message_data
        assert result["message_id"] == "123"
        assert result["conversation_id"] == "conversation123"
        assert result["text"] == "Test message"

    def test_full_build_chain(self, builder, mock_message, mock_sender):
        """Test a complete builder chain"""
        result = builder.reset() \
            .with_basic_info(mock_message, "conversation123") \
            .with_sender_info(mock_sender) \
            .with_thread_info("thread123", mock_message) \
            .with_content(mock_message) \
            .build()

        assert result["message_id"] == "123"
        assert result["conversation_id"] == "conversation123"
        assert result["timestamp"] == mock_message.date
        assert result["sender_id"] == 789
        assert result["sender_name"] == "Test User"
        assert result["is_from_bot"] is False
        assert result["thread_id"] == "thread123"
        assert result["reply_to_message_id"] == 456
        assert result["text"] == "Test message content"

    def test_build_independence(self, builder):
        """Test that subsequent builds don't affect each other"""
        # First build
        builder.message_data = {"key": "value1"}
        first_result = builder.build()

        # Modify data and build again
        builder.message_data["key"] = "value2"
        second_result = builder.build()

        # Check first result is unchanged
        assert first_result["key"] == "value1"
        assert second_result["key"] == "value2"

        # Modify the result and check it doesn"t affect the builder
        first_result["new_key"] = "new_value"
        assert "new_key" not in builder.message_data

import pytest
from unittest.mock import MagicMock

from adapters.telegram_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UserInfo
)
from adapters.telegram_adapter.adapter.conversation_manager.user_builder import UserBuilder

class TestUserBuilder:
    """Tests for the UserBuilder class"""

    @pytest.fixture
    def mock_user(self):
        """Create a mock Telethon user"""
        user = MagicMock()
        user.id = 123
        user.username = "testuser"
        user.first_name = "Test"
        user.last_name = "User"
        user.bot = False
        return user

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info object"""
        return ConversationInfo(
            conversation_id="789",
            conversation_type="private"
        )

    @pytest.fixture
    def delta(self):
        """Create a conversation delta object"""
        return ConversationDelta(
            conversation_id="789", conversation_type="private"
        )

    def test_add_user_info_new_user(self, mock_user, conversation_info, delta):
        """Test adding a new user to conversation info"""
        assert len(conversation_info.known_members) == 0

        UserBuilder.add_user_info_to_conversation(mock_user, conversation_info, delta)

        assert "123" in conversation_info.known_members

        user_info = conversation_info.known_members["123"]
        assert user_info.user_id == "123"
        assert user_info.username == "testuser"
        assert user_info.first_name == "Test"
        assert user_info.last_name == "User"
        assert user_info.is_bot is False

        assert delta.sender["user_id"] == "123"
        assert delta.sender["display_name"] == "@testuser"  # Based on UserInfo.display_name
        assert delta.sender["is_bot"] is False

    def test_add_user_info_existing_user(self, mock_user, conversation_info, delta):
        """Test adding an existing user to conversation info"""
        user_info = UserInfo(str(mock_user.id))
        user_info.username = mock_user.username
        user_info.first_name = mock_user.first_name
        user_info.last_name = mock_user.last_name
        user_info.is_bot = mock_user.bot
        conversation_info.known_members[str(mock_user.id)] = user_info

        UserBuilder.add_user_info_to_conversation(mock_user, conversation_info, delta)

        assert delta.sender["user_id"] == "123"
        assert delta.sender["display_name"] == "@testuser"  # Based on UserInfo.display_name
        assert delta.sender["is_bot"] is False
        assert len(conversation_info.known_members) == 1

    def test_add_user_info_none(self, conversation_info, delta):
        """Test adding a None user to conversation info"""
        UserBuilder.add_user_info_to_conversation(None, conversation_info, delta)

        assert len(conversation_info.known_members) == 0
        assert delta.sender["user_id"] is None
        assert delta.sender["display_name"] == "Unknown"
        assert delta.sender["is_bot"] is False

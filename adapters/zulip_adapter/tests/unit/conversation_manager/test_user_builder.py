import pytest
from unittest.mock import MagicMock

from adapters.zulip_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UserInfo
)
from adapters.zulip_adapter.adapter.conversation_manager.user_builder import UserBuilder

class TestUserBuilder:
    """Tests for the UserBuilder class with Zulip message format"""

    @pytest.fixture
    def mock_zulip_private_message(self):
        """Create a mock Zulip private message"""
        return {
            "sender_id": 123,
            "is_me_message": False,
            "display_recipient": [
                {
                    "id": 123,
                    "email": "test@example.com",
                    "full_name": "Test User"
                },
                {
                    "id": 456,
                    "email": "other@example.com",
                    "full_name": "Other User"
                }
            ]
        }

    @pytest.fixture
    def mock_zulip_stream_message(self):
        """Create a mock Zulip stream message"""
        return {
            "sender_id": 123,
            "sender_full_name": "Test User",
            "is_me_message": False,
            "display_recipient": "General stream"  # Stream name
        }

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info object"""
        return ConversationInfo(
            conversation_id="123_456",
            conversation_type="private"
        )

    def test_add_user_info_new_user(self, mock_zulip_private_message, conversation_info):
        """Test adding a new user from a private message to conversation info"""
        assert len(conversation_info.known_members) == 0

        from_adapter = True
        UserBuilder.add_user_info_to_conversation(
            mock_zulip_private_message, conversation_info, from_adapter
        )

        assert "123" in conversation_info.known_members

        user_info = conversation_info.known_members["123"]
        assert user_info.user_id == "123"
        assert user_info.username == "Test User"  # In Zulip, we use full_name
        assert user_info.is_bot is True

    def test_add_user_info_existing_user(self, mock_zulip_private_message, conversation_info):
        """Test adding an existing user to conversation info"""
        user_info = UserInfo("123")
        user_info.username = "Existing User"
        user_info.is_bot = False
        conversation_info.known_members["123"] = user_info
        from_adapter = False

        UserBuilder.add_user_info_to_conversation(
            mock_zulip_private_message, conversation_info, from_adapter
        )

        assert len(conversation_info.known_members) == 1
        assert conversation_info.known_members["123"].username == "Existing User"

    def test_add_user_info_missing_sender_id(self, conversation_info):
        """Test adding a user with missing sender_id"""
        message = {
            "sender_full_name": "Test User",
            "display_recipient": []
        }
        from_adapter = False

        UserBuilder.add_user_info_to_conversation(
            message, conversation_info, from_adapter
        )

        assert len(conversation_info.known_members) == 0

    def test_add_user_info_non_list_recipient(self, conversation_info):
        """Test when display_recipient is not a list (stream case)"""
        message = {
            "sender_id": 123,
            "sender_full_name": "Test User",
            "display_recipient": "General stream"  # Stream name, not a list
        }
        from_adapter = False

        UserBuilder.add_user_info_to_conversation(
            message, conversation_info, from_adapter
        )

        assert "123" in conversation_info.known_members
        assert conversation_info.known_members["123"].username == "Test User"

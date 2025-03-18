import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum
from telethon.tl.types import ReactionEmoji

from adapters.telegram_adapter.adapter.event_processors.socket_io_events_processor import (
    SocketIoEventsProcessor, EventType
)

class TestSocketIoEventsProcessor:
    """Tests for the SocketIoEventsProcessor class"""

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked Telethon client"""
        client = AsyncMock()
        client.client = AsyncMock()
        client.send_message = AsyncMock()
        client.edit_message = AsyncMock()
        client.delete_messages = AsyncMock()
        client.get_messages = AsyncMock()
        client.get_entity = AsyncMock()
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.create_or_update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.conversations = {}
        return manager

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock()
        uploader.upload_attachment = AsyncMock()
        return uploader

    @pytest.fixture
    def processor(self,
                  patch_config,
                  telethon_client_mock,
                  conversation_manager_mock,
                  uploader_mock):
        """Create a SocketIoEventsProcessor with mocked dependencies"""
        with patch(
            "adapters.telegram_adapter.adapter.event_processors.socket_io_events_processor.Uploader"
        ) as UploaderMock:
            UploaderMock.return_value = uploader_mock

            return SocketIoEventsProcessor(
                patch_config,
                telethon_client_mock,
                conversation_manager_mock
            )

    @pytest.fixture
    def message_mock(self):
        """Create a mock message object"""
        message = MagicMock()
        message.id = 123
        message.chat_id = 456
        message.text = "Test message"
        return message

    @pytest.fixture
    def reaction_mock(self):
        """Create a mock reaction object"""
        reaction = MagicMock()
        results = []

        for emoji in ["👍", "❤️"]:
            result = MagicMock()
            result.reaction = MagicMock()
            result.reaction.emoticon = emoji
            results.append(result)

        reaction.results = results
        return reaction

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type", [
            EventType.SEND_MESSAGE,
            EventType.EDIT_MESSAGE,
            EventType.DELETE_MESSAGE,
            EventType.ADD_REACTION,
            EventType.REMOVE_REACTION
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type):
            """Test that process_event calls the correct handler method"""
            data = {"test": "data"}
            handler_mocks = {}

            for handler_type in EventType:
                method_name = f"_{handler_type.value}"
                handler_mock = AsyncMock(return_value=True)
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            assert await processor.process_event(event_type, data) is True
            handler_mocks[event_type].assert_called_once_with(data)

        @pytest.mark.asyncio
        async def test_process_event_unknown_type(self, processor):
            """Test handling an unknown event type"""
            assert await processor.process_event("unknown_type", {}) is False

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self,
                                            processor,
                                            telethon_client_mock,
                                            message_mock,
                                            uploader_mock):
            """Test sending a message with attachments"""
            telethon_client_mock.send_message.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            attachment_info = {
                "message": MagicMock(),
                "attachment_id": "123",
                "attachment_type": "photo"
            }
            uploader_mock.upload_attachment.return_value = attachment_info

            data = {
                "conversation_id": "123",
                "text": "Hello, world!",
                "thread_id": None,
                "attachments": [{"file_path": "/path/to/file.jpg"}]
            }

            with patch("asyncio.sleep"):
                assert await processor._send_message(data) is True

            telethon_client_mock.send_message.assert_called_once_with(
                entity="entity",
                message="Hello, world!",
                reply_to=None
            )
            uploader_mock.upload_attachment.assert_called_once()
            assert processor.conversation_manager.create_or_update_conversation.call_count == 2

        @pytest.mark.asyncio
        async def test_send_message_missing_required_fields(self, processor):
            """Test sending a message with missing required fields"""
            # Missing conversation_id
            assert await processor._send_message({"text": "Hello"}) is False

            # Missing text
            assert await processor._send_message({"conversation_id": "123"}) is False

        @pytest.mark.asyncio
        async def test_send_message_entity_not_found(self, processor, telethon_client_mock):
            """Test sending a message when entity can't be found"""
            telethon_client_mock.get_entity.return_value = None

            data = {
                "conversation_id": "123",
                "text": "Hello, world!"
            }

            assert await processor._send_message(data) is False
            telethon_client_mock.send_message.assert_not_called()

        @pytest.mark.asyncio
        async def test_send_message_exception(self, processor, telethon_client_mock):
            """Test handling an exception during send_message"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")

            data = {
                "conversation_id": "123",
                "text": "Hello, world!"
            }

            assert await processor._send_message(data) is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, telethon_client_mock, message_mock):
            """Test successfully editing a message"""
            telethon_client_mock.edit_message.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            data = {
                "conversation_id": "123",
                "message_id": "456",
                "text": "Updated text"
            }

            assert await processor._edit_message(data) is True
            telethon_client_mock.edit_message.assert_called_once_with(
                entity="entity",
                message=456,  # Should be converted to int
                text="Updated text"
            )
            processor.conversation_manager.create_or_update_conversation.assert_called_once_with(
                "edited_message", message_mock
            )

        @pytest.mark.asyncio
        async def test_edit_message_missing_required_fields(self, processor):
            """Test editing a message with missing required fields"""
            # Missing conversation_id
            assert await processor._edit_message({"message_id": "123", "text": "Hello"}) is False

            # Missing message_id
            assert await processor._edit_message({"conversation_id": "123", "text": "Hello"}) is False

            # Missing text
            assert await processor._edit_message({"conversation_id": "123", "message_id": "456"}) is False

        @pytest.mark.asyncio
        async def test_edit_message_entity_not_found(self, processor, telethon_client_mock):
            """Test editing a message when entity can't be found"""
            telethon_client_mock.get_entity.return_value = None

            data = {
                "conversation_id": "123",
                "message_id": "456",
                "text": "Updated text"
            }

            assert await processor._edit_message(data) is False
            telethon_client_mock.edit_message.assert_not_called()

        @pytest.mark.asyncio
        async def test_edit_message_exception(self, processor, telethon_client_mock):
            """Test handling an exception during edit_message"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")

            data = {
                "conversation_id": "123",
                "message_id": "456",
                "text": "Updated text"
            }

            assert await processor._edit_message(data) is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, telethon_client_mock):
            """Test successfully deleting a message"""
            telethon_client_mock.delete_messages.return_value = [MagicMock()]
            telethon_client_mock.get_entity.return_value = "entity"

            data = {
                "conversation_id": "123",
                "message_id": "456"
            }

            assert await processor._delete_message(data) is True
            telethon_client_mock.delete_messages.assert_called_once_with(
                entity="entity",
                message_ids=[456]  # Should be converted to int
            )
            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                [456], 123
            )

        @pytest.mark.asyncio
        async def test_delete_message_missing_required_fields(self, processor):
            """Test deleting a message with missing required fields"""
            # Missing conversation_id
            assert await processor._delete_message({"message_id": "123"}) is False

            # Missing message_id
            assert await processor._delete_message({"conversation_id": "123"}) is False

        @pytest.mark.asyncio
        async def test_delete_message_entity_not_found(self, processor, telethon_client_mock):
            """Test deleting a message when entity can't be found"""
            telethon_client_mock.get_entity.return_value = None

            data = {
                "conversation_id": "123",
                "message_id": "456"
            }

            assert await processor._delete_message(data) is False
            telethon_client_mock.delete_messages.assert_not_called()

        @pytest.mark.asyncio
        async def test_delete_message_exception(self, processor, telethon_client_mock):
            """Test handling an exception during delete_message"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")

            data = {
                "conversation_id": "123",
                "message_id": "456"
            }

            assert await processor._delete_message(data) is False

    class TestReactions:
        """Tests for reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, telethon_client_mock, message_mock):
            """Test successfully adding a reaction"""
            telethon_client_mock.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            data = {
                "conversation_id": "123",
                "message_id": "456",
                "emoji": "👍"
            }

            assert await processor._add_reaction(data) is True
            processor.conversation_manager.create_or_update_conversation.assert_called_once_with(
                "edited_message", message_mock
            )

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self,
                                               processor,
                                               telethon_client_mock,
                                               message_mock,
                                               reaction_mock):
            """Test successfully removing a reaction"""
            telethon_client_mock.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            old_message = MagicMock()
            old_message.reactions = reaction_mock
            telethon_client_mock.get_messages.return_value = old_message

            data = {
                "conversation_id": "123",
                "message_id": "456",
                "emoji": "👍"
            }

            with patch.object(processor, "_update_reactions_list") as mock_update_reactions:
                mock_update_reactions.return_value = [ReactionEmoji(emoticon="❤️")]
                assert await processor._remove_reaction(data) is True

            telethon_client_mock.get_messages.assert_called_once_with("entity", ids=456)
            mock_update_reactions.assert_called_once_with(reaction_mock, "👍")
            processor.conversation_manager.create_or_update_conversation.assert_called_once_with(
                "edited_message", message_mock
            )

        @pytest.mark.asyncio
        async def test_remove_reaction_no_reactions(self, processor, telethon_client_mock):
            """Test removing a reaction from a message with no reactions"""
            telethon_client_mock.get_entity.return_value = "entity"

            old_message = MagicMock()
            old_message.reactions = None
            telethon_client_mock.get_messages.return_value = old_message

            data = {
                "conversation_id": "123",
                "message_id": "456",
                "emoji": "👍"
            }

            assert await processor._remove_reaction(data) is True

        def test_update_reactions_list(self, processor, reaction_mock):
            """Test updating the reaction list"""
            result = processor._update_reactions_list(reaction_mock, "👍")
            assert len(result) == 1
            assert result[0].emoticon == "❤️"

            result = processor._update_reactions_list(reaction_mock, "🔥")
            assert len(result) == 2
            assert {r.emoticon for r in result} == {"👍", "❤️"}

            result = processor._update_reactions_list(None, "👍")
            result = processor._update_reactions_list(None, "👍")
            assert result == []

    class TestHelperMethods:
        """Tests for helper methods"""

        @pytest.mark.parametrize("conversation_id,expected", [
            ("123", 123),                       # Private chat
            ("987654321", 987654321),           # Unknown (try as int)
            ("not_a_number", "not_a_number"),   # Unknown (keep as string)
        ])
        def test_format_conversation_id(self, processor, conversation_id, expected):
            """Test formatting conversation IDs"""
            processor.conversation_manager.conversations = {
                "123": MagicMock(conversation_type="private"),
                "456": MagicMock(conversation_type="group"),
                "789": MagicMock(conversation_type="channel")
            }

            assert processor._format_conversation_id(conversation_id) == expected

        def test_format_conversation_id_group(self, processor):
            """Test formatting a group conversation ID"""
            processor.conversation_manager.conversations = {
                "456": MagicMock(conversation_type="group")
            }

            # Should be negative for groups
            assert processor._format_conversation_id("456") == -456

        def test_format_conversation_id_channel(self, processor):
            """Test formatting a channel conversation ID"""
            processor.conversation_manager.conversations = {
                "789": MagicMock(conversation_type="channel")
            }

            # Should be -100 prefix for channels
            assert processor._format_conversation_id("789") == -100789

        @pytest.mark.asyncio
        async def test_get_entity_success(self, processor, telethon_client_mock):
            """Test successfully getting an entity"""
            telethon_client_mock.get_entity.return_value = "test_entity"

            assert await processor._get_entity("123") == "test_entity"
            telethon_client_mock.get_entity.assert_called_once_with("123")

        @pytest.mark.asyncio
        async def test_get_entity_exception(self, processor, telethon_client_mock):
            """Test handling an exception when getting an entity"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")

            assert await processor._get_entity("123") is None
            telethon_client_mock.get_entity.assert_called_once_with("123")

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import emoji

from adapters.zulip_adapter.adapter.event_processors.socket_io_events_processor import (
    SocketIoEventsProcessor, EventType
)

class TestSocketIoEventsProcessor:
    """Tests for the SocketIoEventsProcessor class"""

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        client = AsyncMock()
        client.client = MagicMock()
        client.send_message = MagicMock(return_value={"result": "success"})
        client.update_message = MagicMock(return_value={"result": "success"})
        client.call_endpoint = MagicMock(return_value={"result": "success"})
        client.add_reaction = MagicMock(return_value={"result": "success"})
        client.remove_reaction = MagicMock(return_value={"result": "success"})
        client.get_user_by_id = MagicMock(return_value={
            "result": "success",
            "user": {"email": "test@example.com"}
        })
        client.get_streams = MagicMock(return_value={
            "result": "success",
            "streams": [{"stream_id": 789, "name": "test-stream"}]
        })
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.get_message = AsyncMock()
        manager.conversations = {}
        return manager

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock()
        uploader.upload_file = AsyncMock(return_value={"uri": "test-uri"})
        return uploader

    @pytest.fixture
    def processor(self,
                  patch_config,
                  zulip_client_mock,
                  conversation_manager_mock,
                  uploader_mock):
        """Create a SocketIoEventsProcessor with mocked dependencies"""
        with patch(
            "adapters.zulip_adapter.adapter.attachment_loaders.uploader.Uploader"
        ) as UploaderMock:
            UploaderMock.return_value = uploader_mock

            return SocketIoEventsProcessor(
                patch_config,
                zulip_client_mock,
                conversation_manager_mock
            )

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
        async def test_send_message_private_success(self, processor, zulip_client_mock):
            """Test sending a private message successfully"""
            data = {
                "conversation_id": "123_456",
                "text": "Hello, world!"
            }

            with patch("asyncio.sleep"):
                assert await processor._send_message(data) is True

            zulip_client_mock.send_message.assert_called_once_with({
                "type": "private",
                "to": ["test@example.com", "test@example.com"],
                "content": "Hello, world!",
                "subject": None
            })

        @pytest.mark.asyncio
        async def test_send_message_stream_success(self, processor, zulip_client_mock):
            """Test sending a stream message successfully"""
            data = {
                "conversation_id": "789/Some topic",
                "text": "Hello, stream!"
            }

            with patch("asyncio.sleep"):
                assert await processor._send_message(data) is True

            zulip_client_mock.send_message.assert_called_once_with({
                "type": "stream",
                "to": "test-stream",
                "content": "Hello, stream!",
                "subject": "Some topic"
            })

        @pytest.mark.asyncio
        async def test_send_message_long_text(self, processor, zulip_client_mock):
            """Test sending a message with text longer than max length"""
            data = {
                "conversation_id": "123_456",
                "text": "This is a sentence. " * 10
            }

            with patch("asyncio.sleep"):
                assert await processor._send_message(data) is True
            assert zulip_client_mock.send_message.call_count > 1

        @pytest.mark.asyncio
        async def test_send_message_missing_required_fields(self, processor):
            """Test sending a message with missing required fields"""
            # Missing conversation_id
            assert await processor._send_message({"text": "Hello"}) is False

            # Missing text
            assert await processor._send_message({"conversation_id": "123_456"}) is False

        @pytest.mark.asyncio
        async def test_send_message_api_failure(self, processor, zulip_client_mock):
            """Test sending a message when API fails"""
            zulip_client_mock.send_message.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "text": "Hello, world!"
            }

            assert await processor._send_message(data) is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, zulip_client_mock):
            """Test successfully editing a message"""
            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "text": "Updated text"
            }

            assert await processor._edit_message(data) is True

            zulip_client_mock.update_message.assert_called_once_with({
                "message_id": 789,  # Should be converted to int
                "content": "Updated text"
            })

        @pytest.mark.asyncio
        async def test_edit_message_missing_required_fields(self, processor):
            """Test editing a message with missing required fields"""
            # Missing conversation_id
            assert await processor._edit_message({"message_id": "789", "text": "Hello"}) is False

            # Missing message_id
            assert await processor._edit_message({"conversation_id": "123_456", "text": "Hello"}) is False

            # Missing text
            assert await processor._edit_message({"conversation_id": "123_456", "message_id": "789"}) is False

        @pytest.mark.asyncio
        async def test_edit_message_api_failure(self, processor, zulip_client_mock):
            """Test editing a message when API fails"""
            zulip_client_mock.update_message.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "text": "Updated text"
            }

            assert await processor._edit_message(data) is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, zulip_client_mock):
            """Test successfully deleting a message"""
            data = {
                "conversation_id": "123_456",
                "message_id": "789"
            }

            assert await processor._delete_message(data) is True

            zulip_client_mock.call_endpoint.assert_called_once_with(
                "messages/789",
                method="DELETE"
            )
            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                "789", "123_456"
            )

        @pytest.mark.asyncio
        async def test_delete_message_missing_required_fields(self, processor):
            """Test deleting a message with missing required fields"""
            # Missing conversation_id
            assert await processor._delete_message({"message_id": "789"}) is False

            # Missing message_id
            assert await processor._delete_message({"conversation_id": "123_456"}) is False

        @pytest.mark.asyncio
        async def test_delete_message_api_failure(self, processor, zulip_client_mock):
            """Test deleting a message when API fails"""
            zulip_client_mock.call_endpoint.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789"
            }

            assert await processor._delete_message(data) is False
            processor.conversation_manager.delete_from_conversation.assert_not_called()

    class TestReactions:
        """Tests for reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, zulip_client_mock):
            """Test successfully adding a reaction"""
            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            with patch.object(processor, "_get_emoji_name", return_value="thumbs_up"):
                assert await processor._add_reaction(data) is True

            zulip_client_mock.add_reaction.assert_called_once_with({
                "message_id": 789,
                "emoji_name": "thumbs_up"
            })

        @pytest.mark.asyncio
        async def test_add_reaction_missing_required_fields(self, processor):
            """Test adding a reaction with missing required fields"""
            # Missing conversation_id
            assert await processor._add_reaction({"message_id": "789", "emoji": "👍"}) is False

            # Missing message_id
            assert await processor._add_reaction({"conversation_id": "123_456", "emoji": "👍"}) is False

            # Missing emoji
            assert await processor._add_reaction({"conversation_id": "123_456", "message_id": "789"}) is False

        @pytest.mark.asyncio
        async def test_add_reaction_api_failure(self, processor, zulip_client_mock):
            """Test adding a reaction when API fails"""
            zulip_client_mock.add_reaction.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            assert await processor._add_reaction(data) is False

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self, processor, zulip_client_mock):
            """Test successfully removing a reaction"""
            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            # Patch the emoji name conversion
            with patch.object(processor, "_get_emoji_name", return_value="thumbs_up"):
                assert await processor._remove_reaction(data) is True

            zulip_client_mock.remove_reaction.assert_called_once_with({
                "message_id": 789,
                "emoji_name": "thumbs_up"
            })

        @pytest.mark.asyncio
        async def test_remove_reaction_missing_required_fields(self, processor):
            """Test removing a reaction with missing required fields"""
            # Missing conversation_id
            assert await processor._remove_reaction({"message_id": "789", "emoji": "👍"}) is False

            # Missing message_id
            assert await processor._remove_reaction({"conversation_id": "123_456", "emoji": "👍"}) is False

            # Missing emoji
            assert await processor._remove_reaction({"conversation_id": "123_456", "message_id": "789"}) is False

        @pytest.mark.asyncio
        async def test_remove_reaction_api_failure(self, processor, zulip_client_mock):
            """Test removing a reaction when API fails"""
            zulip_client_mock.remove_reaction.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            assert await processor._remove_reaction(data) is False

    class TestHelperMethods:
        """Tests for helper methods"""

        def test_validate_required_fields_success(self, processor):
            """Test validation with all required fields present"""
            data = {
                "field1": "value1",
                "field2": "value2",
                "field3": "value3"
            }
            
            assert processor._validate_required_fields(data, ["field1", "field2"], "test_operation") is True

        def test_validate_required_fields_missing(self, processor):
            """Test validation with missing required fields"""
            data = {
                "field1": "value1",
                "field3": "value3"
            }
            
            assert processor._validate_required_fields(data, ["field1", "field2"], "test_operation") is False

        def test_check_api_request_success(self, processor):
            """Test API response checking with success result"""
            result = {"result": "success"}
            assert processor._check_api_request_success(result, "test operation") is True

        def test_check_api_request_failure(self, processor):
            """Test API response checking with failure result"""
            result = {"result": "error", "msg": "Test error"}
            assert processor._check_api_request_success(result, "test operation") is False

        def test_check_api_request_none(self, processor):
            """Test API response checking with None result"""
            assert processor._check_api_request_success(None, "test operation") is False

        def test_get_private_to_field(self, processor, zulip_client_mock):
            """Test getting to field for private messages"""
            result = processor._get_private_to_field("123_456")
            assert result == ["test@example.com", "test@example.com"]
            assert zulip_client_mock.get_user_by_id.call_count == 2

        def test_get_stream_to_field(self, processor, zulip_client_mock):
            """Test getting to field for stream messages"""
            result = processor._get_stream_to_field("789")
            assert result == "test-stream"
            zulip_client_mock.get_streams.assert_called_once()

        def test_split_long_message_short(self, processor):
            """Test splitting a message that's already short enough"""
            text = "This is a short message."
            result = processor._split_long_message(text)
            assert result == [text]

        def test_split_long_message_long(self, processor):
            """Test splitting a long message at sentence boundaries"""
            result = processor._split_long_message("First sentence. Second sentence. " * 100)

            assert len(result) > 1
            for part in result[:-1]:
                    assert part.endswith(". ")

        def test_get_emoji_name(self, processor):
            """Test converting emoji to name"""
            with patch("emoji.demojize", return_value="+1"):
                assert processor._get_emoji_name("👍") == "thumbs_up"
            with patch("emoji.demojize", return_value="-1"):
                assert processor._get_emoji_name("👎") == "thumbs_down"
            with patch("emoji.demojize", return_value="smile"):
                assert processor._get_emoji_name("😊") == "smile"

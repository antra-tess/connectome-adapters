import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import emoji

from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.zulip_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
from adapters.zulip_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from core.event_processors.base_outgoing_event_processor import OutgoingEventType

class TestOutgoingEventProcessor:
    """Tests for the OutgoingEventProcessor class"""

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
        return client

    @pytest.fixture
    def private_conversation_mock(self):
        """Create a mocked private conversation"""
        conversation = MagicMock()
        conversation.conversation_type = "private"
        conversation.to_fields.return_value = ["test@example.com", "test@example.com"]
        return conversation

    @pytest.fixture
    def stream_conversation_mock(self):
        """Create a mocked stream conversation"""
        conversation = MagicMock()
        conversation.conversation_type = "stream"
        conversation.to_fields.return_value = "test-stream"
        conversation.conversation_id = "789/Some topic"
        return conversation

    @pytest.fixture
    def conversation_manager_mock(self, private_conversation_mock, stream_conversation_mock):
        """Create a mocked conversation manager"""
        manager = AsyncMock()

        def get_conversation_side_effect(conversation_id):
            if conversation_id == "123_456":
                return private_conversation_mock
            elif conversation_id == "789/Some topic":
                return stream_conversation_mock
            return None

        manager.get_conversation = MagicMock(side_effect=get_conversation_side_effect)
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.get_message = AsyncMock()
        return manager

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock()
        uploader.upload_file = AsyncMock(return_value={"uri": "test-uri"})
        return uploader

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def processor(self,
                  patch_config,
                  zulip_client_mock,
                  conversation_manager_mock,
                  uploader_mock,
                  rate_limiter_mock):
        """Create a ZulipOutgoingEventProcessor with mocked dependencies"""
        with patch.object(Uploader, "__new__", return_value=uploader_mock):
            processor = OutgoingEventProcessor(
                patch_config, zulip_client_mock, conversation_manager_mock
            )
            processor.rate_limiter = rate_limiter_mock
            return processor

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type", [
            OutgoingEventType.SEND_MESSAGE,
            OutgoingEventType.EDIT_MESSAGE,
            OutgoingEventType.DELETE_MESSAGE,
            OutgoingEventType.ADD_REACTION,
            OutgoingEventType.REMOVE_REACTION
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type):
            """Test that process_event calls the correct handler method"""
            data = {"test": "data"}
            handler_mocks = {}

            for handler_type in OutgoingEventType:
                method_name = f"_handle_{handler_type.value}_event"
                handler_mock = AsyncMock(return_value={"request_completed": True})
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            response = await processor.process_event(event_type, data)
            assert response["request_completed"] is True
            handler_mocks[event_type].assert_called_once_with(data)

        @pytest.mark.asyncio
        async def test_process_event_unknown_type(self, processor):
            """Test handling an unknown event type"""
            response = await processor.process_event("unknown_type", {})
            assert response["request_completed"] is False

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
                response = await processor.process_event(OutgoingEventType.SEND_MESSAGE, data)
                assert response["request_completed"] is True

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
                response = await processor.process_event(OutgoingEventType.SEND_MESSAGE, data)
                assert response["request_completed"] is True

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
                response = await processor.process_event(OutgoingEventType.SEND_MESSAGE, data)
                assert response["request_completed"] is True
            assert zulip_client_mock.send_message.call_count > 1

        @pytest.mark.asyncio
        async def test_send_message_missing_required_fields(self, processor):
            """Test sending a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event(
                OutgoingEventType.SEND_MESSAGE, {"text": "Hello"}
            )
            assert response["request_completed"] is False

            # Missing text
            response = await processor.process_event(
                OutgoingEventType.SEND_MESSAGE, {"conversation_id": "123_456"}
            )
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_send_message_api_failure(self, processor, zulip_client_mock):
            """Test sending a message when API fails"""
            zulip_client_mock.send_message.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "text": "Hello, world!"
            }

            response = await processor.process_event(OutgoingEventType.SEND_MESSAGE, data)
            assert response["request_completed"] is False

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

            response = await processor.process_event(OutgoingEventType.EDIT_MESSAGE, data)
            assert response["request_completed"] is True
            zulip_client_mock.update_message.assert_called_once_with({
                "message_id": 789,  # Should be converted to int
                "content": "Updated text"
            })

        @pytest.mark.asyncio
        async def test_edit_message_missing_required_fields(self, processor):
            """Test editing a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event(
                OutgoingEventType.EDIT_MESSAGE, {"message_id": "789", "text": "Hello"}
            )
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event(
                OutgoingEventType.EDIT_MESSAGE, {"conversation_id": "123_456", "text": "Hello"}
            )
            assert response["request_completed"] is False

            # Missing text
            response = await processor.process_event(
                OutgoingEventType.EDIT_MESSAGE, {"conversation_id": "123_456", "message_id": "789"}
            )
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_edit_message_api_failure(self, processor, zulip_client_mock):
            """Test editing a message when API fails"""
            zulip_client_mock.update_message.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "text": "Updated text"
            }

            response = await processor.process_event(OutgoingEventType.EDIT_MESSAGE, data)
            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, zulip_client_mock):
            """Test successfully deleting a message"""
            data = {
                "conversation_id": "123_456",
                "message_id": "789"
            }

            response = await processor.process_event(OutgoingEventType.DELETE_MESSAGE, data)
            assert response["request_completed"] is True

            zulip_client_mock.call_endpoint.assert_called_once_with("messages/789",method="DELETE")
            processor.conversation_manager.delete_from_conversation.assert_called_once_with(outgoing_event=data)

        @pytest.mark.asyncio
        async def test_delete_message_missing_required_fields(self, processor):
            """Test deleting a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event(
                OutgoingEventType.DELETE_MESSAGE, {"message_id": "789"}
            )
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event(
                OutgoingEventType.DELETE_MESSAGE, {"conversation_id": "123_456"}
            )
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_delete_message_api_failure(self, processor, zulip_client_mock):
            """Test deleting a message when API fails"""
            zulip_client_mock.call_endpoint.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789"
            }

            response = await processor.process_event(OutgoingEventType.DELETE_MESSAGE, data)
            assert response["request_completed"] is False
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
                response = await processor.process_event(OutgoingEventType.ADD_REACTION, data)
                assert response["request_completed"] is True

            zulip_client_mock.add_reaction.assert_called_once_with({
                "message_id": 789,
                "emoji_name": "thumbs_up"
            })

        @pytest.mark.asyncio
        async def test_add_reaction_missing_required_fields(self, processor):
            """Test adding a reaction with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event(
                OutgoingEventType.ADD_REACTION, {"message_id": "789", "emoji": "👍"}
            )
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event(
                OutgoingEventType.ADD_REACTION, {"conversation_id": "123_456", "emoji": "👍"}
            )
            assert response["request_completed"] is False

            # Missing emoji
            response = await processor.process_event(
                OutgoingEventType.ADD_REACTION, {"conversation_id": "123_456", "message_id": "789"}
            )
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_add_reaction_api_failure(self, processor, zulip_client_mock):
            """Test adding a reaction when API fails"""
            zulip_client_mock.add_reaction.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            response = await processor.process_event(OutgoingEventType.ADD_REACTION, data)
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self, processor, zulip_client_mock):
            """Test successfully removing a reaction"""
            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            with patch.object(processor, "_get_emoji_name", return_value="thumbs_up"):
                response = await processor.process_event(OutgoingEventType.REMOVE_REACTION, data)
                assert response["request_completed"] is True

            zulip_client_mock.remove_reaction.assert_called_once_with({
                "message_id": 789,
                "emoji_name": "thumbs_up"
            })

        @pytest.mark.asyncio
        async def test_remove_reaction_missing_required_fields(self, processor):
            """Test removing a reaction with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event(
                OutgoingEventType.REMOVE_REACTION, {"message_id": "789", "emoji": "👍"}
            )
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event(
                OutgoingEventType.REMOVE_REACTION, {"conversation_id": "123_456", "emoji": "👍"}
            )
            assert response["request_completed"] is False

            # Missing emoji
            response = await processor.process_event(
                OutgoingEventType.REMOVE_REACTION, {"conversation_id": "123_456", "message_id": "789"}
            )

        @pytest.mark.asyncio
        async def test_remove_reaction_api_failure(self, processor, zulip_client_mock):
            """Test removing a reaction when API fails"""
            zulip_client_mock.remove_reaction.return_value = {"result": "error", "msg": "Test error"}

            data = {
                "conversation_id": "123_456",
                "message_id": "789",
                "emoji": "👍"
            }

            response = await processor.process_event(OutgoingEventType.REMOVE_REACTION, data)
            assert response["request_completed"] is False

    class TestFetchHistory:
        """Tests for the fetch_history method"""

        @pytest.mark.asyncio
        async def test_fetch_history(self, processor):
            """Test fetching history with process_event"""
            mock_history = [
                {
                    "message_id": "1001",
                    "conversation_id": "123_456",
                    "sender": {"user_id": "123", "display_name": "User One"},
                    "text": "Message 1",
                    "timestamp": 1627984000,
                    "attachments": []
                },
                {
                    "message_id": "1002",
                    "conversation_id": "123_456",
                    "sender": {"user_id": "456", "display_name": "User Two"},
                    "text": "Message 2",
                    "timestamp": 1627984100,
                    "attachments": []
                }
            ]
            data = {
                "conversation_id": "123_456",
                "before": 1627985000
            }

            with patch.object(HistoryFetcher, "fetch", AsyncMock(return_value=mock_history)):
                result = await processor.process_event(OutgoingEventType.FETCH_HISTORY, data)

                assert result["request_completed"] is True
                assert result["history"] == mock_history

        @pytest.mark.asyncio
        async def test_fetch_history_missing_parameters(self, processor):
            """Test fetching history with missing parameters"""
            data = {"conversation_id": "123_456"}

            result = await processor.process_event(OutgoingEventType.FETCH_HISTORY, data)
            assert result["request_completed"] is False

    class TestHelperMethods:
        """Tests for helper methods"""

        def test_validate_fields_success(self, processor):
            """Test validation with all required fields present"""
            data = {
                "field1": "value1",
                "field2": "value2",
                "field3": "value3"
            }

            assert processor._validate_fields(data, ["field1", "field2"], "test_operation") is True

        def test_validate_fields_missing(self, processor):
            """Test validation with missing required fields"""
            data = {
                "field1": "value1",
                "field3": "value3"
            }

            assert processor._validate_fields(data, ["field1", "field2"], "test_operation") is False

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

        def test_split_long_message_short(self, processor):
            """Test splitting a message that's already short enough"""
            text = "This is a short message."
            assert processor._split_long_message(text) == [text]

        def test_split_long_message_long(self, processor):
            """Test splitting a long message at sentence boundaries"""
            result = processor._split_long_message("First sentence. Second sentence. " * 100)

            assert len(result) > 1
            assert (result[-1].endswith(". ") or result[-1].endswith("."))

        def test_get_emoji_name(self, processor):
            """Test converting emoji to name"""
            with patch("emoji.demojize", return_value="+1"):
                assert processor._get_emoji_name("👍") == "thumbs_up"
            with patch("emoji.demojize", return_value="-1"):
                assert processor._get_emoji_name("👎") == "thumbs_down"
            with patch("emoji.demojize", return_value="smile"):
                assert processor._get_emoji_name("😊") == "smile"

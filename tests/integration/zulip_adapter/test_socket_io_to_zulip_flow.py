import emoji
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.adapters.zulip_adapter.adapter import Adapter
from src.adapters.zulip_adapter.conversation.data_classes import ConversationInfo
from src.adapters.zulip_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from src.adapters.zulip_adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from src.core.conversation.base_data_classes import UserInfo
from src.core.utils.emoji_converter import EmojiConverter

class TestSocketIOToZulipFlowIntegration:
    """Integration tests for socket.io to Zulip flow"""

    # =============== FIXTURES ===============

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit = MagicMock()
        return socketio

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        client.send_message = MagicMock(return_value={"result": "success", "id": 123})
        client.update_message = MagicMock(return_value={"result": "success"})
        client.call_endpoint = MagicMock(return_value={"result": "success"})
        client.add_reaction = MagicMock(return_value={"result": "success"})
        client.remove_reaction = MagicMock(return_value={"result": "success"})
        client.get_messages = MagicMock(return_value={"result": "success", "messages": []})
        return client

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked Uploader"""
        uploader_mock = AsyncMock()

        async def mock_upload_attachment(attachment):
            return "/user_uploads/test.txt"
        uploader_mock.upload_attachment.side_effect = mock_upload_attachment

        return uploader_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def emoji_converter_mock(self):
        """Create a fully mocked EmojiConverter"""
        converter = MagicMock()
        converter.platform_specific_to_standard.side_effect = lambda x: {
            "+1": "thumbs_up",
            "-1": "thumbs_down",
            "heart": "red_heart"
        }.get(x, x)
        converter.standard_to_platform_specific.side_effect = lambda x: {
            "thumbs_up": "+1",
            "thumbs_down": "-1",
            "red_heart": "heart"
        }.get(x, x)
        return converter

    @pytest.fixture
    def adapter(self,
                zulip_config,
                socketio_mock,
                zulip_client_mock,
                uploader_mock,
                rate_limiter_mock):
        """Create a Zulip adapter with mocked dependencies"""
        adapter = Adapter(zulip_config, socketio_mock)
        adapter.client = zulip_client_mock
        adapter.rate_limiter = rate_limiter_mock

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            zulip_config, zulip_client_mock, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.rate_limiter = rate_limiter_mock
        adapter.outgoing_events_processor.uploader = uploader_mock

        adapter.incoming_events_processor = IncomingEventProcessor(
            zulip_config, zulip_client_mock, adapter.conversation_manager
        )
        adapter.incoming_events_processor.rate_limiter = rate_limiter_mock

        return adapter

    @pytest.fixture
    def setup_private_conversation(self, adapter):
        """Setup a test private conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="101_102",
                conversation_type="private",
                known_members={
                    "101": UserInfo(user_id="101", username="Test User", email="test@example.com"),
                    "102": UserInfo(user_id="102", username="Bot User", email="bot@example.com")
                }
            )
            adapter.conversation_manager.conversations["101_102"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_stream_conversation(self, adapter):
        """Setup a test stream conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="201/Test Topic",
                conversation_type="stream",
                conversation_name="Test Stream"
            )
            adapter.conversation_manager.conversations["201/Test Topic"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(conversation_id, message_id="12345", reactions=None):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "text": "Test message",
                "sender_id": "101",
                "sender_name": "Test User",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "is_from_bot": False
            })

            if reactions is not None:
                cached_msg.reactions = reactions

            if conversation_id in adapter.conversation_manager.conversations:
                adapter.conversation_manager.conversations[conversation_id].messages.add(message_id)

            return cached_msg
        return _setup

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_send_private_message_flow(self, adapter, zulip_client_mock, setup_private_conversation):
        """Test the complete flow from socket.io send_message to Zulip for private messages"""
        setup_private_conversation()

        response = await adapter.outgoing_events_processor.process_event({
            "event_type": "send_message",
            "data": {
                "conversation_id": "101_102",
                "text": "Hello, world!"
            }
        })
        assert response["request_completed"] is True
        assert response["message_ids"] == ["123"]

        zulip_client_mock.send_message.assert_called_once_with({
            "type": "private",
            "to": ["test@example.com", "bot@example.com"],
            "content": "Hello, world!",
            "subject": None
        })

    @pytest.mark.asyncio
    async def test_send_stream_message_flow(self, adapter, zulip_client_mock, setup_stream_conversation):
        """Test the complete flow from socket.io send_message to Zulip for stream messages"""
        setup_stream_conversation()

        response = await adapter.outgoing_events_processor.process_event({
            "event_type": "send_message",
            "data": {
                "conversation_id": "201/Test Topic",
                "text": "Hello, stream!"
            }
        })
        assert response["request_completed"] is True
        assert response["message_ids"] == ["123"]

        zulip_client_mock.send_message.assert_called_once_with({
            "type": "stream",
            "to": "Test Stream",
            "content": "Hello, stream!",
            "subject": "Test Topic"
        })

    @pytest.mark.asyncio
    async def test_send_message_with_attachment_flow(self, adapter, zulip_client_mock, setup_private_conversation):
        """Test sending a message with an attachment"""
        setup_private_conversation()

        response = await adapter.outgoing_events_processor.process_event({
            "event_type": "send_message",
            "data": {
                "conversation_id": "101_102",
                "text": "See attachment",
                "attachments": [
                    {
                        "file_name": "test.txt",
                        "content": "dGVzdAo="
                    }
                ]
            }
        })
        assert response["request_completed"] is True
        assert response["message_ids"] == ["123"]

        adapter.outgoing_events_processor.uploader.upload_attachment.assert_called_once()
        zulip_client_mock.send_message.assert_called_once()

        call_args = zulip_client_mock.send_message.call_args[0][0]
        assert call_args["type"] == "private"
        assert call_args["to"] == ["test@example.com", "bot@example.com"]
        assert "See attachment" in call_args["content"]
        assert "/user_uploads/test.txt" in call_args["content"]

    @pytest.mark.asyncio
    async def test_edit_message_flow(self, adapter, zulip_client_mock, setup_private_conversation, setup_message):
        """Test the complete flow from socket.io edit_message to Zulip call"""
        setup_private_conversation()
        await setup_message("101_102")

        response = await adapter.outgoing_events_processor.process_event({
            "event_type": "edit_message",
            "data": {
                "conversation_id": "101_102",
                "message_id": "12345",
                "text": "Edited message content"
            }
        })
        assert response["request_completed"] is True

        zulip_client_mock.update_message.assert_called_once_with({
            "message_id": 12345,  # Should be converted to int
            "content": "Edited message content"
        })

    @pytest.mark.asyncio
    async def test_delete_message_flow(self, adapter, zulip_client_mock, setup_private_conversation, setup_message):
        """Test the complete flow from socket.io delete_message to Zulip call"""
        setup_private_conversation()
        await setup_message("101_102")

        response = await adapter.outgoing_events_processor.process_event({
            "event_type": "delete_message",
            "data": {
                "conversation_id": "101_102",
                "message_id": "12345"
            }
        })
        assert response["request_completed"] is True

        zulip_client_mock.call_endpoint.assert_called_once_with(
            "messages/12345",
            method="DELETE"
        )

    @pytest.mark.asyncio
    async def test_add_reaction_flow(self,
                                     adapter,
                                     zulip_client_mock,
                                     emoji_converter_mock,
                                     setup_private_conversation,
                                     setup_message):
        """Test the complete flow from socket.io add_reaction to Zulip call"""
        setup_private_conversation()
        await setup_message("101_102")

        with patch.object(EmojiConverter, "get_instance", return_value=emoji_converter_mock):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "add_reaction",
                "data": {
                    "conversation_id": "101_102",
                    "message_id": "12345",
                    "emoji": "thumbs_up"
                }
            })
            assert response["request_completed"] is True

            zulip_client_mock.add_reaction.assert_called_once_with({
                "message_id": 12345,
                "emoji_name": "+1"
            })

    @pytest.mark.asyncio
    async def test_remove_reaction_flow(self,
                                        adapter,
                                        zulip_client_mock,
                                        emoji_converter_mock,
                                        setup_private_conversation,
                                        setup_message):
        """Test the complete flow from socket.io remove_reaction to Zulip call"""
        setup_private_conversation()
        await setup_message("101_102", reactions={"thumbs_up": 1})

        with patch.object(EmojiConverter, "get_instance", return_value=emoji_converter_mock):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "remove_reaction",
                "data": {
                    "conversation_id": "101_102",
                    "message_id": "12345",
                    "emoji": "thumbs_up"
                }
            })
            assert response["request_completed"] is True

            zulip_client_mock.remove_reaction.assert_called_once_with({
                "message_id": 12345,
                "emoji_name": "+1"
            })

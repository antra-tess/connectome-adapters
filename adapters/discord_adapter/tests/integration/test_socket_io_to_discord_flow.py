import asyncio
import discord
import os
import pytest
import shutil

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from adapters.discord_adapter.adapter.adapter import Adapter
from adapters.discord_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.discord_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor

class TestSocketIOToDiscordFlowIntegration:
    """Integration tests for socket.io to Discord flow"""

    # =============== FIXTURES ===============

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/image", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit_event = MagicMock()
        return socketio

    @pytest.fixture
    def discord_bot_mock(self):
        """Create a mocked Discord bot"""
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 12345678
        bot.user.name = "Test Bot"
        return bot

    @pytest.fixture
    def discord_client_mock(self, discord_bot_mock):
        """Create a mocked Discord client"""
        client = MagicMock()
        client.bot = discord_bot_mock
        client.running = True
        return client

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked Uploader"""
        uploader_mock = MagicMock(spec=Uploader)
        uploader_mock.upload_attachment = MagicMock(return_value=[])
        uploader_mock.clean_up_uploaded_files = MagicMock()
        return uploader_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self,
                patch_config,
                socketio_mock,
                discord_client_mock,
                uploader_mock,
                rate_limiter_mock):
        """Create a Discord adapter with mocked dependencies"""
        adapter = Adapter(patch_config, socketio_mock)
        adapter.client = discord_client_mock
        adapter.rate_limiter = rate_limiter_mock

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            patch_config, discord_client_mock.bot, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.uploader = uploader_mock

        adapter.incoming_events_processor = IncomingEventProcessor(
            patch_config, discord_client_mock.bot, adapter.conversation_manager
        )

        return adapter

    @pytest.fixture
    def setup_channel_conversation(self, adapter):
        """Setup a test channel conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="987654321/123456789",
                conversation_type="channel",
                conversation_name="general"
            )
            adapter.conversation_manager.conversations["987654321/123456789"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(conversation_id, message_id="111222333", reactions=None):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "text": "Test message",
                "sender_id": "123456789",
                "sender_name": "Test User",
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                "is_from_bot": False
            })

            if reactions is not None:
                cached_msg.reactions = reactions

            if conversation_id in adapter.conversation_manager.conversations:
                adapter.conversation_manager.conversations[conversation_id].messages.add(message_id)

            return cached_msg
        return _setup

    @pytest.fixture
    def channel_mock(self):
        """Create a mocked Discord channel with proper async methods"""
        channel = AsyncMock()
        channel.send = AsyncMock(return_value=MagicMock())

        message = MagicMock()
        message.edit = AsyncMock(return_value=MagicMock())
        message.delete = AsyncMock(return_value=MagicMock())
        message.add_reaction = AsyncMock(return_value=MagicMock())
        message.remove_reaction = AsyncMock(return_value=MagicMock())

        channel.fetch_message = AsyncMock(return_value=message)

        return channel

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_send_message_with_attachment_flow(self,
                                                     adapter,
                                                     setup_channel_conversation,
                                                     channel_mock,
                                                     uploader_mock):
        """Test sending a message with an attachment"""
        setup_channel_conversation()

        mock_file = MagicMock()
        uploader_mock.upload_attachment.return_value = [mock_file]

        with patch.object(
            adapter.outgoing_events_processor,
            '_get_channel',
            return_value=channel_mock
        ):
            response = await adapter.process_outgoing_event(
                "send_message",
                {
                    "conversation_id": "987654321/123456789",
                    "text": "See attachment",
                    "attachments": [
                        {
                            "attachment_type": "image",
                            "file_path": "test_attachments/image/test.jpg",
                            "size": 12345
                        }
                    ]
                }
            )
            assert response["request_completed"] is True

            uploader_mock.upload_attachment.assert_called_once()
            uploader_mock.clean_up_uploaded_files.assert_called_once()

            channel_mock.send.assert_any_call("See attachment")
            channel_mock.send.assert_any_call(files=[mock_file])

    @pytest.mark.asyncio
    async def test_edit_message_flow(self,
                                     adapter,
                                     setup_channel_conversation,
                                     setup_message,
                                     channel_mock):
        """Test the complete flow from socket.io edit_message to Discord call"""
        setup_channel_conversation()
        await setup_message("987654321/123456789")

        with patch.object(
            adapter.outgoing_events_processor,
            '_get_channel',
            return_value=channel_mock
        ):
            response = await adapter.process_outgoing_event(
                "edit_message",
                {
                    "conversation_id": "987654321/123456789",
                    "message_id": "111222333",
                    "text": "Edited message content"
                }
            )
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.edit.assert_called_once_with(content="Edited message content")

    @pytest.mark.asyncio
    async def test_delete_message_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       setup_message,
                                       channel_mock):
        """Test the complete flow from socket.io delete_message to Discord call"""
        setup_channel_conversation()
        await setup_message("987654321/123456789")

        with patch.object(
            adapter.outgoing_events_processor,
            '_get_channel',
            return_value=channel_mock
        ):
            response = await adapter.process_outgoing_event(
                "delete_message",
                {
                    "conversation_id": "987654321/123456789",
                    "message_id": "111222333"
                }
            )
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_reaction_flow(self,
                                     adapter,
                                     setup_channel_conversation,
                                     setup_message,
                                     channel_mock):
        """Test the complete flow from socket.io add_reaction to Discord call"""
        setup_channel_conversation()
        await setup_message("987654321/123456789")

        with patch.object(
            adapter.outgoing_events_processor,
            '_get_channel',
            return_value=channel_mock
        ):
            response = await adapter.process_outgoing_event(
                "add_reaction",
                {
                    "conversation_id": "987654321/123456789",
                    "message_id": "111222333",
                    "emoji": "👍"
                }
            )
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.add_reaction.assert_called_once_with("👍")

    @pytest.mark.asyncio
    async def test_remove_reaction_flow(self,
                                        adapter,
                                        setup_channel_conversation,
                                        setup_message,
                                        channel_mock):
        """Test the complete flow from socket.io remove_reaction to Discord call"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", reactions={"👍": 1})

        with patch.object(
            adapter.outgoing_events_processor,
            '_get_channel',
            return_value=channel_mock
        ):
            response = await adapter.process_outgoing_event(
                "remove_reaction",
                {
                    "conversation_id": "987654321/123456789",
                    "message_id": "111222333",
                    "emoji": "👍"
                }
            )
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.remove_reaction.assert_called_once_with("👍", adapter.client.bot.user)

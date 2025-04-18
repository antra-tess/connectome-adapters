import discord
import os
import pytest
import shutil
from unittest.mock import AsyncMock, MagicMock, patch, call

from adapters.discord_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.discord_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from core.event_processors.base_outgoing_event_processor import OutgoingEventType

class TestOutgoingEventProcessor:
    """Tests for the Discord OutgoingEventProcessor class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def discord_client_mock(self):
        """Create a mocked Discord client"""
        client = AsyncMock()
        client.user = MagicMock()
        channel_mock = AsyncMock()
        channel_mock.send = AsyncMock()
        channel_mock.fetch_message = AsyncMock()
        client.get_channel = MagicMock(return_value=channel_mock)
        client.fetch_channel = AsyncMock(return_value=channel_mock)
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        return manager

    @pytest.fixture
    def channel_mock(self):
        """Create a mocked Discord channel"""
        channel = AsyncMock()
        channel.send = AsyncMock(return_value=MagicMock(id=999))
        message_mock = AsyncMock()
        message_mock.edit = AsyncMock()
        message_mock.delete = AsyncMock()
        message_mock.add_reaction = AsyncMock()
        message_mock.remove_reaction = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=message_mock)
        return channel

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock()
        return rate_limiter

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = MagicMock()
        uploader.upload_attachment = MagicMock(return_value=[])
        uploader.clean_up_uploaded_files = MagicMock()
        return uploader

    @pytest.fixture
    def processor(self,
                  patch_config,
                  discord_client_mock,
                  conversation_manager_mock,
                  channel_mock,
                  rate_limiter_mock,
                  uploader_mock):
        """Create a DiscordOutgoingEventProcessor with mocked dependencies"""
        with patch.object(Uploader, "upload_attachment", return_value=[]):
            processor = OutgoingEventProcessor(
                patch_config, discord_client_mock, conversation_manager_mock
            )
            processor._get_channel = AsyncMock(return_value=channel_mock)
            processor.rate_limiter = rate_limiter_mock
            processor.uploader = uploader_mock
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
        async def test_process_unknown_event_type(self, processor):
            """Test handling an unknown event type"""
            response = await processor.process_event("unknown_type", {})
            assert response["request_completed"] is False

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self, processor, channel_mock):
            """Test sending a simple message successfully"""
            response = await processor._handle_send_message_event({
                "conversation_id": "123456789",
                "text": "Hello, world!"
            })
            assert response["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_once_with(
                "message", "123456789"
            )
            channel_mock.send.assert_called_once_with("Hello, world!")

        @pytest.mark.asyncio
        async def test_send_message_long_text(self, processor, channel_mock):
            """Test sending a message with text longer than max length"""
            data = {
                "conversation_id": "123456789",
                "text": "This is a sentence. " * 100  # Well over Discord's limit
            }

            with patch.object(processor, "_split_long_message", return_value=["Part 1", "Part 2"]):
                response = await processor._handle_send_message_event(data)
                assert response["request_completed"] is True

            assert channel_mock.send.call_count == 2
            channel_mock.send.assert_has_calls([call("Part 1"), call("Part 2")])

        @pytest.mark.asyncio
        async def test_send_message_with_attachments(self, processor, channel_mock):
            """Test sending a message with attachments"""
            attachments = [
                {
                    "attachment_type": "document",
                    "file_path": "test_attachments/document/file1.txt",
                    "size": 100
                }
            ]
            data = {
                "conversation_id": "123456789",
                "text": "Message with attachments",
                "attachments": attachments
            }

            with patch('os.remove'):
                response = await processor._handle_send_message_event(data)
                assert response["request_completed"] is True
                assert channel_mock.send.call_count == 2

                processor.uploader.upload_attachment.assert_called_once_with(attachments)
                processor.uploader.clean_up_uploaded_files.assert_called_once_with(attachments)

        @pytest.mark.asyncio
        async def test_send_message_with_many_attachments(self,
                                                          processor,
                                                          channel_mock,
                                                          uploader_mock):
            """Test sending a message with many attachments that need to be chunked"""
            attachments = [
                {
                    "attachment_type": "document",
                    "file_path": f"test_attachments/document/file{i}.txt",
                    "size": 100
                } for i in range(2)
            ]

            data = {
                "conversation_id": "123456789",
                "text": "Message with many attachments",
                "attachments": attachments
            }

            # patch_config sets attachment limit to 1, so even 2 files will be chunked
            chunk1_files = [MagicMock()]
            chunk2_files = [MagicMock()]

            uploader_mock.upload_attachment.side_effect = [
                chunk1_files, chunk2_files
            ]

            with patch('os.remove'):
                response = await processor._handle_send_message_event(data)
                assert response["request_completed"] is True
                assert channel_mock.send.call_count == 3
                assert uploader_mock.upload_attachment.call_count == 2
                uploader_mock.clean_up_uploaded_files.assert_called_once_with(attachments)

        @pytest.mark.asyncio
        async def test_send_message_channel_not_found(self, processor):
            """Test sending a message when channel isn't found"""
            data = {
                "conversation_id": "999999",
                "text": "Hello, world!"
            }
            processor._get_channel.side_effect = Exception("Channel not found")

            response = await processor._handle_send_message_event(data)
            assert response["request_completed"] is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, channel_mock):
            """Test successfully editing a message"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321",
                "text": "Updated text"
            }

            response = await processor._handle_edit_message_event(data)
            assert response["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_once_with(
                "edit_message", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.edit.assert_called_once_with(content="Updated text")

        @pytest.mark.asyncio
        async def test_edit_message_not_found(self, processor, channel_mock):
            """Test editing a message that doesn't exist"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321",
                "text": "Updated text"
            }
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor._handle_edit_message_event(data)
            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, channel_mock):
            """Test successfully deleting a message"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321"
            }

            response = await processor._handle_delete_message_event(data)
            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "delete_message", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.delete.assert_called_once()

        @pytest.mark.asyncio
        async def test_delete_message_not_found(self, processor, channel_mock):
            """Test deleting a message that doesn't exist"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321"
            }
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor._handle_delete_message_event(data)
            assert response["request_completed"] is False

    class TestReactions:
        """Tests for the reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, channel_mock):
            """Test successfully adding a reaction"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321",
                "emoji": "👍"
            }

            response = await processor._handle_add_reaction_event(data)
            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "add_reaction", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.add_reaction.assert_called_once_with("👍")

        @pytest.mark.asyncio
        async def test_add_reaction_message_not_found(self, processor, channel_mock):
            """Test adding a reaction to a message that doesn't exist"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321",
                "emoji": "👍"
            }
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor._handle_add_reaction_event(data)
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self, processor, channel_mock, discord_client_mock):
            """Test successfully removing a reaction"""
            data = {
                "conversation_id": "123456789",
                "message_id": "987654321",
                "emoji": "👍"
            }

            response = await processor._handle_remove_reaction_event(data)
            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "remove_reaction", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.remove_reaction.assert_called_once_with("👍", discord_client_mock.user)

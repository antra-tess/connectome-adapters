import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

from adapters.zulip_adapter.adapter.event_processors.zulip_events_processor import (
    ZulipEventsProcessor, EventType
)

class TestZulipEventsProcessor:
    """Tests for the ZulipEventsProcessor class"""

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        return AsyncMock()

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        return manager

    @pytest.fixture
    def processor(self, patch_config, zulip_client_mock, conversation_manager_mock):
        """Create a ZulipEventsProcessor with mocked dependencies"""
        return ZulipEventsProcessor(
            patch_config,
            zulip_client_mock,
            conversation_manager_mock,
            "test_bot"
        )

    @pytest.fixture
    def message_event_mock(self):
        """Create a mock for a new message event"""
        return {
            "type": "message",
            "message": {
                "id": 123,
                "content": "Test message",
                "sender_id": 456,
                "sender_full_name": "Test User",
                "timestamp": 1234567890,
                "type": "private",
                "display_recipient": [
                    {"id": 456, "email": "test@example.com", "full_name": "Test User"},
                    {"id": 789, "email": "bot@example.com", "full_name": "Test Bot"}
                ]
            }
        }

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type,event_key", [
            (EventType.MESSAGE, "message"),
            (EventType.UPDATE_MESSAGE, "update_message"),
            (EventType.REACTION, "reaction")
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type, event_key):
            """Test that process_event calls the correct handler method"""
            event = {"type": event_type}
            handler_mocks = {}

            for handler_type in EventType:
                method_name = f"_handle_{handler_type.value}"
                handler_mock = AsyncMock(return_value=["event_info"])
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            assert await processor.process_event(event) == ["event_info"]
            handler_mocks[event_type].assert_called_once_with(event)

        @pytest.mark.asyncio
        async def test_process_unknown_event(self, processor):
            """Test processing an unknown event type"""
            assert await processor.process_event({"type": "unknown_event"}) == []

        @pytest.mark.asyncio
        async def test_process_event_exception(self, processor, message_event_mock):
            """Test handling exceptions during event processing"""
            with patch.object(processor, "_handle_message", side_effect=Exception("Test error")):
                assert await processor.process_event(message_event_mock) == []

    class TestHandleMessage:
        """Tests for the _handle_message method"""

        @pytest.mark.asyncio
        async def test_handle_message(self, processor, message_event_mock):
            """Test handling a new message"""
            delta = {
                "updates": ["conversation_started", "message_received"],
                "conversation_id": "456_789",
                "message_id": "123",
                "text": "Test message",
                "sender": {"user_id": "456", "display_name": "Test User"},
                "timestamp": 1234567890000,
                "attachments": []
            }

            processor.conversation_manager.add_to_conversation.return_value = delta
            processor._fetch_conversation_history = AsyncMock(return_value=[{"some": "history"}])
            processor._conversation_started_event_info = AsyncMock(
                return_value={"event_type": "conversation_started"}
            )
            processor._new_message_event_info = AsyncMock(return_value={"event_type": "message_received"})

            result = await processor._handle_message(message_event_mock)

            assert len(result) == 2
            assert {"event_type": "conversation_started"} in result
            assert {"event_type": "message_received"} in result

            processor.conversation_manager.add_to_conversation.assert_called_once_with(
                message_event_mock.get("message"), None
            )
            
            processor._fetch_conversation_history.assert_called_once()
            processor._conversation_started_event_info.assert_called_once_with(
                delta, processor._fetch_conversation_history.return_value
            )
            processor._new_message_event_info.assert_called_once_with(delta)

        @pytest.mark.asyncio
        async def test_handle_message_no_delta(self, processor, message_event_mock):
            """Test handling a message with no conversation delta"""
            processor.conversation_manager.add_to_conversation.return_value = None
            assert await processor._handle_message(message_event_mock) == []

        @pytest.mark.asyncio
        async def test_handle_message_exception(self, processor, message_event_mock):
            """Test handling exceptions during message processing"""
            processor.conversation_manager.add_to_conversation.side_effect = Exception("Test error")
            assert await processor._handle_message(message_event_mock) == []

    class TestHandleUpdateMessage:
        """Tests for the _handle_update_message method"""

        @pytest.fixture
        def update_message_event_mock(self):
            """Create a mock for an update message event"""
            return {
                "type": "update_message",
                "message_id": 123,
                "orig_content": "Test message",
                "content": "Edited test message",
                "user_id": 456,
                "timestamp": 1234567890
            }

        @pytest.mark.asyncio
        async def test_handle_update_message(self, processor, update_message_event_mock):
            """Test handling an updated message"""
            delta = {
                "updates": ["message_edited"],
                "conversation_id": "456_789",
                "message_id": "123",
                "text": "Edited test message",
                "timestamp": 1234567890000
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._edited_message_event_info = AsyncMock(return_value={"event_type": "message_updated"})

            result = await processor._handle_update_message(update_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_updated"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with(
                "update_message", update_message_event_mock
            )
            processor._edited_message_event_info.assert_called_once_with(delta)

        @pytest.mark.asyncio
        async def test_handle_update_message_no_delta(self, processor, update_message_event_mock):
            """Test handling an updated message with no delta"""
            processor.conversation_manager.update_conversation.return_value = None
            assert await processor._handle_update_message(update_message_event_mock) == []

        @pytest.mark.asyncio
        async def test_handle_update_message_exception(self, processor, update_message_event_mock):
            """Test handling exceptions during update message processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_update_message(update_message_event_mock) == []

    class TestHandleReaction:
        """Tests for the _handle_reaction method"""

        @pytest.fixture
        def reaction_event_mock(self):
            """Create a mock for a reaction event"""
            return {
                "type": "reaction",
                "op": "add",
                "user_id": 456,
                "message_id": 123,
                "emoji_name": "+1",
                "emoji_code": "1f44d",
                "reaction_type": "unicode_emoji"
            }

        @pytest.mark.asyncio
        async def test_handle_reaction_added(self, processor, reaction_event_mock):
            """Test handling a reaction added event"""
            delta = {
                "updates": ["reaction_added"],
                "conversation_id": "456_789",
                "message_id": "123",
                "added_reactions": ["👍"],
                "timestamp": 1234567890000
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._reaction_update_event_info = AsyncMock(return_value={"event_type": "reaction_added"})

            result = await processor._handle_reaction(reaction_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_added"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with(
                "reaction", reaction_event_mock
            )
            processor._reaction_update_event_info.assert_called_once_with(
                "reaction_added", delta, "👍"
            )

        @pytest.mark.asyncio
        async def test_handle_reaction_removed(self, processor):
            """Test handling a reaction removed event"""
            reaction_removed_event = {
                "type": "reaction",
                "op": "remove",
                "user_id": 456,
                "message_id": 123,
                "emoji_name": "+1",
                "emoji_code": "1f44d",
                "reaction_type": "unicode_emoji"
            }

            delta = {
                "updates": ["reaction_removed"],
                "conversation_id": "456_789",
                "message_id": "123",
                "removed_reactions": ["👍"],
                "timestamp": 1234567890000
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._reaction_update_event_info = AsyncMock(return_value={"event_type": "reaction_removed"})

            result = await processor._handle_reaction(reaction_removed_event)

            assert len(result) == 1
            assert {"event_type": "reaction_removed"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with(
                "reaction", reaction_removed_event
            )
            processor._reaction_update_event_info.assert_called_once_with(
                "reaction_removed", delta, "👍"
            )

        @pytest.mark.asyncio
        async def test_handle_reaction_no_delta(self, processor, reaction_event_mock):
            """Test handling a reaction with no delta"""
            processor.conversation_manager.update_conversation.return_value = None
            assert await processor._handle_reaction(reaction_event_mock) == []

        @pytest.mark.asyncio
        async def test_handle_reaction_exception(self, processor, reaction_event_mock):
            """Test handling exceptions during reaction processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_reaction(reaction_event_mock) == []

    class TestHelperMethods:
        """Tests for helper methods"""

        @pytest.mark.asyncio
        async def test_conversation_started_event_info(self, processor):
            """Test creating a conversation started event"""
            delta = {"conversation_id": "456_789"}
            history = [{"message_id": "1", "text": "Test history message"}]
            
            result = await processor._conversation_started_event_info(delta, history)

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "conversation_started"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["history"] == []  # Note: Currently returns empty list

        @pytest.mark.asyncio
        async def test_new_message_event_info(self, processor):
            """Test creating a new message event"""
            delta = {
                "message_id": "123",
                "conversation_id": "456_789",
                "text": "Hello, world!",
                "sender": {"user_id": "456", "display_name": "Test User"},
                "timestamp": 1234567890000,
                "attachments": [{"type": "image"}],
                "thread_id": "thread123"
            }

            result = await processor._new_message_event_info(delta)

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "message_received"
            assert result["data"]["adapter_name"] == "test_bot"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["text"] == "Hello, world!"
            assert result["data"]["sender"]["user_id"] == "456"
            assert result["data"]["sender"]["display_name"] == "Test User"
            assert result["data"]["timestamp"] == 1234567890000
            assert len(result["data"]["attachments"]) == 1
            assert result["data"]["thread_id"] == "thread123"

        @pytest.mark.asyncio
        async def test_edited_message_event_info(self, processor):
            """Test creating an edited message event"""
            delta = {
                "message_id": "123",
                "conversation_id": "456_789",
                "text": "Edited message",
                "timestamp": 1234567890000
            }

            result = await processor._edited_message_event_info(delta)

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "message_updated"
            assert result["data"]["adapter_name"] == "test_bot"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["new_text"] == "Edited message"
            assert result["data"]["timestamp"] == 1234567890000

        @pytest.mark.asyncio
        async def test_reaction_update_event_info(self, processor):
            """Test creating a reaction event"""
            delta = {
                "message_id": "123",
                "conversation_id": "456_789"
            }

            result = await processor._reaction_update_event_info("reaction_added", delta, "👍")

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "reaction_added"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["emoji"] == "👍"

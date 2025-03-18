import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.zulip_adapter.adapter.adapter import ZulipAdapter
from adapters.zulip_adapter.adapter.event_processors.zulip_events_processor import ZulipEventsProcessor
from adapters.zulip_adapter.adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

class TestZulipAdapter:
    """Tests for the ZulipAdapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def zulip_events_processor_mock(self):
        """Create a mocked ZulipEventsProcessor"""
        processor = AsyncMock()
        processor.process_event = AsyncMock(return_value=[{"test": "event"}])
        return processor

    @pytest.fixture
    def socket_io_events_processor_mock(self):
        """Create a mocked SocketIoEventsProcessor"""
        processor = AsyncMock()
        processor.process_event = AsyncMock(return_value=True)
        return processor

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked ConversationManager"""
        return MagicMock()

    @pytest.fixture
    def adapter(self, socketio_server_mock, patch_config):
        """Create a TelegramAdapter with mocked dependencies"""
        conversation_manager_mock = MagicMock()
        attachment_cache_mock = MagicMock()
        message_cache_mock = MagicMock()

        conversation_manager_mock.message_cache = message_cache_mock
        conversation_manager_mock.attachment_cache = attachment_cache_mock
        
        with patch(
            "adapters.zulip_adapter.adapter.conversation_manager.conversation_manager.ConversationManager",
            return_value=conversation_manager_mock
        ):
            with patch(
                "core.cache.attachment_cache.AttachmentCache",
                return_value=attachment_cache_mock
            ):
                with patch(
                    "core.cache.message_cache.MessageCache",
                    return_value=message_cache_mock
                ):
                    with patch('os.path.exists', return_value=False):
                        with patch('os.makedirs'):
                            with patch('os.listdir', return_value=[]):
                                yield ZulipAdapter(patch_config, socketio_server_mock)

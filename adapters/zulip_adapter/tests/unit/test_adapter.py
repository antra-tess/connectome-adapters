import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

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
    def zulip_client_mock(self):
        """Create a mocked ZulipClient"""
        client = AsyncMock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.start_polling = AsyncMock()
        client.client = AsyncMock()
        client.client.get_profile = MagicMock(return_value={
            "result": "success",
            "full_name": "Test Bot",
            "email": "test@example.com"
        })
        client.running = True
        return client

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
        """Create a ZulipAdapter with mocked dependencies"""
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

    class TestMonitorConnection:
        """Tests for the connection monitoring"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_monitor_connection_success(self, adapter, zulip_client_mock):
            """Test successful connection check"""
            adapter.running = True
            adapter.initialized = True
            adapter.zulip_client = zulip_client_mock

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter.socketio_server.emit_event.assert_called_once_with(
                    "connect", {"adapter_type": adapter.adapter_type}
                )

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, zulip_client_mock):
            """Test connection check failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.zulip_client = zulip_client_mock
            zulip_client_mock.client.get_profile.return_value = {"result": "error"}

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter.socketio_server.emit_event.assert_called_once_with(
                    "disconnect", {"adapter_type": adapter.adapter_type}
                )

    class TestEventProcessing:
        """Tests for event processing"""

        @pytest.mark.asyncio
        async def test_process_zulip_event(self, adapter, zulip_events_processor_mock):
            """Test processing Zulip events"""
            adapter.zulip_events_processor = zulip_events_processor_mock
            test_event = {"type": "message", "data": "test_data"}

            await adapter.process_zulip_event(test_event)

            zulip_events_processor_mock.process_event.assert_called_once_with(test_event)
            adapter.socketio_server.emit_event.assert_called_once_with("bot_request", {"test": "event"})

        @pytest.mark.asyncio
        async def test_process_socket_io_event(self, adapter, socket_io_events_processor_mock):
            """Test processing Socket.IO events"""
            adapter.socket_io_events_processor = socket_io_events_processor_mock
            adapter.zulip_client = MagicMock()
            test_data = {"test": "socket_data"}

            assert await adapter.process_socket_io_event("send_message", test_data) is True
            socket_io_events_processor_mock.process_event.assert_called_once_with("send_message", test_data)

        @pytest.mark.asyncio
        async def test_process_socket_io_event_not_connected(self, adapter):
            """Test processing Socket.IO events when not connected"""
            adapter.zulip_client = None

            assert await adapter.process_socket_io_event("send_message", {"test": "socket_data"}) is False

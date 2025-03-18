import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.adapter import TelegramAdapter
from adapters.telegram_adapter.adapter.event_processors.telegram_events_processor import TelegramEventsProcessor
from adapters.telegram_adapter.adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

class TestTelegramAdapter:
    """Tests for the TelegramAdapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked TelethonClient"""
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        client.client = AsyncMock()
        client.client.get_me = AsyncMock()
        client.connected = True
        return client

    @pytest.fixture
    def telegram_events_processor_mock(self):
        """Create a mocked TelegramEventsProcessor"""
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
            "adapters.telegram_adapter.adapter.conversation_manager.conversation_manager.ConversationManager",
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
                                yield TelegramAdapter(patch_config, socketio_server_mock)

    class TestMonitorConnection:
        """Tests for the connection monitoring"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_monitor_connection_success(self, adapter, telethon_client_mock):
            """Test successful connection check"""
            adapter.running = True
            adapter.initialized = True
            adapter.telethon_client = telethon_client_mock

            sleep_mock = AsyncMock()
            sleep_mock.side_effect = [None, asyncio.CancelledError()]

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                telethon_client_mock.client.get_me.assert_called_once()
                adapter.socketio_server.emit_event.assert_called_once_with(
                    "connect", {"adapter_type": "telegram"}
                )

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, telethon_client_mock):
            """Test connection check failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.telethon_client = telethon_client_mock
            telethon_client_mock.client.get_me.return_value = None

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter.socketio_server.emit_event.assert_called_once_with(
                    "disconnect", {"adapter_type": "telegram"}
                )

    class TestEventProcessing:
        """Tests for event processing"""

        @pytest.mark.asyncio
        async def test_process_telegram_event(self, adapter, telegram_events_processor_mock):
            """Test processing Telegram events"""
            adapter.telegram_events_processor = telegram_events_processor_mock
            test_event = {"test": "event_data"}

            await adapter.process_telegram_event("new_message", test_event)

            telegram_events_processor_mock.process_event.assert_called_once_with("new_message", test_event)
            adapter.socketio_server.emit_event.assert_called_once_with("bot_request", {"test": "event"})

        @pytest.mark.asyncio
        async def test_process_socket_io_event(self, adapter, socket_io_events_processor_mock):
            """Test processing Socket.IO events"""
            adapter.socket_io_events_processor = socket_io_events_processor_mock
            adapter.telethon_client = MagicMock()
            test_data = {"test": "socket_data"}

            result = await adapter.process_socket_io_event("send_message", test_data)

            socket_io_events_processor_mock.process_event.assert_called_once_with("send_message", test_data)
            assert result is True

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from adapter.adapter import TelegramAdapter
from adapter.event_processors.telegram_events_processor import TelegramEventsProcessor
from adapter.event_processors.socket_io_events_processor import SocketIoEventsProcessor

class TestTelegramAdapter:
    """Tests for the TelegramAdapter class"""

    @pytest.fixture
    def config_mock(self):
        """Create a mocked Config instance"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key, default=None: {
            "adapter": {
                "type": "telegram",
                "connection_check_interval": 60,
                "retry_delay": 5
            }
        }.get(section, {}).get(key, default)
        return config

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
    def adapter(self, socketio_server_mock, config_mock):
        """Create a TelegramAdapter with mocked dependencies"""
        with patch("adapter.adapter.Config") as ConfigMock:
            ConfigMock.get_instance.return_value = config_mock

            with patch("adapter.adapter.ConversationManager") as ConversationManagerMock:
              adapter = TelegramAdapter(socketio_server_mock)
              yield adapter

    class TestStartStop:
        """Tests for the start method"""

        @pytest.mark.asyncio
        async def test_start_success(self, adapter, telethon_client_mock):
            """Test successful start"""
            with patch("adapter.adapter.TelethonClient", return_value=telethon_client_mock):
                with patch("adapter.adapter.TelegramEventsProcessor") as TelegramEventsProcessorMock:
                    with patch("adapter.adapter.SocketIoEventsProcessor") as SocketIoEventsProcessorMock:
                        with patch("asyncio.create_task") as create_task_mock:
                            adapter_info = MagicMock()
                            adapter_info.username = "test_bot"
                            telethon_client_mock.client.get_me.return_value = adapter_info

                            await adapter.start()

                            assert adapter.initialized is True
                            assert adapter.adapter_name == "test_bot"

                            telethon_client_mock.connect.assert_called_once()
                            telethon_client_mock.client.get_me.assert_called_once()
                            TelegramEventsProcessorMock.assert_called_once()
                            SocketIoEventsProcessorMock.assert_called_once()
                            create_task_mock.assert_called_once()
                            adapter.socketio_server.emit_event.assert_called_once_with(
                                "connect", {"adapter_type": "telegram"}
                            )

        @pytest.mark.asyncio
        async def test_start_connection_failure(self, adapter, telethon_client_mock):
            """Test start with connection failure"""
            telethon_client_mock.connect = AsyncMock(return_value=False)

            with patch("adapter.adapter.TelethonClient", return_value=telethon_client_mock):
                await adapter.start()

                assert adapter.initialized is False
                telethon_client_mock.connect.assert_called_once()
                adapter.socketio_server.emit_event.assert_not_called()

        @pytest.mark.asyncio
        async def test_stop_when_running(self, adapter, telethon_client_mock):
            """Test stopping the adapter when it is running"""
            adapter.running = True
            adapter.telethon_client = telethon_client_mock
            adapter.monitoring_task = AsyncMock()
            adapter.monitoring_task.cancel = MagicMock()

            await adapter.stop()

            assert adapter.running is False
            adapter.monitoring_task.cancel.assert_called_once()
            telethon_client_mock.disconnect.assert_called_once()
            adapter.socketio_server.emit_event.assert_called_once_with(
                "disconnect", {"adapter_type": "telegram"}
            )

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

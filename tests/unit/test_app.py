import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, call

import app
from app import main

class TestApp:

    @pytest.fixture
    def mock_setup_logging(self):
        with patch("app.setup_logging") as mock:
            yield mock

    @pytest.fixture
    def mock_socketio_server(self):
        mock = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.set_telegram_adapter = MagicMock()

        with patch("app.SocketIOServer", return_value=mock) as mock_class:
            yield mock_class, mock

    @pytest.fixture
    def mock_telegram_adapter(self):
        mock = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.running = True

        with patch("app.TelegramAdapter", return_value=mock) as mock_class:
            yield mock_class, mock

    @pytest.fixture
    def mock_sleep(self):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def app_fixtures(self, mock_setup_logging, mock_socketio_server, mock_telegram_adapter, mock_sleep):
        """Combined fixture for common app test setup"""
        _, server_instance = mock_socketio_server
        _, adapter_instance = mock_telegram_adapter

        return {
            "logging": mock_setup_logging,
            "server": server_instance,
            "adapter": adapter_instance,
            "sleep": mock_sleep
        }


    class TestMain:
        """Tests for the main() loop implementation"""

        @pytest.mark.asyncio
        async def test_main_running_loop(self, app_fixtures):
            """Test the main loop running multiple times"""
            server = app_fixtures["server"]
            adapter = app_fixtures["adapter"]
            mock_sleep = app_fixtures["sleep"]
            mock_logging = app_fixtures["logging"]

            # Configure adapter to stop after three iterations
            call_count = 0
            def sleep_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count >= 3:
                    adapter.running = False
                return None

            mock_sleep.side_effect = sleep_side_effect

            await main()

            assert mock_logging.call_count == 1
            assert mock_sleep.call_count == 3
            assert server.start.call_count == 1
            assert adapter.start.call_count == 1
            assert adapter.stop.call_count == 0
            assert server.stop.call_count == 1

        @pytest.mark.parametrize("error_class,error_msg", [
            (FileNotFoundError, "Config file not found"),
            (ValueError, "Missing token")
        ])
        @pytest.mark.asyncio
        async def test_main_file_not_found_error(self, app_fixtures, error_class, error_msg):
            """Test handling of file not found errors"""
            server = app_fixtures["server"]
            adapter = app_fixtures["adapter"]
            mock_logging = app_fixtures["logging"]

            # Configure adapter to raise the specified error
            adapter.start.side_effect = error_class(error_msg)
            adapter.running = False

            await main()

            assert mock_logging.call_count == 1
            assert server.start.call_count == 1
            assert adapter.start.call_count == 1
            assert adapter.stop.call_count == 0
            assert server.stop.call_count == 1

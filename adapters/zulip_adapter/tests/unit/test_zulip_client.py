import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

from adapters.zulip_adapter.adapter.zulip_client import ZulipClient

class TestZulipClient:
    """Tests for ZulipClient"""

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip Client instance directly"""
        with patch("zulip.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.register = MagicMock(return_value={
                "queue_id": "test_queue_id",
                "last_event_id": 12345
            })
            mock_client.get_events = MagicMock(return_value={
                "events": [
                    {"id": 12346, "type": "message", "content": "test message"},
                    {"id": 12347, "type": "reaction", "emoji_code": "1f44d"}
                ]
            })
            mock_client.delete_queue = MagicMock(return_value={"result": "success"})
            mock_client_class.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def zulip_client(self, patch_config, zulip_client_mock):
        """Create a ZulipClient with mocked dependencies"""
        client = ZulipClient(patch_config, AsyncMock())
        client.client = zulip_client_mock
        yield client

    class TestInitialization:
        """Tests for ZulipClient initialization"""

        def test_initialization(self, patch_config):
            """Test client initialization with valid config"""
            with patch("zulip.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                process_event_mock = AsyncMock()
                client = ZulipClient(patch_config, process_event_mock)

                assert client.config == patch_config
                assert client.queue_id is None
                assert client.last_event_id is None
                assert client.running is False
                assert client._polling_task is None

                mock_client_class.assert_called_once_with(
                    email=patch_config.get_setting("adapter", "adapter_email"),
                    api_key=patch_config.get_setting("adapter", "api_key"),
                    site=patch_config.get_setting("adapter", "site")
                )

    class TestConnection:
        """Tests for connecting to Zulip"""

        @pytest.mark.asyncio
        async def test_connect_success(self, zulip_client, zulip_client_mock):
            """Test successful connection to Zulip"""
            with patch.object(zulip_client, "client", zulip_client_mock):
                await zulip_client.connect()
                
                zulip_client_mock.register.assert_called_once_with(
                    event_types=["message", "reaction", "update_message"]
                )
                
                assert zulip_client.queue_id == "test_queue_id"
                assert zulip_client.last_event_id == 12345
                assert zulip_client.running is True

        @pytest.mark.asyncio
        async def test_connect_failure_empty_result(self, zulip_client, zulip_client_mock):
            """Test connecting with empty result"""
            zulip_client_mock.register.return_value = None
            
            with patch.object(zulip_client, "client", zulip_client_mock):
                await zulip_client.connect()
                
                zulip_client_mock.register.assert_called_once()
                assert zulip_client.running is False

        @pytest.mark.asyncio
        async def test_connect_exception(self, zulip_client, zulip_client_mock):
            """Test connecting with an exception"""
            zulip_client_mock.register.side_effect = Exception("Test error")
            
            with patch.object(zulip_client, "client", zulip_client_mock):
                await zulip_client.connect()
                
                zulip_client_mock.register.assert_called_once()
                assert zulip_client.running is False

    class TestPolling:
        """Tests for event polling"""

        @pytest.mark.asyncio
        async def test_start_polling(self, zulip_client):
            """Test starting the polling loop"""
            with patch("asyncio.create_task") as create_task_mock:
                await zulip_client.start_polling()
                
                create_task_mock.assert_called_once()
                assert zulip_client._polling_task is not None

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_polling_loop_processes_events(self, zulip_client, zulip_client_mock):
            """Test that the polling loop processes events"""
            zulip_client.running = True
            zulip_client.queue_id = "test_queue_id"
            zulip_client.last_event_id = 12345

            call_count = 0
            def mock_get_events(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return {
                        "events": [
                            {"id": 12346, "type": "message", "content": "test message"}
                        ]
                    }
                else:
                    raise Exception("Stop loop")

            process_calls = []
            async def mock_process_event(event):
                process_calls.append(event)
            
            zulip_client_mock.get_events = MagicMock(side_effect=mock_get_events)
            zulip_client.process_event = mock_process_event

            try:
                await asyncio.wait_for(zulip_client._polling_loop(), timeout=1.0)
            except (asyncio.TimeoutError, Exception) as e:
                pass

            assert len(process_calls) == 1
            assert process_calls[0]["type"] == "message"
            assert zulip_client.last_event_id == 12346

        @pytest.mark.asyncio
        async def test_polling_loop_handles_error(self, zulip_client, zulip_client_mock):
            """Test that the polling loop handles errors properly"""
            zulip_client.running = True
            zulip_client.queue_id = "test_queue_id"
            zulip_client.last_event_id = 12345

            zulip_client_mock.get_events.side_effect = [
                Exception("API error"),
                asyncio.CancelledError()
            ]
            
            with patch.object(zulip_client, "client", zulip_client_mock):
                with patch("asyncio.sleep") as sleep_mock:
                    with pytest.raises(asyncio.CancelledError):
                        await zulip_client._polling_loop()
                    sleep_mock.assert_called_once_with(5)

    class TestDisconnection:
        """Tests for disconnecting from Zulip"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_disconnect(self, zulip_client, zulip_client_mock):
            """Test disconnecting with an active polling task"""
            zulip_client.running = True
            zulip_client.queue_id = "test_queue_id"
            zulip_client._polling_task = AsyncMock()
            
            with patch.object(zulip_client, "client", zulip_client_mock):
                await zulip_client.disconnect()
                
                assert zulip_client.running is False
                zulip_client_mock.delete_queue.assert_called_once_with("test_queue_id")
                assert zulip_client.queue_id is None
                assert zulip_client.last_event_id is None

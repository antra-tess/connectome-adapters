import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum

from adapters.zulip_adapter.adapter.event_processors.socket_io_events_processor import (
    SocketIoEventsProcessor, EventType
)

class TestSocketIoEventsProcessor:
    """Tests for the SocketIoEventsProcessor class"""

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.conversations = {}
        return manager

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock()
        uploader.upload_attachment = AsyncMock()
        return uploader

    @pytest.fixture
    def processor(self,
                  patch_config,
                  conversation_manager_mock,
                  uploader_mock):
        """Create a SocketIoEventsProcessor with mocked dependencies"""
        with patch(
            "adapters.zulip_adapter.adapter.event_processors.socket_io_events_processor.Uploader"
        ) as UploaderMock:
            UploaderMock.return_value = uploader_mock

            return SocketIoEventsProcessor(
                patch_config,
                conversation_manager_mock
            )

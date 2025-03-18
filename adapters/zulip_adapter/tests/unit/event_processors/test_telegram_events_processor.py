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
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        return manager

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock(return_value={})
        return downloader

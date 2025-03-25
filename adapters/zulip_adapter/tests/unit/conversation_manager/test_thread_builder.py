import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from adapters.zulip_adapter.adapter.conversation_manager.thread_handler import ThreadHandler
from adapters.zulip_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ThreadInfo
)
from core.cache.message_cache import CachedMessage

class TestThreadHandler:
    """Tests for the ThreadHandler class"""

    @pytest.fixture
    def message_cache_mock(self):
        """Create a mocked MessageCache"""
        return AsyncMock()

    @pytest.fixture
    def conversation_info(self):
        """Create a ConversationInfo instance for testing"""
        return ConversationInfo(
            conversation_id="123_456",
            conversation_type="private",
            just_started=False,
            threads={},
            messages=set()
        )

    @pytest.fixture
    def thread_info(self):
        """Create a ThreadInfo instance for testing"""
        return ThreadInfo(
            thread_id="789",
            title=None,
            root_message_id="789",
            message_count=1,
            last_activity=datetime.now()
        )

    @pytest.fixture
    def cached_message(self):
        """Create a CachedMessage instance for testing"""
        return CachedMessage(
            message_id="123",
            conversation_id="123_456",
            thread_id=None,
            sender_id="user1",
            sender_name="User One",
            text="Hello world",
            timestamp=int(datetime.now().timestamp() * 1000),
            is_from_bot=False,
            reply_to_message_id=None
        )

    class TestExtractReplyToId:
        """Tests for extract_reply_to_id method"""

        @pytest.mark.parametrize("content,expected", [
            # Standard reply format
            ('@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nHi there', "456"),
            # Stream message reply
            ('@_**User|123** [said](https://zulip.at-hub.com/#narrow/stream/789-general/topic/test/near/456):\n```quote\nHello\n```', "456"),
            # No reply
            ('Just a regular message', None),
            # Malformed reply
            ('@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/abc):\n```quote\nHello\n```', None),
            # Empty content
            ('', None),
            # Multiple replies (should find the first one)
            ('@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\n' +
             '@_**User|789** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/789):\n```quote\nHello\n```\n' +
             '```\nHi there', "456"),
        ])
        def test_extract_reply_to_id(self, content, expected):
            """Test extracting reply_to message ID from content"""
            assert ThreadHandler.extract_reply_to_id(content) == expected

    class TestAddThreadInfoToConversation:
        """Tests for add_thread_info_to_conversation method"""

        @pytest.mark.asyncio
        async def test_no_content(self, message_cache_mock, conversation_info):
            """Test handling message with no content"""
            message = {}
            result = await ThreadHandler.add_thread_info_to_conversation(
                message_cache_mock, message, conversation_info
            )

            assert result is None
            assert len(conversation_info.threads) == 0

        @pytest.mark.asyncio
        async def test_no_reply(self, message_cache_mock, conversation_info):
            """Test handling message with no reply"""
            message = {"content": "Just a regular message"}
            result = await ThreadHandler.add_thread_info_to_conversation(
                message_cache_mock, message, conversation_info
            )

            assert result is None
            assert len(conversation_info.threads) == 0

        @pytest.mark.asyncio
        async def test_new_thread(self, message_cache_mock, conversation_info):
            """Test creating a new thread"""
            message = {
                "content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nHi there'
            }
            
            message_cache_mock.get_message_by_id.return_value = None
            
            result = await ThreadHandler.add_thread_info_to_conversation(
                message_cache_mock, message, conversation_info
            )
            
            assert result is not None
            assert result.thread_id == "456"
            assert result.root_message_id == "456"
            assert result.message_count == 1
            assert result.last_activity is not None
            
            assert "456" in conversation_info.threads
            assert conversation_info.threads["456"] == result
            
            message_cache_mock.get_message_by_id.assert_called_once_with(
                conversation_id="123_456",
                message_id="456"
            )

        @pytest.mark.asyncio
        async def test_existing_thread(self, message_cache_mock, conversation_info, thread_info):
            """Test adding to an existing thread"""
            conversation_info.threads["789"] = thread_info
            original_message_count = thread_info.message_count
            original_last_activity = thread_info.last_activity
            
            message = {
                "content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/789):\n```quote\nHello\n```\nHi there'
            }

            await asyncio.sleep(0.01)
            
            result = await ThreadHandler.add_thread_info_to_conversation(
                message_cache_mock, message, conversation_info
            )
            
            assert result is not None
            assert result.thread_id == "789"
            assert result.message_count == original_message_count + 1
            assert result.last_activity > original_last_activity
            
            assert "789" in conversation_info.threads
            assert conversation_info.threads["789"] == result

        @pytest.mark.asyncio
        async def test_reply_to_reply(self, message_cache_mock, conversation_info, cached_message):
            """Test handling reply to a message that is itself a reply"""
            replied_message = CachedMessage(
                message_id="456",
                conversation_id=cached_message.conversation_id,
                thread_id="123",
                sender_id=cached_message.sender_id,
                sender_name=cached_message.sender_name,
                text=cached_message.text,
                timestamp=cached_message.timestamp,
                is_from_bot=cached_message.is_from_bot,
                reply_to_message_id="123"  # This message replies to message 123
            )
            
            original_thread = ThreadInfo(
                thread_id="123",
                root_message_id="123",
                message_count=2
            )
            conversation_info.threads["123"] = original_thread

            message_cache_mock.get_message_by_id.return_value = replied_message
            message = {
                "content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nHi there'
            }            
            result = await ThreadHandler.add_thread_info_to_conversation(
                message_cache_mock, message, conversation_info
            )
            
            assert result is not None
            assert result.thread_id == "456"  # Thread ID is the immediate reply target
            assert result.root_message_id == "123"  # But root ID is from the original thread
            assert result.message_count == 1
            
            assert "456" in conversation_info.threads
            assert conversation_info.threads["456"] == result
            
            message_cache_mock.get_message_by_id.assert_called_once_with(
                conversation_id="123_456",
                message_id="456"
            )

    class TestUpdateThreadInfo:
        """Tests for update_thread_info method"""

        @pytest.mark.asyncio
        async def test_no_change(self, message_cache_mock, conversation_info):
            """Test when threading hasn't changed"""
            message = {
                "message_id": "123",
                "orig_content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nOriginal reply',
                "content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nEdited reply'
            }
            
            changed, thread_info = await ThreadHandler.update_thread_info(
                message_cache_mock, message, conversation_info
            )
            
            assert changed is False
            assert thread_info is None

        @pytest.mark.asyncio
        async def test_reply_removed(self, message_cache_mock, conversation_info):
            """Test when a reply reference is removed"""
            message = {
                "message_id": "123",
                "orig_content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nOriginal reply',
                "content": 'Edited with no reply'
            }
            
            changed, thread_info = await ThreadHandler.update_thread_info(
                message_cache_mock, message, conversation_info
            )
            
            assert changed is True
            assert thread_info is None

        @pytest.mark.asyncio
        async def test_reply_added(self, message_cache_mock, conversation_info):
            """Test when a reply reference is added"""
            message = {
                "message_id": "123",
                "orig_content": 'Original with no reply',
                "content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nNow it\'s a reply'
            }

            with patch.object(
                ThreadHandler, 'add_thread_info_to_conversation',
                return_value=ThreadInfo(thread_id="456", root_message_id="456")
            ) as mock_add:
                changed, thread_info = await ThreadHandler.update_thread_info(
                    message_cache_mock, message, conversation_info
                )
                
                assert changed is True
                assert thread_info is not None
                assert thread_info.thread_id == "456"
                
                mock_add.assert_called_once_with(
                    message_cache_mock, message, conversation_info
                )

        @pytest.mark.asyncio
        async def test_reply_changed(self, message_cache_mock, conversation_info):
            """Test when a reply reference is changed to a different message"""
            message = {
                "message_id": "123",
                "orig_content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/456):\n```quote\nHello\n```\nOriginal reply',
                "content": '@_**User|123** [said](https://zulip.at-hub.com/#narrow/dm/123-dm/near/789):\n```quote\nHello\n```\nReplying to different message'
            }

            with patch.object(
                ThreadHandler, 'add_thread_info_to_conversation',
                return_value=ThreadInfo(thread_id="789", root_message_id="789")
            ) as mock_add:
                changed, thread_info = await ThreadHandler.update_thread_info(
                    message_cache_mock, message, conversation_info
                )
                
                assert changed is True
                assert thread_info is not None
                assert thread_info.thread_id == "789"
                
                mock_add.assert_called_once_with(
                    message_cache_mock, message, conversation_info
                )

    class TestRemoveThreadInfo:
        """Tests for remove_thread_info method"""

        def test_remove_from_thread(self, conversation_info, cached_message):
            """Test removing a message from a thread that has multiple messages"""
            test_thread = ThreadInfo(
                thread_id="test_thread",
                root_message_id="123",
                message_count=2
            )
            conversation_info.threads["test_thread"] = test_thread
            cached_message.thread_id = "test_thread"

            ThreadHandler.remove_thread_info(conversation_info, cached_message)

            assert "test_thread" in conversation_info.threads
            assert conversation_info.threads["test_thread"].message_count == 1

        def test_remove_last_message_from_thread(self, conversation_info, cached_message):
            """Test removing the last message from a thread"""
            test_thread = ThreadInfo(
                thread_id="test_thread",
                root_message_id="123",
                message_count=1
            )
            conversation_info.threads["test_thread"] = test_thread            
            cached_message.thread_id = "test_thread"
            
            ThreadHandler.remove_thread_info(conversation_info, cached_message)
            
            assert "test_thread" not in conversation_info.threads

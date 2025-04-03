import re
from typing import Any, Optional, Tuple

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo

from core.cache.message_cache import MessageCache
from core.conversation.base_data_classes import ThreadInfo
from core.conversation.base_thread_handler import BaseThreadHandler

class ThreadHandler(BaseThreadHandler):
    """Handles thread information for Discord messages"""

    def __init__(self, message_cache: MessageCache):
        super().__init__(message_cache)

    def _extract_reply_to_id(self, message: Any) -> Optional[str]:
        """Extract the reply_to_message_id from a message.

        Args:
            message: Discord message object

        Returns:
            Message ID being replied to, or None if not a reply
        """
        if not message or not hasattr(message, "reference") or not message.reference:
            return None

        return str(message.reference.message_id)

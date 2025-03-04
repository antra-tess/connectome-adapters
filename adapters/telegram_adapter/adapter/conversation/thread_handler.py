from typing import Any, Optional

from core.cache.message_cache import MessageCache
from core.conversation.base_thread_handler import BaseThreadHandler

class ThreadHandler(BaseThreadHandler):
    """Handles thread information"""

    def __init__(self, message_cache: MessageCache):
        super().__init__(message_cache)

    def _extract_reply_to_id(self, message: Any) -> Optional[str]:
        """Extract the reply_to_message_id from a message.

        Args:
            message: Telethon message object

        Returns:
            Message ID being replied to, or None if not a reply
        """
        if not message or not hasattr(message, "reply_to") or not message.reply_to:
            return None

        return str(message.reply_to.reply_to_msg_id)

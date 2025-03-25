import logging
import re
from datetime import datetime
from typing import Any, Optional, Tuple

from adapters.zulip_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ThreadInfo
)
from core.cache.message_cache import MessageCache, CachedMessage

class ThreadHandler:
    """Handles thread information for Zulip messages"""

    @staticmethod
    def extract_reply_to_id(content: str) -> Optional[str]:
        """Extract the replied-to message ID from a message's content
        
        Args:
            content: Message content
            
        Returns:
            Message ID being replied to, or None if not a reply
        """
        # Look for the pattern: [said](https://zulip.at-hub.com/#narrow/.../near/MESSAGE_ID)
        pattern = r'\[said\]\([^\)]+/near/(\d+)\)'
        match = re.search(pattern, content)

        if match:
            return match.group(1)

        return None

    @staticmethod
    async def add_thread_info_to_conversation(message_cache: MessageCache,
                                              message: Any,
                                              conversation_info: ConversationInfo) -> Optional[ThreadInfo]:
        """Get thread info from Zulip message object
        
        Args:
            message_cache: Message cache object
            message: Zulip message object
            conversation_info: Conversation info object

        Returns:
            Thread info object if found, None otherwise
        """
        if not message or "content" not in message:
            return

        reply_to_msg_id = ThreadHandler.extract_reply_to_id(
            message.get("content", "")
        )
        if not reply_to_msg_id:
            return

        thread_id = reply_to_msg_id        
        thread_info = None

        if thread_id in conversation_info.threads:
            thread_info = conversation_info.threads[thread_id]
        else:
            root_message_id = reply_to_msg_id

            try:
                replied_msg = await message_cache.get_message_by_id(
                    conversation_id=conversation_info.conversation_id,
                    message_id=reply_to_msg_id
                )
                if replied_msg and replied_msg.reply_to_message_id:
                    parent_thread_id = replied_msg.thread_id or replied_msg.reply_to_message_id
                    if parent_thread_id in conversation_info.threads:
                        root_message_id = conversation_info.threads[parent_thread_id].root_message_id
            except Exception as e:
                logging.warning(f"Error finding thread root: {e}")

            thread_info = ThreadInfo(thread_id=thread_id, root_message_id=root_message_id)

        thread_info.message_count += 1
        thread_info.last_activity = datetime.now()
        conversation_info.threads[thread_id] = thread_info

        return thread_info

    @staticmethod
    async def update_thread_info(message_cache: MessageCache,
                                 message: Any,
                                 conversation_info: ConversationInfo) -> Tuple[bool, Optional[ThreadInfo]]:
        """Update thread info when a message is edited
        
        Args:
            message_cache: Message cache object
            message: Edited message object
            conversation_info: Conversation info object
            
        Returns:
            Tuple of (bool indicating if threading changed, updated ThreadInfo)
        """
        old_reply_to_id = ThreadHandler.extract_reply_to_id(message.get("orig_content", ""))
        new_reply_to_id = ThreadHandler.extract_reply_to_id(message.get("content", ""))

        if old_reply_to_id == new_reply_to_id:
            return (False, None)
            
        if old_reply_to_id and not new_reply_to_id:
            return (True, None)

        if new_reply_to_id:
            thread_info = await ThreadHandler.add_thread_info_to_conversation(
                message_cache, message, conversation_info
            )
            return (True, thread_info)
            
        return (False, None)

    @staticmethod
    def remove_thread_info(conversation_info: ConversationInfo,
                           cached_msg: CachedMessage) -> None:
        """Remove thread info from a message

        Args:
            conversation_info: Conversation info object
            cached_msg: Cached message object
        """
        if cached_msg.thread_id in conversation_info.threads:
            conversation_info.threads[cached_msg.thread_id].message_count -= 1
            if conversation_info.threads[cached_msg.thread_id].message_count == 0:
                del conversation_info.threads[cached_msg.thread_id]

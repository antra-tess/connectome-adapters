import logging

from datetime import datetime
from typing import Any

from adapters.telegram_adapter.adapter.conversation_manager.conversation_data_classes import (
  ConversationInfo, ConversationDelta, ThreadInfo
)
from core.cache.message_cache import MessageCache

class ThreadBuilder:
    """Builds thread information"""

    @staticmethod
    async def add_thread_info_to_conversation(message_cache: MessageCache,
                                              message: Any,
                                              conversation_info: ConversationInfo,
                                              delta: ConversationDelta) -> None:
        """Get thread info from Telethon message object

        Args:
            message_cache: Message cache object
            message: Telethon message object
            conversation_info: Conversation info object
            delta: Conversation delta object to update
        """
        if not hasattr(message, "reply_to") or not message.reply_to:
            return delta

        reply_to_msg_id = str(message.reply_to.reply_to_msg_id)
        thread_id = reply_to_msg_id

        thread_info = None
        if thread_id in conversation_info.threads:
            thread_info = conversation_info.threads[thread_id]
        else:
            # We track root message that started the thread
            root_message_id = reply_to_msg_id

            try:
                replied_msg = await message_cache.get_message_by_id(
                    conversation_id=conversation_info.conversation_id,
                    message_id=reply_to_msg_id
                )
                if replied_msg and replied_msg.thread_id:
                    parent_thread_id = replied_msg.thread_id
                    if parent_thread_id in conversation_info.threads:
                        root_message_id = conversation_info.threads[parent_thread_id].root_message_id
            except Exception as e:
                logging.warning(f"Error finding thread root: {e}")

            thread_info = ThreadInfo(
                thread_id=thread_id,
                root_message_id=root_message_id
            )

        thread_info.message_count += 1
        thread_info.last_activity = datetime.now()
        conversation_info.threads[thread_id] = thread_info

        delta.thread_id = thread_info.thread_id

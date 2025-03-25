from typing import Any, Dict, Set
from adapters.telegram_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UserInfo
)

class UserBuilder:
    """Builds user information"""

    @staticmethod
    def add_user_info_to_conversation(message: Dict[str, Any],
                                      conversation_info: ConversationInfo,
                                      from_adapter: bool) -> UserInfo:
        """Add user info to conversation info

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            from_adapter: Whether the message is from the adapter

        Returns:
            User info object
        """
        user_id = str(message.get("sender_id", ""))

        if user_id in conversation_info.known_members:
            return conversation_info.known_members[user_id]

        if user_id:
            user = None
            recipients = message.get("display_recipient", [])

            if isinstance(recipients, list):
                for recipient in recipients:
                    if str(recipient.get("id")) == user_id:
                        user = recipient
                        break

            if user:
                username = user.get("full_name", None)
            else:
                username = message.get("sender_full_name", None)

            conversation_info.known_members[user_id] = UserInfo(
                user_id=user_id,
                username=username,
                is_bot=from_adapter
            )

            return conversation_info.known_members[user_id]

        return None

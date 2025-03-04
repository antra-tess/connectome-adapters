from typing import Any
from adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UserInfo
)

class UserBuilder:
    """Builds user information"""

    @staticmethod
    def add_user_info_to_conversation(user: Any,
                                      conversation_info: ConversationInfo,
                                      delta: ConversationDelta) -> None:
        """Add user info to conversation info

        Args:
            user: Telethon user object
            conversation_info: Conversation info object
            delta: Conversation delta object to update
        """
        result = {
            "user_id": getattr(user, "id", None),
            "display_name": "Unknown",
            "is_bot": False
        }

        if result["user_id"]:
            result["user_id"] = str(result["user_id"])
            user_info = None

            if result["user_id"] in conversation_info.known_members:
                user_info = conversation_info.known_members[result["user_id"]]
            else:
                user_info = UserInfo(result["user_id"])
                user_info.username = getattr(user, "username", None)
                user_info.first_name = getattr(user, "first_name", "Unknown")
                user_info.last_name = getattr(user, "last_name", "Unknown")
                user_info.is_bot = getattr(user, "bot", False)
                conversation_info.known_members[result["user_id"]] = user_info

            result["display_name"] = user_info.display_name
            result["is_bot"] = user_info.is_bot

        delta.sender = result

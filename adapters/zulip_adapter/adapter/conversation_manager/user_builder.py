from typing import Any, Dict
from adapters.telegram_adapter.adapter.conversation_manager.conversation_data_classes import (
    ConversationInfo, ConversationDelta, UserInfo
)

class UserBuilder:
    """Builds user information"""

    @staticmethod
    def add_user_info_to_conversation(message: Dict[str, Any],
                                      conversation_info: ConversationInfo,
                                      delta: ConversationDelta) -> None:
        """Add user info to conversation info

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            delta: Conversation delta object to update
        """
        result = {
            "user_id": message.get("sender_id", None),
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

                user = None
                recipients = message.get("display_recipient", [])

                if isinstance(recipients, list):
                    for recipient in recipients:
                        if recipient.get("id") == result["user_id"]:
                            user = recipient
                            break

                if user:
                    user_info.username = user.get("full_name", None)
                else:
                    user_info.username = message.get("sender_full_name", None)
                
                user_info.is_bot = message.get("is_me_message", False)
                conversation_info.known_members[result["user_id"]] = user_info

            result["display_name"] = user_info.display_name
            result["is_bot"] = user_info.is_bot

        delta.sender = result

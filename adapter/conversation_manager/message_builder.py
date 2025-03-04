from typing import Dict, Any, Optional
from datetime import datetime

class MessageBuilder:
    """Builds message objects from Telethon events"""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset the builder to its initial state"""
        self.message_data = {}
        return self

    def with_basic_info(self, message: Any, conversation_id: str) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message.id)
        self.message_data["conversation_id"] = conversation_id

        if hasattr(message, 'date'):
            self.message_data["timestamp"] = message.date
        else:
            self.message_data["timestamp"] = datetime.now()

        return self

    def with_sender_info(self, sender: Optional[Dict[str, Any]]) -> 'MessageBuilder':
        """Add sender information"""
        if sender:
            self.message_data["sender_id"] = sender.get("user_id")
            self.message_data["sender_name"] = sender.get("display_name")
            self.message_data["is_from_bot"] = sender.get("is_bot", False)
        else:
            self.message_data["is_from_bot"] = True

        return self

    def with_thread_info(self, thread_id: Optional[str], message: Any) -> 'MessageBuilder':
        """Add thread information"""
        self.message_data["thread_id"] = thread_id

        if thread_id and hasattr(message, 'reply_to') and message.reply_to:
            self.message_data["reply_to_message_id"] = getattr(message.reply_to, 'reply_to_msg_id', None)

        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = getattr(message, 'message', '')
        return self

    def build(self) -> Dict[str, Any]:
        """Build the final message object"""
        return self.message_data.copy()

import asyncio
import logging
import os

from datetime import datetime
from typing import List, Dict, Any

from adapters.zulip_adapter.adapter.conversation_manager.conversation_manager import ConversationManager
from core.utils.config import Config

class TelegramHistoryFormatter:
    """Formats Telegram history"""

    def __init__(self,
                 config: Config,
                 conversation_manager: ConversationManager,
                 history: List[Dict[str, Any]],
                 conversation_id: str,
                 current_message_id: str):
        self.config = config
        self.conversation_manager = conversation_manager
        self.history = history
        self.users = {}
        self.conversation_id = conversation_id
        self.current_message_id = current_message_id

        self._get_users()

    async def fetch_conversation_history(self, conversation_id: str, message_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch and format message history from Zulip
        
        Args:
            conversation_id: ID of the conversation
            message_id: ID of the current message (for anchor)
            limit: Maximum number of messages to fetch
            
        Returns:
            List of formatted message objects
        """
        return
        try:
            # Parse conversation ID to determine type and parameters
            conversation_type, params = self._parse_conversation_id(conversation_id)
            
            # Set up the request parameters
            request = {
                "anchor": message_id if message_id else "newest",
                "num_before": limit,
                "num_after": 0,  # Don't fetch newer messages
                "apply_markdown": False,  # Get raw message content
                "narrow": self._create_narrow(conversation_type, params)
            }
            
            # Call the API
            result = self.zulip_client.client.get_messages(request)
            
            if result["result"] != "success":
                logging.error(f"Error fetching history: {result.get('msg', 'Unknown error')}")
                return []
            
            # Process and format messages
            formatted_messages = []
            for message in result["messages"]:
                formatted_message = await self._format_message_for_history(message, conversation_id)
                if formatted_message:
                    formatted_messages.append(formatted_message)
            
            # Return in chronological order (oldest first)
            return formatted_messages
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    def _parse_conversation_id(self, conversation_id: str) -> Tuple[str, Dict[str, Any]]:
        """Parse a conversation ID into type and parameters"""
        return
        if '/' in conversation_id:
            # Stream conversation - format is "stream_id/topic"
            stream_id, topic = conversation_id.split('/', 1)
            return "stream", {"stream_id": int(stream_id), "topic": topic}
        elif ',' in conversation_id:
            # Private conversation - format is "user_id,user_id,..."
            user_ids = conversation_id.split(',')
            return "private", {"user_ids": [int(uid) for uid in user_ids]}
        
        # Default to private with single user (direct message)
        return "private", {"user_ids": [int(conversation_id)]}

    def _create_narrow(self, conversation_type: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create a narrow specification for the API"""
        return
        if conversation_type == "stream":
            # For stream messages, narrow by stream and topic
            return [
                {"operator": "stream", "operand": params["stream_id"]},
                {"operator": "topic", "operand": params["topic"]}
            ]
        else:
            # For private messages, narrow by user IDs
            if len(params["user_ids"]) == 1:
                # Direct message with single user
                return [
                    {"operator": "pm-with", "operand": params["user_ids"][0]}
                ]
            else:
                # Group message with multiple users
                user_list = ','.join([str(uid) for uid in params["user_ids"]])
                return [
                    {"operator": "pm-with", "operand": user_list}
                ]

    async def _format_message_for_history(self, message: Dict[str, Any], conversation_id: str) -> Optional[Dict[str, Any]]:
        """Format a Zulip message for the history response"""
        return
        # Check if message is valid/not deleted
        if message.get("content") in ["(deleted)", "", "(message deleted)"]:
            return None
        
        # Get sender information
        sender_id = str(message.get("sender_id", ""))
        sender_full_name = message.get("sender_full_name", "Unknown User")
        sender_email = message.get("sender_email", "")
        
        # Format attachments if any
        attachments = []
        if self._has_attachments(message):
            attachment_info = await self._process_attachments(message)
            if attachment_info:
                attachments.append(attachment_info)
        
        # Create the formatted message
        return {
            "message_id": str(message.get("id")),
            "conversation_id": conversation_id,
            "text": message.get("content", ""),
            "sender": {
                "user_id": sender_id,
                "display_name": sender_full_name,
                "email": sender_email,
                "username": sender_email.split("@")[0] if "@" in sender_email else ""
            },
            "timestamp": int(message.get("timestamp") * 1000) if "timestamp" in message else None,
            "attachments": attachments
        }

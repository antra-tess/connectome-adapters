from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Set

class UpdateType(str, Enum):
    """Types of updates that can occur in a conversation"""
    CONVERSATION_STARTED = "conversation_started"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_EDITED = "message_edited"
    REACTION_ADDED = "reaction_added"
    REACTION_REMOVED = "reaction_removed"
    MESSAGE_PINNED = "message_pinned"
    MESSAGE_UNPINNED = "message_unpinned"

@dataclass
class UserInfo:
    """Information about a Zulip user"""
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    is_bot: bool = False

    @property
    def display_name(self) -> str:
        """Get a human-readable display name"""
        if self.username:
            return self.username

        name_parts = []
        if self.first_name:
            name_parts.append(self.first_name)
        if self.last_name:
            name_parts.append(self.last_name)
        if name_parts:
            return " ".join(name_parts)

        return f"User {self.user_id}"

@dataclass
class ThreadInfo:
    """Information about a thread within a conversation"""
    thread_id: str  # Could be message_thread_id, reply message_id, etc.
    title: Optional[str] = None  # For named threads/topics
    root_message_id: Optional[str] = None  # ID of the message that started the thread
    message_count: int = 0
    last_activity: datetime = None

    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = datetime.now()

@dataclass
class ConversationInfo:
    """Comprehensive information about a Zulip conversation"""
    # Core identifiers
    conversation_id: str
    conversation_type: str  # 'private', 'group', 'supergroup', 'channel'

    # Activity tracking
    created_at: datetime = None  # When we first saw this chat
    last_activity: datetime = None  # Last message time
    message_count: int = 0  # Count of messages seen

    # Metadata storage
    known_members: Dict[str, UserInfo] = field(default_factory=dict)
    just_started: bool = False

    # Add thread tracking
    threads: Dict[str, ThreadInfo] = field(default_factory=dict)

    # Add attachment tracking
    attachments: Set[str] = field(default_factory=set)

    # Add message tracking
    messages: Set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_activity is None:
            self.last_activity = datetime.now()

@dataclass
class ConversationDelta:
    """Changes in conversation state"""
    conversation_id: str
    conversation_type: str
    updates: List[str] = field(default_factory=list)
    message_id: Optional[str] = None
    timestamp: Optional[int] = None
    text: Optional[str] = None
    thread_id: Optional[str] = None
    sender: Optional[Dict[str, Any]] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    added_reactions: List[str] = field(default_factory=list)
    removed_reactions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {"conversation_id": self.conversation_id, "updates": self.updates}

        if self.message_id:
            result["message_id"] = self.message_id
        if self.timestamp:
            result["timestamp"] = self.timestamp
        if self.text:
            result["text"] = self.text
        if self.thread_id:
            result["thread_id"] = self.thread_id
        if self.sender:
            result["sender"] = self.sender
        if self.attachments:
            result["attachments"] = self.attachments
        if self.added_reactions:
            result["added_reactions"] = self.added_reactions
        if self.removed_reactions:
            result["removed_reactions"] = self.removed_reactions

        return result

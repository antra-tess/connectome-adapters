import emoji

from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta

class ReactionHandler:
    """Handles message reactions"""

    @staticmethod
    def add_reaction(cached_msg: CachedMessage, reaction: str) -> None:
        """Add a reaction to the message

        Args:
            cached_msg: Cached message object
            reaction: Reaction to add
        """
        if reaction in cached_msg.reactions:
            cached_msg.reactions[reaction] += 1
        else:
            cached_msg.reactions[reaction] = 1

    @staticmethod
    def remove_reaction(cached_msg: CachedMessage, reaction: str) -> None:
        """Remove a reaction from the message

        Args:
            cached_msg: Cached message object
            reaction: Reaction to remove
        """
        if reaction in cached_msg.reactions:
            cached_msg.reactions[reaction] -= 1
            if cached_msg.reactions[reaction] == 0:
                del cached_msg.reactions[reaction]

    @staticmethod
    def update_message_reactions(op: str,
                                 cached_msg: CachedMessage,
                                 reaction: str,
                                 delta: ConversationDelta) -> None:
        """Update delta with reaction changes

        Args:
            op: Operation to perform
            cached_msg: Cached message object
            reaction: Reaction to update
            delta: Current delta object
        """
        if op == "added_reaction":
            ReactionHandler.add_reaction(cached_msg, reaction)
            delta.added_reactions = [] if cached_msg.is_from_bot else [reaction]
        elif op == "removed_reaction":
            ReactionHandler.remove_reaction(cached_msg, reaction)
            delta.removed_reactions = [] if cached_msg.is_from_bot else [reaction]

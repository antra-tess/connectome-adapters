import pytest

from adapters.discord_adapter.adapter.conversation.reaction_handler import ReactionHandler
from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta

class TestReactionHandler:
    """Tests for the Discord ReactionHandler class"""

    @pytest.fixture
    def cached_message(self):
        """Create a cached message with initial reactions"""
        cached_msg = CachedMessage(
            message_id="123",
            conversation_id="456",
            text="Test message",
            sender_id="789",
            sender_name="Test User",
            timestamp=1234567890000,
            is_from_bot=False,
            thread_id=None,
            reactions={"👍": 1}  # Initial reaction
        )
        return cached_msg

    @pytest.fixture
    def bot_message(self):
        """Create a cached message from a bot"""
        cached_msg = CachedMessage(
            message_id="124",
            conversation_id="456",
            text="Bot message",
            sender_id="790",
            sender_name="Bot User",
            timestamp=1234567890001,
            is_from_bot=True,  # This is a bot message
            thread_id=None,
            reactions={"👍": 1}  # Initial reaction
        )
        return cached_msg

    @pytest.fixture
    def delta(self):
        """Create a ConversationDelta object"""
        return ConversationDelta(conversation_id="456", message_id="123")

    class TestReactionManagement:
        """Tests for reaction addition and removal"""

        def test_add_reaction_new(self, cached_message):
            """Test adding a new reaction"""
            ReactionHandler.add_reaction(cached_message, "❤️")

            assert "❤️" in cached_message.reactions
            assert cached_message.reactions["❤️"] == 1
            assert cached_message.reactions["👍"] == 1  # Original reaction still present

        def test_add_reaction_existing(self, cached_message):
            """Test increasing count of an existing reaction"""
            ReactionHandler.add_reaction(cached_message, "👍")

            assert cached_message.reactions["👍"] == 2

        def test_remove_reaction_existing(self, cached_message):
            """Test removing an existing reaction"""
            ReactionHandler.remove_reaction(cached_message, "👍")

            assert "👍" not in cached_message.reactions  # Should be removed when count reaches 0

        def test_remove_reaction_multiple(self, cached_message):
            """Test decreasing count of a reaction with multiple occurrences"""
            cached_message.reactions["❤️"] = 2

            ReactionHandler.remove_reaction(cached_message, "❤️")

            assert "❤️" in cached_message.reactions
            assert cached_message.reactions["❤️"] == 1  # Count decreased but still present

    class TestUpdateMessageReactions:
        """Tests for the update_message_reactions method"""

        def test_update_message_reactions_add(self, cached_message, delta):
            """Test updating delta when a reaction is added"""
            ReactionHandler.update_message_reactions(
                "added_reaction", cached_message, "❤️", delta
            )

            assert len(delta.added_reactions) == 1
            assert delta.added_reactions[0] == "❤️"
            assert not delta.removed_reactions

            assert "❤️" in cached_message.reactions
            assert cached_message.reactions["❤️"] == 1

        def test_update_message_reactions_remove(self, cached_message, delta):
            """Test updating delta when a reaction is removed"""
            ReactionHandler.update_message_reactions(
                "removed_reaction", cached_message, "👍", delta
            )

            assert len(delta.removed_reactions) == 1
            assert delta.removed_reactions[0] == "👍"
            assert not delta.added_reactions
            assert "👍" not in cached_message.reactions  # Should be removed

        def test_bot_message_reactions_add(self, bot_message, delta):
            """Test reactions on bot messages are not included in delta"""
            ReactionHandler.update_message_reactions(
                "added_reaction", bot_message, "❤️", delta
            )

            # Message should be updated
            assert "❤️" in bot_message.reactions
            assert bot_message.reactions["❤️"] == 1

            # But delta should have empty lists rather than the reaction
            assert delta.added_reactions == []
            assert not delta.removed_reactions

        def test_bot_message_reactions_remove(self, bot_message, delta):
            """Test reaction removal on bot messages are not included in delta"""
            ReactionHandler.update_message_reactions(
                "removed_reaction", bot_message, "👍", delta
            )

            # Message should be updated
            assert "👍" not in bot_message.reactions

            # But delta should have empty lists rather than the reaction
            assert delta.removed_reactions == []
            assert not delta.added_reactions

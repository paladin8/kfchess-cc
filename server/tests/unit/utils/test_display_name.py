"""Tests for display name utilities."""


from kfchess.utils.display_name import (
    extract_user_ids,
    format_player_id,
)


class TestFormatPlayerId:
    """Tests for format_player_id function."""

    def test_format_user_with_username_map(self) -> None:
        """Should return username when found in map."""
        username_map = {123: "TestUser"}
        result = format_player_id("u:123", username_map)
        assert result == "TestUser"

    def test_format_user_without_username_map(self) -> None:
        """Should return fallback when no map provided."""
        result = format_player_id("u:123")
        assert result == "User 123"

    def test_format_user_not_in_map(self) -> None:
        """Should return fallback when user not in map."""
        username_map = {456: "OtherUser"}
        result = format_player_id("u:123", username_map)
        assert result == "User 123"

    def test_format_guest(self) -> None:
        """Should return 'Guest' for guest players."""
        result = format_player_id("guest:abc123")
        assert result == "Guest"

    def test_format_bot_dummy(self) -> None:
        """Should format bot:dummy as 'AI (Dummy)'."""
        result = format_player_id("bot:dummy")
        assert result == "AI (Dummy)"

    def test_format_bot_mcts(self) -> None:
        """Should format bot:mcts as 'AI (Mcts)'."""
        result = format_player_id("bot:mcts")
        assert result == "AI (Mcts)"

    def test_format_unknown(self) -> None:
        """Should return as-is for unknown format."""
        result = format_player_id("some_unknown_format")
        assert result == "some_unknown_format"


class TestExtractUserIds:
    """Tests for extract_user_ids function."""

    def test_extract_single_user(self) -> None:
        """Should extract single user ID."""
        result = extract_user_ids(["u:123"])
        assert result == [123]

    def test_extract_multiple_users(self) -> None:
        """Should extract multiple user IDs."""
        result = extract_user_ids(["u:123", "u:456"])
        assert result == [123, 456]

    def test_ignore_guests(self) -> None:
        """Should ignore guest player IDs."""
        result = extract_user_ids(["u:123", "guest:abc"])
        assert result == [123]

    def test_ignore_bots(self) -> None:
        """Should ignore bot player IDs."""
        result = extract_user_ids(["u:123", "bot:dummy"])
        assert result == [123]

    def test_mixed_players(self) -> None:
        """Should handle mixed player types."""
        result = extract_user_ids(["u:1", "guest:abc", "u:2", "bot:dummy", "u:3"])
        assert result == [1, 2, 3]

    def test_empty_list(self) -> None:
        """Should handle empty list."""
        result = extract_user_ids([])
        assert result == []

    def test_no_users(self) -> None:
        """Should handle list with no users."""
        result = extract_user_ids(["guest:abc", "bot:dummy"])
        assert result == []

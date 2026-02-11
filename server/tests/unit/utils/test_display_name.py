"""Tests for display name utilities."""

from unittest.mock import AsyncMock, patch

import pytest

from kfchess.utils.display_name import (
    PlayerDisplay,
    _resolve_from_info,
    _UserInfo,
    extract_user_ids,
    format_player_id,
    resolve_player_info,
    resolve_player_info_batch,
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

    def test_format_legacy_bot(self) -> None:
        """Should format legacy b:novice as 'AI (Novice)'."""
        result = format_player_id("b:novice")
        assert result == "AI (Novice)"

    def test_format_legacy_bot_intermediate(self) -> None:
        """Should format legacy b:intermediate as 'AI (Intermediate)'."""
        result = format_player_id("b:intermediate")
        assert result == "AI (Intermediate)"

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


class TestResolveFromInfo:
    """Tests for _resolve_from_info function."""

    def test_registered_user_found(self) -> None:
        """Should resolve user with picture_url from info map."""
        info_map = {10: _UserInfo("alice", "https://pic.com/a.jpg")}
        result = _resolve_from_info({1: "u:10"}, info_map)
        assert result[1] == PlayerDisplay(name="alice", picture_url="https://pic.com/a.jpg", user_id=10)

    def test_registered_user_not_found(self) -> None:
        """Should fallback when user not in info map."""
        result = _resolve_from_info({1: "u:99"}, {})
        assert result[1] == PlayerDisplay(name="User 99", picture_url=None, user_id=99)

    def test_registered_user_no_picture(self) -> None:
        """Should handle user with no picture_url."""
        info_map = {10: _UserInfo("alice", None)}
        result = _resolve_from_info({1: "u:10"}, info_map)
        assert result[1].picture_url is None
        assert result[1].name == "alice"

    def test_invalid_user_id_format(self) -> None:
        """Should handle non-numeric user ID."""
        result = _resolve_from_info({1: "u:notanumber"}, {})
        assert result[1] == PlayerDisplay(name="u:notanumber", picture_url=None, user_id=None)

    def test_guest_player(self) -> None:
        """Should resolve guest player."""
        result = _resolve_from_info({1: "guest:abc"}, {})
        assert result[1] == PlayerDisplay(name="Guest", picture_url=None, user_id=None)

    def test_bot_player(self) -> None:
        """Should resolve bot player."""
        result = _resolve_from_info({1: "bot:dummy"}, {})
        assert result[1] == PlayerDisplay(name="AI (Dummy)", picture_url=None, user_id=None, is_bot=True)

    def test_legacy_bot_player(self) -> None:
        """Should resolve legacy b: bot player with is_bot=True."""
        result = _resolve_from_info({1: "b:novice"}, {})
        assert result[1] == PlayerDisplay(name="AI (Novice)", picture_url=None, user_id=None, is_bot=True)

    def test_mixed_players(self) -> None:
        """Should handle mixed player types."""
        info_map = {10: _UserInfo("alice", "https://pic.com/a.jpg")}
        result = _resolve_from_info(
            {1: "u:10", 2: "bot:dummy", 3: "guest:x"},
            info_map,
        )
        assert len(result) == 3
        assert result[1].name == "alice"
        assert result[1].picture_url == "https://pic.com/a.jpg"
        assert result[2].name == "AI (Dummy)"
        assert result[3].name == "Guest"

    def test_empty_players(self) -> None:
        """Should handle empty players dict."""
        result = _resolve_from_info({}, {})
        assert result == {}


class TestResolvePlayerInfo:
    """Tests for resolve_player_info async function."""

    @pytest.mark.asyncio
    async def test_resolves_with_db(self) -> None:
        """Should fetch user info and resolve players."""
        mock_session = AsyncMock()
        with patch(
            "kfchess.utils.display_name._fetch_user_info",
            return_value={5: _UserInfo("bob", "https://pic.com/b.jpg")},
        ):
            result = await resolve_player_info(mock_session, {1: "u:5", 2: "bot:dummy"})
        assert result[1].name == "bob"
        assert result[1].picture_url == "https://pic.com/b.jpg"
        assert result[2].name == "AI (Dummy)"


class TestResolvePlayerInfoBatch:
    """Tests for resolve_player_info_batch function."""

    @pytest.mark.asyncio
    async def test_single_query_for_multiple_dicts(self) -> None:
        """Should make one DB call for all player dicts."""
        mock_session = AsyncMock()
        with patch(
            "kfchess.utils.display_name._fetch_user_info",
            return_value={
                1: _UserInfo("alice", None),
                2: _UserInfo("bob", "https://pic.com/b.jpg"),
            },
        ) as mock_fetch:
            result = await resolve_player_info_batch(
                mock_session,
                [
                    {1: "u:1", 2: "u:2"},
                    {1: "u:1", 2: "bot:dummy"},
                ],
            )
        # Called exactly once
        mock_fetch.assert_awaited_once()
        # Deduplicates user IDs
        call_user_ids = set(mock_fetch.call_args[0][1])
        assert call_user_ids == {1, 2}

        assert len(result) == 2
        assert result[0][1].name == "alice"
        assert result[0][2].name == "bob"
        assert result[1][1].name == "alice"
        assert result[1][2].name == "AI (Dummy)"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        """Should handle empty list."""
        mock_session = AsyncMock()
        with patch("kfchess.utils.display_name._fetch_user_info", return_value={}):
            result = await resolve_player_info_batch(mock_session, [])
        assert result == []

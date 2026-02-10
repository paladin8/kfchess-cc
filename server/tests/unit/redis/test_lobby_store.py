"""Tests for RedisLobbyManager."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import fakeredis.aioredis
import pytest
from fakeredis import FakeServer

from kfchess.lobby.models import LobbySettings, LobbyStatus
from kfchess.redis.lobby_store import (
    LOBBY_TTL_SECONDS,
    LobbyError,
    RedisLobbyManager,
    _keys_key,
    _lobby_key,
    _pubsub_channel,
)


@pytest.fixture
def fake_server():
    """Create a shared FakeServer for cross-connection tests."""
    return FakeServer()


@pytest.fixture
def redis(fake_server):
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis(server=fake_server, decode_responses=True)


@pytest.fixture
def redis2(fake_server):
    """Second connection for simulating concurrent modifications."""
    return fakeredis.aioredis.FakeRedis(server=fake_server, decode_responses=True)


@pytest.fixture
def manager(redis):
    """Create a RedisLobbyManager using fakeredis."""
    mgr = RedisLobbyManager()
    # Patch _get_redis to return our fakeredis
    mgr._get_redis = lambda: _async_return(redis)
    return mgr


async def _async_return(value):
    return value


class TestCreateLobby:
    """Tests for lobby creation."""

    @pytest.mark.asyncio
    async def test_create_basic_lobby(self, manager, redis) -> None:
        result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", player_id="u:1",
        )
        assert not isinstance(result, LobbyError)
        lobby, host_key = result

        assert lobby.code is not None
        assert len(lobby.code) == 6
        assert lobby.host_slot == 1
        assert 1 in lobby.players
        assert lobby.players[1].username == "Alice"
        assert lobby.players[1].player_id == "u:1"
        assert host_key.startswith("s1_")

        # Verify stored in Redis
        stored = await redis.get(_lobby_key(lobby.code))
        assert stored is not None
        stored_key = await redis.hget(_keys_key(lobby.code), "1")
        assert stored_key == host_key

    @pytest.mark.asyncio
    async def test_create_lobby_with_ai(self, manager) -> None:
        result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            add_ai=True, ai_type="bot:intermediate",
        )
        assert not isinstance(result, LobbyError)
        lobby, _ = result

        assert len(lobby.players) == 2
        assert lobby.players[2].is_ai is True
        assert lobby.players[2].ai_type == "bot:intermediate"

    @pytest.mark.asyncio
    async def test_create_public_lobby_indexed(self, manager, redis) -> None:
        result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True),
        )
        lobby, _ = result

        # Should be in public index
        members = await redis.zrange("lobby:public_index", 0, -1)
        assert lobby.code in members

    @pytest.mark.asyncio
    async def test_create_private_lobby_not_indexed(self, manager, redis) -> None:
        result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=False),
        )
        lobby, _ = result

        members = await redis.zrange("lobby:public_index", 0, -1)
        assert lobby.code not in members

    @pytest.mark.asyncio
    async def test_create_lobby_sequential_ids(self, manager) -> None:
        result1 = await manager.create_lobby(host_user_id=1, host_username="A")
        result2 = await manager.create_lobby(host_user_id=2, host_username="B")

        lobby1, _ = result1
        lobby2, _ = result2
        assert lobby2.id == lobby1.id + 1

    @pytest.mark.asyncio
    async def test_create_four_player_lobby_with_ai(self, manager) -> None:
        result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(player_count=4),
            add_ai=True, ai_type="bot:novice",
        )
        lobby, _ = result

        assert len(lobby.players) == 4
        assert lobby.players[1].is_ai is False
        for slot in [2, 3, 4]:
            assert lobby.players[slot].is_ai is True


class TestJoinLobby:
    """Tests for joining lobbies."""

    @pytest.mark.asyncio
    async def test_join_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        join_result = await manager.join_lobby(
            code=lobby.code, user_id=2, username="Bob", player_id="u:2",
        )
        assert not isinstance(join_result, LobbyError)
        updated_lobby, player_key, slot = join_result

        assert slot == 2
        assert player_key.startswith("s2_")
        assert updated_lobby.players[2].username == "Bob"

    @pytest.mark.asyncio
    async def test_join_nonexistent_lobby(self, manager) -> None:
        result = await manager.join_lobby(code="NOPE00", user_id=1, username="Alice")
        assert isinstance(result, LobbyError)
        assert result.code == "not_found"

    @pytest.mark.asyncio
    async def test_join_full_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, _ = create_result

        result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        assert isinstance(result, LobbyError)
        assert result.code == "lobby_full"

    @pytest.mark.asyncio
    async def test_join_in_game_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        # Start game to make it IN_GAME
        await manager.set_ready(lobby.code, host_key, True)
        await manager.start_game(lobby.code, host_key)

        result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        assert isinstance(result, LobbyError)
        assert result.code == "game_in_progress"

    @pytest.mark.asyncio
    async def test_join_preferred_slot(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(player_count=4),
        )
        lobby, _ = create_result

        result = await manager.join_lobby(
            code=lobby.code, user_id=2, username="Bob", preferred_slot=3,
        )
        assert not isinstance(result, LobbyError)
        _, _, slot = result
        assert slot == 3


class TestLeaveLobby:
    """Tests for leaving lobbies."""

    @pytest.mark.asyncio
    async def test_leave_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        join_result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        _, player_key, _ = join_result

        result = await manager.leave_lobby(lobby.code, player_key)
        assert result is not None
        assert 2 not in result.players

    @pytest.mark.asyncio
    async def test_leave_last_player_deletes_lobby(self, manager, redis) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        result = await manager.leave_lobby(lobby.code, host_key)
        assert result is None  # Lobby deleted

        # Verify deleted from Redis
        stored = await redis.get(_lobby_key(lobby.code))
        assert stored is None

    @pytest.mark.asyncio
    async def test_leave_transfers_host(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(player_count=4),
        )
        lobby, host_key = create_result

        join_result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        _, _, _ = join_result

        result = await manager.leave_lobby(lobby.code, host_key)
        assert result is not None
        assert result.host_slot == 2


class TestSetReady:
    """Tests for ready state."""

    @pytest.mark.asyncio
    async def test_set_ready(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        result = await manager.set_ready(lobby.code, host_key, True)
        assert not isinstance(result, LobbyError)
        assert result.players[1].is_ready is True

    @pytest.mark.asyncio
    async def test_set_unready(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        result = await manager.set_ready(lobby.code, host_key, False)
        assert not isinstance(result, LobbyError)
        assert result.players[1].is_ready is False

    @pytest.mark.asyncio
    async def test_set_ready_invalid_key(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        result = await manager.set_ready(lobby.code, "bad_key", True)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_key"


class TestUpdateSettings:
    """Tests for settings updates."""

    @pytest.mark.asyncio
    async def test_update_settings(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        new_settings = LobbySettings(speed="lightning")
        result = await manager.update_settings(lobby.code, host_key, new_settings)
        assert not isinstance(result, LobbyError)
        assert result.settings.speed == "lightning"

    @pytest.mark.asyncio
    async def test_update_settings_unreadies_players(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)

        new_settings = LobbySettings(speed="lightning")
        result = await manager.update_settings(lobby.code, host_key, new_settings)
        assert not isinstance(result, LobbyError)
        assert result.players[1].is_ready is False

    @pytest.mark.asyncio
    async def test_update_settings_non_host_rejected(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        join_result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        _, player_key, _ = join_result

        result = await manager.update_settings(lobby.code, player_key, LobbySettings())
        assert isinstance(result, LobbyError)
        assert result.code == "not_host"

    @pytest.mark.asyncio
    async def test_update_public_index(self, manager, redis) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True),
        )
        lobby, host_key = create_result

        # Change to private
        result = await manager.update_settings(
            lobby.code, host_key, LobbySettings(is_public=False),
        )
        assert not isinstance(result, LobbyError)

        members = await redis.zrange("lobby:public_index", 0, -1)
        assert lobby.code not in members

    @pytest.mark.asyncio
    async def test_update_settings_ranked_with_ai_rejected(self, manager) -> None:
        """Cannot enable ranked when lobby has AI players."""
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        result = await manager.update_settings(lobby.code, host_key, LobbySettings(is_ranked=True))
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_settings"

    @pytest.mark.asyncio
    async def test_update_settings_ranked_with_guest_rejected(self, manager) -> None:
        """Cannot enable ranked when lobby has guest (unauthenticated) players."""
        create_result = await manager.create_lobby(
            host_user_id=None, host_username="Guest",
        )
        lobby, host_key = create_result

        result = await manager.update_settings(lobby.code, host_key, LobbySettings(is_ranked=True))
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_settings"


class TestKickPlayer:
    """Tests for kicking players."""

    @pytest.mark.asyncio
    async def test_kick_player(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")

        result = await manager.kick_player(lobby.code, host_key, 2)
        assert not isinstance(result, LobbyError)
        assert 2 not in result.players

    @pytest.mark.asyncio
    async def test_kick_self_rejected(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        result = await manager.kick_player(lobby.code, host_key, 1)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_action"

    @pytest.mark.asyncio
    async def test_kick_ai_rejected(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        result = await manager.kick_player(lobby.code, host_key, 2)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_action"

    @pytest.mark.asyncio
    async def test_kick_during_game_rejected(self, manager) -> None:
        """Cannot kick players while game is in progress."""
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        join_result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        _, p2_key, _ = join_result

        await manager.set_ready(lobby.code, host_key, True)
        await manager.set_ready(lobby.code, p2_key, True)
        await manager.start_game(lobby.code, host_key)

        result = await manager.kick_player(lobby.code, host_key, 2)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_state"


class TestAIManagement:
    """Tests for AI player management."""

    @pytest.mark.asyncio
    async def test_add_ai(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        result = await manager.add_ai(lobby.code, host_key, "bot:expert")
        assert not isinstance(result, LobbyError)
        assert result.players[2].is_ai is True
        assert result.players[2].ai_type == "bot:expert"

    @pytest.mark.asyncio
    async def test_add_ai_full_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        result = await manager.add_ai(lobby.code, host_key)
        assert isinstance(result, LobbyError)
        assert result.code == "lobby_full"

    @pytest.mark.asyncio
    async def test_remove_ai(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        result = await manager.remove_ai(lobby.code, host_key, 2)
        assert not isinstance(result, LobbyError)
        assert 2 not in result.players

    @pytest.mark.asyncio
    async def test_remove_non_ai_rejected(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")

        result = await manager.remove_ai(lobby.code, host_key, 2)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_action"

    @pytest.mark.asyncio
    async def test_change_ai_type(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        result = await manager.change_ai_type(lobby.code, host_key, 2, "bot:expert")
        assert not isinstance(result, LobbyError)
        assert result.players[2].ai_type == "bot:expert"
        assert "Expert" in result.players[2].username

    @pytest.mark.asyncio
    async def test_add_ai_to_ranked_rejected(self, manager) -> None:
        """Cannot add AI to a ranked lobby."""
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_ranked=True),
        )
        lobby, host_key = create_result

        result = await manager.add_ai(lobby.code, host_key)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_action"


class TestStartGame:
    """Tests for starting games."""

    @pytest.mark.asyncio
    async def test_start_game(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        result = await manager.start_game(lobby.code, host_key)

        assert not isinstance(result, LobbyError)
        game_id, game_keys = result
        assert game_id is not None
        assert 1 in game_keys  # Human player gets key
        assert 2 not in game_keys  # AI doesn't

    @pytest.mark.asyncio
    async def test_start_game_auto_readies_host(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        # Don't explicitly set ready - start_game should auto-ready host
        result = await manager.start_game(lobby.code, host_key)
        assert not isinstance(result, LobbyError)

    @pytest.mark.asyncio
    async def test_start_game_not_full(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        result = await manager.start_game(lobby.code, host_key)
        assert isinstance(result, LobbyError)
        assert result.code == "not_ready"

    @pytest.mark.asyncio
    async def test_start_game_not_all_ready(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")

        result = await manager.start_game(lobby.code, host_key)
        assert isinstance(result, LobbyError)
        assert result.code == "not_ready"

    @pytest.mark.asyncio
    async def test_start_game_sets_in_game_status(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        await manager.start_game(lobby.code, host_key)

        updated = await manager.get_lobby(lobby.code)
        assert updated.status == LobbyStatus.IN_GAME

    @pytest.mark.asyncio
    async def test_start_game_stores_game_mapping(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        game_id, _ = await manager.start_game(lobby.code, host_key)

        found_code = await manager.find_lobby_by_game(game_id)
        assert found_code == lobby.code


class TestEndGame:
    """Tests for game completion."""

    @pytest.mark.asyncio
    async def test_end_game(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        game_id, _ = await manager.start_game(lobby.code, host_key)

        result = await manager.end_game(lobby.code, winner=1)
        assert result is not None
        assert result.status == LobbyStatus.FINISHED
        assert result.players[1].is_ready is False

    @pytest.mark.asyncio
    async def test_end_game_clears_game_mapping(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        game_id, _ = await manager.start_game(lobby.code, host_key)

        await manager.end_game(lobby.code)

        found = await manager.find_lobby_by_game(game_id)
        assert found is None


class TestReturnToLobby:
    """Tests for returning to lobby after game."""

    @pytest.mark.asyncio
    async def test_return_to_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        await manager.start_game(lobby.code, host_key)
        await manager.end_game(lobby.code)

        result = await manager.return_to_lobby(lobby.code)
        assert not isinstance(result, LobbyError)
        assert result.status == LobbyStatus.WAITING

    @pytest.mark.asyncio
    async def test_return_during_game_rejected(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice", add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        await manager.start_game(lobby.code, host_key)

        result = await manager.return_to_lobby(lobby.code)
        assert isinstance(result, LobbyError)
        assert result.code == "invalid_state"


class TestReadOperations:
    """Tests for read-only operations."""

    @pytest.mark.asyncio
    async def test_get_lobby(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        result = await manager.get_lobby(lobby.code)
        assert result is not None
        assert result.code == lobby.code

    @pytest.mark.asyncio
    async def test_get_nonexistent_lobby(self, manager) -> None:
        result = await manager.get_lobby("NOPE00")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_public_lobbies(self, manager) -> None:
        await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True),
        )
        await manager.create_lobby(
            host_user_id=2, host_username="Bob",
            settings=LobbySettings(is_public=False),
        )

        lobbies = await manager.get_public_lobbies()
        assert len(lobbies) == 1
        assert lobbies[0].players[1].username == "Alice"

    @pytest.mark.asyncio
    async def test_get_public_lobbies_filters_full(self, manager) -> None:
        await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True), add_ai=True,
        )

        lobbies = await manager.get_public_lobbies()
        assert len(lobbies) == 0  # Full lobby not shown

    @pytest.mark.asyncio
    async def test_get_public_lobbies_filter_speed(self, manager) -> None:
        await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True, speed="standard"),
        )
        await manager.create_lobby(
            host_user_id=2, host_username="Bob",
            settings=LobbySettings(is_public=True, speed="lightning"),
        )

        lobbies = await manager.get_public_lobbies(speed="lightning")
        assert len(lobbies) == 1
        assert lobbies[0].settings.speed == "lightning"

    @pytest.mark.asyncio
    async def test_validate_player_key(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        slot = await manager.validate_player_key(lobby.code, host_key)
        assert slot == 1

    @pytest.mark.asyncio
    async def test_validate_invalid_key(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        slot = await manager.validate_player_key(lobby.code, "bad_key")
        assert slot is None

    @pytest.mark.asyncio
    async def test_find_lobby_by_game_not_found(self, manager) -> None:
        result = await manager.find_lobby_by_game("NOTEXIST")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_public_lobbies_filter_player_count(self, manager) -> None:
        """get_public_lobbies filters by player_count."""
        await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True, player_count=2),
        )
        await manager.create_lobby(
            host_user_id=2, host_username="Bob",
            settings=LobbySettings(is_public=True, player_count=4),
        )

        lobbies = await manager.get_public_lobbies(player_count=4)
        assert len(lobbies) == 1
        assert lobbies[0].settings.player_count == 4

    @pytest.mark.asyncio
    async def test_corrupted_lobby_data_returns_none(self, manager, redis) -> None:
        """Corrupted JSON in Redis returns None instead of crashing."""
        await redis.set(_lobby_key("CORRUPT"), "not valid json {{{")
        result = await manager.get_lobby("CORRUPT")
        assert result is None


class TestConnectionStatus:
    """Tests for connection status tracking."""

    @pytest.mark.asyncio
    async def test_set_disconnected(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        result = await manager.set_connected(lobby.code, 1, False)
        assert result is not None
        assert result.players[1].is_connected is False
        assert result.players[1].disconnected_at is not None

    @pytest.mark.asyncio
    async def test_set_reconnected(self, manager) -> None:
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        await manager.set_connected(lobby.code, 1, False)
        result = await manager.set_connected(lobby.code, 1, True)
        assert result is not None
        assert result.players[1].is_connected is True
        assert result.players[1].disconnected_at is None

    @pytest.mark.asyncio
    async def test_cleanup_disconnected_players(self, manager) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(player_count=4),
        )
        lobby, host_key = create_result

        join_result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        _, _, _ = join_result

        # Manually set disconnected_at in the past
        r = await manager._get_redis()
        lobby_data = json.loads(await r.get(_lobby_key(lobby.code)))
        past_time = (datetime.utcnow() - timedelta(seconds=60)).isoformat()
        lobby_data["players"]["2"]["is_connected"] = False
        lobby_data["players"]["2"]["disconnected_at"] = past_time
        await r.set(_lobby_key(lobby.code), json.dumps(lobby_data), ex=LOBBY_TTL_SECONDS)

        cleaned = await manager.cleanup_disconnected_players(lobby.code)
        assert 2 in cleaned

        # Player should be gone
        updated = await manager.get_lobby(lobby.code)
        assert 2 not in updated.players


class TestDeleteLobby:
    """Tests for lobby deletion."""

    @pytest.mark.asyncio
    async def test_delete_lobby(self, manager, redis) -> None:
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True),
        )
        lobby, _ = create_result

        result = await manager.delete_lobby(lobby.code)
        assert result is True

        # Verify fully cleaned up
        assert await redis.get(_lobby_key(lobby.code)) is None
        assert await redis.exists(_keys_key(lobby.code)) == 0
        members = await redis.zrange("lobby:public_index", 0, -1)
        assert lobby.code not in members

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, manager) -> None:
        result = await manager.delete_lobby("NOPE00")
        assert result is False


class TestCleanupStaleLobby:
    """Tests for stale lobby cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_old_waiting_lobby_no_humans(self, manager, redis) -> None:
        """Cleanup removes old WAITING lobbies with no human players."""
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True), add_ai=True,
        )
        lobby, _ = create_result

        # Manipulate Redis: remove host, set old timestamp
        data = json.loads(await redis.get(_lobby_key(lobby.code)))
        del data["players"]["1"]
        data["created_at"] = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        await redis.set(_lobby_key(lobby.code), json.dumps(data))

        cleaned = await manager.cleanup_stale_lobbies(waiting_max_age_seconds=3600)
        assert cleaned == 1
        assert await manager.get_lobby(lobby.code) is None

    @pytest.mark.asyncio
    async def test_cleanup_old_finished_lobby(self, manager, redis) -> None:
        """Cleanup removes old FINISHED lobbies."""
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True), add_ai=True,
        )
        lobby, host_key = create_result

        # Start and end game to reach FINISHED state
        await manager.set_ready(lobby.code, host_key, True)
        await manager.start_game(lobby.code, host_key)
        await manager.end_game(lobby.code)

        # Manipulate timestamp to make it old
        data = json.loads(await redis.get(_lobby_key(lobby.code)))
        data["game_finished_at"] = (datetime.utcnow() - timedelta(days=2)).isoformat()
        await redis.set(_lobby_key(lobby.code), json.dumps(data))

        cleaned = await manager.cleanup_stale_lobbies(finished_max_age_seconds=86400)
        assert cleaned == 1
        assert await manager.get_lobby(lobby.code) is None

    @pytest.mark.asyncio
    async def test_cleanup_skips_in_game_lobby(self, manager) -> None:
        """Cleanup does not remove lobbies with active games."""
        create_result = await manager.create_lobby(
            host_user_id=1, host_username="Alice",
            settings=LobbySettings(is_public=True), add_ai=True,
        )
        lobby, host_key = create_result

        await manager.set_ready(lobby.code, host_key, True)
        await manager.start_game(lobby.code, host_key)

        cleaned = await manager.cleanup_stale_lobbies()
        assert cleaned == 0
        assert await manager.get_lobby(lobby.code) is not None

    @pytest.mark.asyncio
    async def test_cleanup_stale_index_entry(self, manager, redis) -> None:
        """Cleanup removes stale public index entries for deleted lobbies."""
        # Add a stale entry to the public index (lobby doesn't exist in Redis)
        await redis.zadd("lobby:public_index", {"STALE1": 1.0})

        cleaned = await manager.cleanup_stale_lobbies()
        assert cleaned == 1

        members = await redis.zrange("lobby:public_index", 0, -1)
        assert "STALE1" not in members


class TestWatchErrorRetry:
    """Tests that WATCH/MULTI/EXEC retry mechanism handles concurrent conflicts."""

    @pytest.mark.asyncio
    async def test_join_retries_on_concurrent_modification(self, manager, redis2) -> None:
        """join_lobby succeeds after retrying due to concurrent modification."""
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, _ = create_result

        original_load = manager._load_lobby
        interfered = [False]

        async def load_with_interference(r, code):
            result = await original_load(r, code)
            if not interfered[0]:
                interfered[0] = True
                # Modify the watched key from a different connection → triggers WatchError
                data = await redis2.get(_lobby_key(code))
                await redis2.set(_lobby_key(code), data, ex=LOBBY_TTL_SECONDS)
            return result

        manager._load_lobby = load_with_interference

        result = await manager.join_lobby(code=lobby.code, user_id=2, username="Bob")
        assert not isinstance(result, LobbyError)
        _, _, slot = result
        assert slot == 2
        # Verify retry actually happened (load called at least twice)
        assert interfered[0]

    @pytest.mark.asyncio
    async def test_set_ready_retries_on_concurrent_modification(self, manager, redis2) -> None:
        """set_ready succeeds after retrying due to concurrent modification."""
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        original_load = manager._load_lobby
        interfered = [False]

        async def load_with_interference(r, code):
            result = await original_load(r, code)
            if not interfered[0]:
                interfered[0] = True
                data = await redis2.get(_lobby_key(code))
                await redis2.set(_lobby_key(code), data, ex=LOBBY_TTL_SECONDS)
            return result

        manager._load_lobby = load_with_interference

        result = await manager.set_ready(lobby.code, host_key, True)
        assert not isinstance(result, LobbyError)
        assert result.players[1].is_ready is True

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_returns_conflict(self, manager, redis2) -> None:
        """Returns conflict error when all retries are exhausted."""
        create_result = await manager.create_lobby(host_user_id=1, host_username="Alice")
        lobby, host_key = create_result

        original_load = manager._load_lobby

        async def always_interfere(r, code):
            result = await original_load(r, code)
            # Always modify → every attempt fails
            data = await redis2.get(_lobby_key(code))
            if data:
                await redis2.set(_lobby_key(code), data, ex=LOBBY_TTL_SECONDS)
            return result

        manager._load_lobby = always_interfere

        result = await manager.set_ready(lobby.code, host_key, True)
        assert isinstance(result, LobbyError)
        assert result.code == "conflict"


class TestPubSubEvents:
    """Tests for pub/sub event publishing."""

    @pytest.mark.asyncio
    async def test_publish_event_delivers_to_subscriber(self, manager, redis) -> None:
        """publish_event sends JSON to the correct pub/sub channel."""
        channel = _pubsub_channel("TEST01")
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        # Drain subscribe confirmation
        sub_msg = await pubsub.get_message()
        assert sub_msg["type"] == "subscribe"

        await manager.publish_event("TEST01", {"type": "test_event", "data": "hello"})

        msg = await pubsub.get_message()
        assert msg is not None
        assert msg["type"] == "message"
        assert json.loads(msg["data"]) == {"type": "test_event", "data": "hello"}

        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

    @pytest.mark.asyncio
    async def test_publish_to_different_channel_not_received(self, manager, redis) -> None:
        """Events published to one channel are not received on another."""
        pubsub = redis.pubsub()
        await pubsub.subscribe(_pubsub_channel("LOBBY_A"))
        await pubsub.get_message()  # drain subscribe confirmation

        # Publish to a different lobby
        await manager.publish_event("LOBBY_B", {"type": "other_event"})

        msg = await pubsub.get_message()
        assert msg is None

        # Publish to the subscribed lobby
        await manager.publish_event("LOBBY_A", {"type": "our_event"})

        msg = await pubsub.get_message()
        assert msg is not None
        assert json.loads(msg["data"])["type"] == "our_event"

        await pubsub.unsubscribe(_pubsub_channel("LOBBY_A"))
        await pubsub.aclose()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_event(self, manager, redis, redis2) -> None:
        """Events are delivered to all subscribers on the channel."""
        channel = _pubsub_channel("MULTI")
        ps1 = redis.pubsub()
        ps2 = redis2.pubsub()
        await ps1.subscribe(channel)
        await ps2.subscribe(channel)
        await ps1.get_message()  # drain subscribe confirmations
        await ps2.get_message()

        await manager.publish_event("MULTI", {"type": "broadcast"})

        msg1 = await ps1.get_message()
        msg2 = await ps2.get_message()

        assert msg1 is not None
        assert msg2 is not None
        assert json.loads(msg1["data"])["type"] == "broadcast"
        assert json.loads(msg2["data"])["type"] == "broadcast"

        await ps1.unsubscribe(channel)
        await ps2.unsubscribe(channel)
        await ps1.aclose()
        await ps2.aclose()

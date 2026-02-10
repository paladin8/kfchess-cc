"""Tests for Redis snapshot store."""

from __future__ import annotations

import json
import time

import fakeredis.aioredis
import pytest

from kfchess.game.snapshot import GameSnapshot
from kfchess.redis.snapshot_store import (
    SNAPSHOT_TTL_SECONDS,
    delete_snapshot,
    list_snapshot_game_ids,
    load_snapshot,
    save_snapshot,
)


@pytest.fixture
def redis():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _make_snapshot(game_id: str = "TEST1234", **kwargs) -> GameSnapshot:
    """Create a minimal test snapshot."""
    defaults = {
        "game_id": game_id,
        "state": {
            "game_id": game_id,
            "speed": "standard",
            "board_type": "standard",
            "board_width": 8,
            "board_height": 8,
            "players": {"1": "u:1", "2": "bot:novice"},
            "current_tick": 100,
            "status": "playing",
            "winner": None,
            "win_reason": None,
            "ready_players": [1, 2],
            "pieces": [],
            "active_moves": [],
            "cooldowns": [],
            "replay_moves": [],
            "last_move_tick": 90,
            "last_capture_tick": 50,
            "started_at": None,
            "finished_at": None,
        },
        "player_keys": {1: "p1_abc123"},
        "ai_config": {2: "novice"},
        "server_id": "worker1",
        "snapshot_tick": 100,
        "snapshot_time": time.time(),
    }
    defaults.update(kwargs)
    return GameSnapshot(**defaults)


class TestSaveSnapshot:
    """Tests for save_snapshot."""

    @pytest.mark.asyncio
    async def test_save_and_load_round_trip(self, redis) -> None:
        """Snapshot saved to Redis can be loaded back."""
        snapshot = _make_snapshot()
        await save_snapshot(redis, snapshot)

        loaded = await load_snapshot(redis, "TEST1234")
        assert loaded is not None
        assert loaded.game_id == "TEST1234"
        assert loaded.player_keys == {1: "p1_abc123"}
        assert loaded.ai_config == {2: "novice"}
        assert loaded.server_id == "worker1"
        assert loaded.snapshot_tick == 100

    @pytest.mark.asyncio
    async def test_save_sets_ttl(self, redis) -> None:
        """Snapshot key has the correct TTL."""
        snapshot = _make_snapshot()
        await save_snapshot(redis, snapshot)

        ttl = await redis.ttl("game:TEST1234:snapshot")
        assert 0 < ttl <= SNAPSHOT_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, redis) -> None:
        """Saving again overwrites the previous snapshot."""
        snapshot1 = _make_snapshot(snapshot_tick=100)
        await save_snapshot(redis, snapshot1)

        snapshot2 = _make_snapshot(snapshot_tick=200)
        await save_snapshot(redis, snapshot2)

        loaded = await load_snapshot(redis, "TEST1234")
        assert loaded is not None
        assert loaded.snapshot_tick == 200

    @pytest.mark.asyncio
    async def test_save_stores_valid_json(self, redis) -> None:
        """Stored value is valid JSON."""
        snapshot = _make_snapshot()
        await save_snapshot(redis, snapshot)

        raw = await redis.get("game:TEST1234:snapshot")
        data = json.loads(raw)
        assert data["game_id"] == "TEST1234"

    @pytest.mark.asyncio
    async def test_save_with_campaign_fields(self, redis) -> None:
        """Campaign-specific fields are preserved."""
        snapshot = _make_snapshot(
            campaign_level_id=5,
            campaign_user_id=42,
            initial_board_str="rnbqkbnr/pppppppp",
        )
        await save_snapshot(redis, snapshot)

        loaded = await load_snapshot(redis, "TEST1234")
        assert loaded is not None
        assert loaded.campaign_level_id == 5
        assert loaded.campaign_user_id == 42
        assert loaded.initial_board_str == "rnbqkbnr/pppppppp"

    @pytest.mark.asyncio
    async def test_save_with_draw_offers(self, redis) -> None:
        """Draw offers set is preserved."""
        snapshot = _make_snapshot(draw_offers={1, 2})
        await save_snapshot(redis, snapshot)

        loaded = await load_snapshot(redis, "TEST1234")
        assert loaded is not None
        assert loaded.draw_offers == {1, 2}

    @pytest.mark.asyncio
    async def test_save_with_resigned_piece_ids(self, redis) -> None:
        """Resigned piece IDs are preserved."""
        snapshot = _make_snapshot(resigned_piece_ids=["k3", "k4"])
        await save_snapshot(redis, snapshot)

        loaded = await load_snapshot(redis, "TEST1234")
        assert loaded is not None
        assert loaded.resigned_piece_ids == ["k3", "k4"]


class TestLoadSnapshot:
    """Tests for load_snapshot."""

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, redis) -> None:
        """Loading a missing key returns None."""
        result = await load_snapshot(redis, "NOTEXIST")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_corrupted_json_returns_none(self, redis) -> None:
        """Invalid JSON returns None instead of raising."""
        await redis.set("game:BAD_JSON:snapshot", "not valid json", ex=7200)
        result = await load_snapshot(redis, "BAD_JSON")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_corrupted_data_returns_none(self, redis) -> None:
        """Valid JSON but invalid snapshot data returns None."""
        await redis.set("game:BAD_DATA:snapshot", '{"foo": "bar"}', ex=7200)
        result = await load_snapshot(redis, "BAD_DATA")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_preserves_state_dict(self, redis) -> None:
        """The state dict is preserved exactly."""
        snapshot = _make_snapshot()
        await save_snapshot(redis, snapshot)

        loaded = await load_snapshot(redis, "TEST1234")
        assert loaded is not None
        assert loaded.state["current_tick"] == 100
        assert loaded.state["status"] == "playing"


class TestDeleteSnapshot:
    """Tests for delete_snapshot."""

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, redis) -> None:
        """Deleting a snapshot removes it from Redis."""
        snapshot = _make_snapshot()
        await save_snapshot(redis, snapshot)

        await delete_snapshot(redis, "TEST1234")
        result = await load_snapshot(redis, "TEST1234")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_noop(self, redis) -> None:
        """Deleting a missing key doesn't raise."""
        await delete_snapshot(redis, "NOTEXIST")  # Should not raise


class TestListSnapshotGameIds:
    """Tests for list_snapshot_game_ids."""

    @pytest.mark.asyncio
    async def test_list_empty(self, redis) -> None:
        """Empty Redis returns empty list."""
        result = await list_snapshot_game_ids(redis)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, redis) -> None:
        """Multiple snapshots are listed."""
        for gid in ["GAME1111", "GAME2222", "GAME3333"]:
            await save_snapshot(redis, _make_snapshot(game_id=gid))

        result = await list_snapshot_game_ids(redis)
        assert sorted(result) == ["GAME1111", "GAME2222", "GAME3333"]

    @pytest.mark.asyncio
    async def test_list_ignores_non_snapshot_keys(self, redis) -> None:
        """Only game:*:snapshot keys are returned."""
        await save_snapshot(redis, _make_snapshot())
        await redis.set("game:TEST1234:server", "worker1")
        await redis.set("server:worker1:heartbeat", "123")

        result = await list_snapshot_game_ids(redis)
        assert result == ["TEST1234"]

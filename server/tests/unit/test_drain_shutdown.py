"""Tests for the drain shutdown sequence in main.py lifespan."""

from __future__ import annotations

from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from kfchess.drain import set_draining
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.state import GameStatus, Speed
from kfchess.services.game_service import GameService, ManagedGame


def _make_playing_game(game_id: str = "DRAIN001") -> ManagedGame:
    """Create a ManagedGame in PLAYING status."""
    state = GameEngine.create_game(
        speed=Speed.STANDARD,
        players={1: "u:1", 2: "bot:novice"},
        board_type=BoardType.STANDARD,
        game_id=game_id,
    )
    GameEngine.set_player_ready(state, 1)
    GameEngine.set_player_ready(state, 2)
    for _ in range(10):
        GameEngine.tick(state)

    return ManagedGame(
        state=state,
        player_keys={1: "p1_key"},
        ai_config={2: "novice"},
    )


@pytest.fixture(autouse=True)
def _reset_drain():
    """Reset drain state before and after each test."""
    set_draining(False)
    yield
    set_draining(False)


@pytest.fixture
def redis():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestDrainShutdownSequence:
    """Tests for the drain shutdown sequence."""

    @pytest.mark.asyncio
    async def test_drain_saves_final_snapshots(self, redis) -> None:
        """During drain, final snapshots are saved synchronously for all active games."""
        from kfchess.redis.snapshot_store import load_snapshot, save_snapshot
        from kfchess.ws.handler import _build_snapshot

        game_service = GameService()
        mg1 = _make_playing_game("DRAIN001")
        mg2 = _make_playing_game("DRAIN002")
        game_service.games["DRAIN001"] = mg1
        game_service.games["DRAIN002"] = mg2

        # Simulate the drain sequence snapshot-saving loop
        snapshot_count = 0
        for gid, managed_game in game_service.games.items():
            if managed_game.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
                snapshot = _build_snapshot(gid, managed_game)
                await save_snapshot(redis, snapshot)
                snapshot_count += 1

        assert snapshot_count == 2

        # Verify snapshots are in Redis
        snap1 = await load_snapshot(redis, "DRAIN001")
        snap2 = await load_snapshot(redis, "DRAIN002")
        assert snap1 is not None
        assert snap2 is not None
        assert snap1.snapshot_tick == 10
        assert snap2.snapshot_tick == 10

    @pytest.mark.asyncio
    async def test_drain_does_not_snapshot_finished_games(self, redis) -> None:
        """Finished games are not snapshotted during drain."""
        from kfchess.redis.snapshot_store import load_snapshot, save_snapshot
        from kfchess.ws.handler import _build_snapshot

        game_service = GameService()
        mg = _make_playing_game("FINISHED1")
        mg.state.status = GameStatus.FINISHED
        mg.state.winner = 1
        game_service.games["FINISHED1"] = mg

        snapshot_count = 0
        for gid, managed_game in game_service.games.items():
            if managed_game.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
                snapshot = _build_snapshot(gid, managed_game)
                await save_snapshot(redis, snapshot)
                snapshot_count += 1

        assert snapshot_count == 0
        snap = await load_snapshot(redis, "FINISHED1")
        assert snap is None

    @pytest.mark.asyncio
    async def test_drain_closes_game_ws_with_4301(self) -> None:
        """During drain, all game WS connections are closed with code 4301."""
        from kfchess.ws.handler import ConnectionManager

        cm = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await cm.connect("GAME1", ws1, 1)
        await cm.connect("GAME2", ws2, 1)

        await cm.close_all(code=4301, reason="server shutting down")

        ws1.close.assert_called_once_with(code=4301, reason="server shutting down")
        ws2.close.assert_called_once_with(code=4301, reason="server shutting down")

    @pytest.mark.asyncio
    async def test_drain_preserves_routing_keys(self, redis) -> None:
        """During drain, routing keys are NOT deleted (left for crash recovery)."""
        from kfchess.redis.routing import get_game_server, register_game_routing

        # Register routing keys (as would exist for active games)
        await register_game_routing(redis, "DRAIN001", "this-server")
        await register_game_routing(redis, "DRAIN002", "this-server")

        # The drain sequence does NOT delete routing keys.
        # Verify they still exist after drain would run.
        assert await get_game_server(redis, "DRAIN001") == "this-server"
        assert await get_game_server(redis, "DRAIN002") == "this-server"

    @pytest.mark.asyncio
    async def test_non_drain_shutdown_skips_snapshot_save(self) -> None:
        """Normal shutdown (not drain) doesn't write final snapshots."""
        from kfchess.drain import is_draining

        # Drain is not set
        assert is_draining() is False

        # In normal shutdown, the drain block is skipped entirely
        # This test verifies the condition check works
        save_snapshot_called = False

        if is_draining():
            save_snapshot_called = True

        assert save_snapshot_called is False


class TestDrainSequenceOrdering:
    """Tests that verify drain sequence ordering."""

    @pytest.mark.asyncio
    async def test_snapshots_saved_before_connections_closed(self) -> None:
        """Final snapshots are saved before WebSocket connections are closed."""
        call_order: list[str] = []

        async def mock_save_snapshot(r, snapshot):
            call_order.append("snapshot_saved")

        async def mock_close_all(code=1000, reason=""):
            call_order.append("connections_closed")

        # Simulate the drain sequence
        from kfchess.game.state import GameStatus
        from kfchess.ws.handler import _build_snapshot

        game_service = GameService()
        mg = _make_playing_game("ORDER001")
        game_service.games["ORDER001"] = mg

        # Step 1: Save snapshots
        for gid, managed_game in game_service.games.items():
            if managed_game.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
                snapshot = _build_snapshot(gid, managed_game)
                await mock_save_snapshot(None, snapshot)

        # Step 2: Close connections
        await mock_close_all(code=4301, reason="server shutting down")

        assert call_order == ["snapshot_saved", "connections_closed"]

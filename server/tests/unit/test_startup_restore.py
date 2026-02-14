"""Tests for the startup restoration pipeline.

Tests the end-to-end flow: snapshots in Redis → heartbeat check → restore_game.
"""

from __future__ import annotations

import time

import fakeredis.aioredis
import pytest

from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.snapshot import GameSnapshot
from kfchess.game.state import Speed
from kfchess.redis.heartbeat import is_server_alive, start_heartbeat, stop_heartbeat
from kfchess.redis.routing import (
    claim_game_routing,
    get_game_server,
    register_game_routing,
)
from kfchess.redis.snapshot_store import load_snapshot, save_snapshot
from kfchess.services.game_service import GameService


@pytest.fixture
def redis():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _make_snapshot(
    game_id: str,
    server_id: str = "old-server",
) -> GameSnapshot:
    """Create a test snapshot from a real game."""
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

    return GameSnapshot(
        game_id=game_id,
        state=state.to_snapshot_dict(),
        player_keys={1: "p1_key123"},
        ai_config={2: "novice"},
        server_id=server_id,
        snapshot_tick=state.current_tick,
        snapshot_time=time.time(),
    )


async def _run_restore_pipeline(
    redis: fakeredis.aioredis.FakeRedis,
    service: GameService,
) -> int:
    """Simulate the startup restoration pipeline from main.py."""
    from kfchess.redis.snapshot_store import list_snapshot_game_ids

    game_ids = await list_snapshot_game_ids(redis)
    restored = 0
    for gid in game_ids:
        snapshot = await load_snapshot(redis, gid)
        if snapshot is None:
            continue
        if snapshot.server_id and await is_server_alive(redis, snapshot.server_id):
            continue
        if service.restore_game(snapshot):
            restored += 1
    return restored


class TestStartupRestorePipeline:
    """Tests for the full startup restoration pipeline."""

    @pytest.mark.asyncio
    async def test_restores_orphaned_games(self, redis) -> None:
        """Games from a dead server are restored."""
        snapshot = _make_snapshot("ORPHAN01", server_id="dead-server")
        await save_snapshot(redis, snapshot)

        service = GameService()
        restored = await _run_restore_pipeline(redis, service)

        assert restored == 1
        assert service.get_game("ORPHAN01") is not None

    @pytest.mark.asyncio
    async def test_skips_games_from_live_server(self, redis) -> None:
        """Games from a server with active heartbeat are not claimed."""
        await start_heartbeat(redis, "live-server")
        import asyncio
        await asyncio.sleep(0.05)

        snapshot = _make_snapshot("LIVE0001", server_id="live-server")
        await save_snapshot(redis, snapshot)

        service = GameService()
        restored = await _run_restore_pipeline(redis, service)

        assert restored == 0
        assert service.get_game("LIVE0001") is None

        await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_restores_multiple_games(self, redis) -> None:
        """Multiple orphaned games are all restored."""
        for i in range(3):
            snapshot = _make_snapshot(f"MULTI{i:04d}", server_id="crashed")
            await save_snapshot(redis, snapshot)

        service = GameService()
        restored = await _run_restore_pipeline(redis, service)

        assert restored == 3
        for i in range(3):
            assert service.get_game(f"MULTI{i:04d}") is not None

    @pytest.mark.asyncio
    async def test_skips_expired_snapshots(self, redis) -> None:
        """Expired (deleted) snapshots don't cause errors."""
        # Save then delete — simulates TTL expiry
        snapshot = _make_snapshot("EXPIRED1")
        await save_snapshot(redis, snapshot)
        await redis.delete("game:EXPIRED1:snapshot")

        service = GameService()
        restored = await _run_restore_pipeline(redis, service)
        assert restored == 0

    @pytest.mark.asyncio
    async def test_skips_corrupted_snapshot(self, redis) -> None:
        """Corrupted JSON in Redis is handled gracefully."""
        await redis.set("game:BADDATA1:snapshot", "not valid json", ex=7200)

        service = GameService()
        # Should not raise — load_snapshot returns None or restore_game returns False
        try:
            restored = await _run_restore_pipeline(redis, service)
        except Exception:
            pytest.fail("Pipeline should not raise on corrupted data")
        assert restored == 0

    @pytest.mark.asyncio
    async def test_empty_server_id_treated_as_dead(self, redis) -> None:
        """Snapshot with empty server_id is claimed (no heartbeat to check)."""
        snapshot = _make_snapshot("NOOWNER1", server_id="")
        await save_snapshot(redis, snapshot)

        service = GameService()
        restored = await _run_restore_pipeline(redis, service)

        assert restored == 1

    @pytest.mark.asyncio
    async def test_mixed_live_and_dead_servers(self, redis) -> None:
        """Only games from dead servers are restored."""
        import asyncio

        await start_heartbeat(redis, "alive")
        await asyncio.sleep(0.05)

        await save_snapshot(redis, _make_snapshot("FROM_ALIVE", server_id="alive"))
        await save_snapshot(redis, _make_snapshot("FROM_DEAD1", server_id="dead"))
        await save_snapshot(redis, _make_snapshot("FROM_DEAD2", server_id="dead"))

        service = GameService()
        restored = await _run_restore_pipeline(redis, service)

        assert restored == 2
        assert service.get_game("FROM_ALIVE") is None
        assert service.get_game("FROM_DEAD1") is not None
        assert service.get_game("FROM_DEAD2") is not None

        await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_restored_game_is_functional(self, redis) -> None:
        """Restored game can continue ticking."""
        snapshot = _make_snapshot("FUNC0001")
        await save_snapshot(redis, snapshot)

        service = GameService()
        await _run_restore_pipeline(redis, service)

        state, events, finished, _, _ = service.tick("FUNC0001")
        assert state is not None
        assert state.current_tick == 11  # Was at 10


async def _run_cas_restore_pipeline(
    redis: fakeredis.aioredis.FakeRedis,
    service: GameService,
    my_server_id: str = "my-server",
) -> int:
    """Simulate the CAS-based startup restoration pipeline from main.py.

    Must mirror the logic in main.py lifespan startup.
    """
    from kfchess.redis.snapshot_store import list_snapshot_game_ids

    game_ids = await list_snapshot_game_ids(redis)
    restored = 0
    for gid in game_ids:
        snapshot = await load_snapshot(redis, gid)
        if snapshot is None:
            continue

        # Skip games owned by a different server that is still alive
        if snapshot.server_id and snapshot.server_id != my_server_id:
            if await is_server_alive(redis, snapshot.server_id):
                continue
            # Atomically claim the routing key from the dead server
            claimed = await claim_game_routing(
                redis, gid, snapshot.server_id, my_server_id
            )
            if not claimed:
                continue
        elif snapshot.server_id == my_server_id:
            # Same server restarting — refresh the routing key
            await register_game_routing(redis, gid, my_server_id)
        else:
            # No owner (empty server_id) — just register directly
            await register_game_routing(redis, gid, my_server_id)

        if service.restore_game(snapshot):
            restored += 1
    return restored


class TestStartupRestoreWithCAS:
    """Tests for CAS-based startup restoration pipeline (Phase 5)."""

    @pytest.mark.asyncio
    async def test_cas_claims_routing_key(self, redis) -> None:
        """CAS restore claims the routing key from the dead server."""
        snapshot = _make_snapshot("CAS00001", server_id="dead-server")
        await save_snapshot(redis, snapshot)
        await register_game_routing(redis, "CAS00001", "dead-server")

        service = GameService()
        restored = await _run_cas_restore_pipeline(redis, service, "my-server")

        assert restored == 1
        assert await get_game_server(redis, "CAS00001") == "my-server"

    @pytest.mark.asyncio
    async def test_cas_failure_skips_game(self, redis) -> None:
        """CAS failure (another server claimed) skips the game."""
        snapshot = _make_snapshot("CAS00002", server_id="dead-server")
        await save_snapshot(redis, snapshot)
        # Another server already claimed this game
        await register_game_routing(redis, "CAS00002", "other-server")

        service = GameService()
        restored = await _run_cas_restore_pipeline(redis, service, "my-server")

        assert restored == 0
        assert service.get_game("CAS00002") is None
        # Routing key still points to other-server
        assert await get_game_server(redis, "CAS00002") == "other-server"

    @pytest.mark.asyncio
    async def test_empty_server_id_uses_direct_register(self, redis) -> None:
        """Snapshot with empty server_id uses register_game_routing (no CAS needed)."""
        snapshot = _make_snapshot("CAS00003", server_id="")
        await save_snapshot(redis, snapshot)

        service = GameService()
        restored = await _run_cas_restore_pipeline(redis, service, "my-server")

        assert restored == 1
        assert await get_game_server(redis, "CAS00003") == "my-server"

    @pytest.mark.asyncio
    async def test_cas_concurrent_servers(self, redis) -> None:
        """Two servers racing to claim the same game — only one succeeds."""
        snapshot = _make_snapshot("CAS00004", server_id="dead-server")
        await save_snapshot(redis, snapshot)
        await register_game_routing(redis, "CAS00004", "dead-server")

        service_a = GameService()
        service_b = GameService()

        # Run both restore pipelines
        import asyncio
        restored_a, restored_b = await asyncio.gather(
            _run_cas_restore_pipeline(redis, service_a, "server-A"),
            _run_cas_restore_pipeline(redis, service_b, "server-B"),
        )

        # Exactly one should have restored the game
        assert restored_a + restored_b == 1

        # The routing key should point to the winner
        owner = await get_game_server(redis, "CAS00004")
        if restored_a == 1:
            assert owner == "server-A"
            assert service_a.get_game("CAS00004") is not None
        else:
            assert owner == "server-B"
            assert service_b.get_game("CAS00004") is not None

    @pytest.mark.asyncio
    async def test_same_server_id_restores_own_games(self, redis) -> None:
        """Server restarting with the same ID restores its own games.

        When KFCHESS_SERVER_ID is set to a stable value (e.g., 'worker1'),
        the restarted server must restore games from its previous run even
        though its own heartbeat is now alive.
        """
        server_id = "worker1"

        # Simulate previous run: snapshot and routing key from same server_id
        snapshot = _make_snapshot("OWNSNAP1", server_id=server_id)
        await save_snapshot(redis, snapshot)
        await register_game_routing(redis, "OWNSNAP1", server_id)

        # Start heartbeat (as main.py does before restore)
        await start_heartbeat(redis, server_id)
        import asyncio
        await asyncio.sleep(0.05)

        service = GameService()
        restored = await _run_cas_restore_pipeline(redis, service, server_id)

        assert restored == 1
        assert service.get_game("OWNSNAP1") is not None
        # Routing key still points to us
        assert await get_game_server(redis, "OWNSNAP1") == server_id

        await stop_heartbeat()

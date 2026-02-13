"""Integration tests for multi-server features (Phases 1-5).

Tests snapshot lifecycle, drain shutdown, crash recovery, startup restore,
and concurrent CAS routing using fakeredis with shared FakeServer for
realistic cross-client Redis behavior.

These tests do NOT require PostgreSQL or import the FastAPI app.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from fakeredis import FakeServer

from kfchess.campaign.levels import get_level
from kfchess.drain import set_draining
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.snapshot import GameSnapshot
from kfchess.game.state import GameStatus, Speed
from kfchess.redis.heartbeat import is_server_alive, start_heartbeat, stop_heartbeat
from kfchess.redis.routing import (
    claim_game_routing,
    get_game_server,
    register_game_routing,
)
from kfchess.redis.snapshot_store import (
    list_snapshot_game_ids,
    load_snapshot,
    save_snapshot,
)
from kfchess.services.game_service import GameService, ManagedGame
from kfchess.ws.handler import _build_snapshot, _check_routing_ownership

# ── Helpers ──────────────────────────────────────────────────────────


def _make_playing_game(
    game_id: str = "INT_0001",
    tick_count: int = 10,
) -> ManagedGame:
    """Create a ManagedGame in PLAYING status with real engine state."""
    state = GameEngine.create_game(
        speed=Speed.STANDARD,
        players={1: "u:1", 2: "bot:novice"},
        board_type=BoardType.STANDARD,
        game_id=game_id,
    )
    GameEngine.set_player_ready(state, 1)
    GameEngine.set_player_ready(state, 2)
    for _ in range(tick_count):
        GameEngine.tick(state)

    return ManagedGame(
        state=state,
        player_keys={1: "p1_testkey123"},
        ai_config={2: "novice"},
    )


def _make_snapshot_from_game(
    game_id: str,
    managed_game: ManagedGame,
    server_id: str = "server-A",
) -> GameSnapshot:
    """Build a GameSnapshot using the real _build_snapshot, controlling server_id."""
    with patch(
        "kfchess.ws.handler.get_settings",
        return_value=MagicMock(effective_server_id=server_id),
    ):
        return _build_snapshot(game_id, managed_game)


def _get_redis_factory(server: FakeServer):
    """Return an async function that creates FakeRedis from a shared server."""
    async def _get_redis():
        return fakeredis.aioredis.FakeRedis(
            server=server, decode_responses=True, version=(7,)
        )
    return _get_redis


async def _run_startup_restore(
    redis: fakeredis.aioredis.FakeRedis,
    service: GameService,
    my_server_id: str,
) -> int:
    """Replicate the CAS-based startup restore pipeline from main.py."""
    game_ids = await list_snapshot_game_ids(redis)
    restored = 0
    for gid in game_ids:
        snapshot = await load_snapshot(redis, gid)
        if snapshot is None:
            continue
        if snapshot.server_id and await is_server_alive(redis, snapshot.server_id):
            continue

        if snapshot.server_id:
            claimed = await claim_game_routing(
                redis, gid, snapshot.server_id, my_server_id
            )
            if not claimed:
                continue
        else:
            await register_game_routing(redis, gid, my_server_id)

        if service.restore_game(snapshot):
            restored += 1
    return restored


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def fake_redis_server():
    """Create a fresh FakeServer per test for shared Redis state."""
    return FakeServer()


@pytest.fixture
async def redis(fake_redis_server):
    """Get a FakeRedis client connected to the shared server."""
    return fakeredis.aioredis.FakeRedis(
        server=fake_redis_server, decode_responses=True, version=(7,)
    )


@pytest.fixture
def game_service():
    """Create a fresh GameService."""
    return GameService()


@pytest.fixture(autouse=True)
def _reset_drain():
    """Reset drain state before and after each test."""
    set_draining(False)
    yield
    set_draining(False)


@pytest.fixture(autouse=True)
async def _stop_heartbeat_cleanup():
    """Stop heartbeat after each test to prevent cross-test leaking."""
    yield
    await stop_heartbeat()


# ── Test Classes ─────────────────────────────────────────────────────


class TestSnapshotRoundTrip:
    """Full round-trip: engine → snapshot → Redis → restore → verify."""

    @pytest.mark.asyncio
    async def test_snapshot_round_trip_preserves_game_state(
        self, redis, game_service
    ) -> None:
        """Create game, snapshot to Redis, restore on fresh service, verify state."""
        mg = _make_playing_game("SNAP0001", tick_count=50)

        # Build and save snapshot
        snapshot = _make_snapshot_from_game("SNAP0001", mg, "server-A")
        await save_snapshot(redis, snapshot)

        # Load from Redis and restore
        loaded = await load_snapshot(redis, "SNAP0001")
        assert loaded is not None
        assert loaded.game_id == "SNAP0001"
        assert loaded.snapshot_tick == 50
        assert loaded.player_keys == {1: "p1_testkey123"}
        assert loaded.ai_config == {2: "novice"}
        assert loaded.server_id == "server-A"

        result = game_service.restore_game(loaded)
        assert result is True

        # Verify restored state matches original
        restored = game_service.get_game("SNAP0001")
        assert restored is not None
        assert restored.current_tick == 50
        assert restored.status == GameStatus.PLAYING
        assert restored.players == {1: "u:1", 2: "bot:novice"}

        # Pieces should be intact
        active_pieces = [p for p in restored.board.pieces if not p.captured]
        assert len(active_pieces) == 32

        # AI should be rebuilt
        managed = game_service.get_managed_game("SNAP0001")
        assert managed is not None
        assert 2 in managed.ai_players


class TestDrainShutdown:
    """Drain shutdown sequence: snapshots, heartbeat, routing."""

    @pytest.mark.asyncio
    async def test_drain_saves_final_snapshots_for_all_active_games(
        self, redis, game_service
    ) -> None:
        """Drain saves snapshots for all PLAYING games."""
        mg1 = _make_playing_game("DRAIN_01", tick_count=30)
        mg2 = _make_playing_game("DRAIN_02", tick_count=60)
        game_service.games["DRAIN_01"] = mg1
        game_service.games["DRAIN_02"] = mg2

        # Simulate drain snapshot loop (from main.py)
        snapshot_count = 0
        for gid, managed_game in game_service.games.items():
            if managed_game.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
                snapshot = _make_snapshot_from_game(gid, managed_game, "drain-server")
                await save_snapshot(redis, snapshot)
                snapshot_count += 1

        assert snapshot_count == 2

        snap1 = await load_snapshot(redis, "DRAIN_01")
        snap2 = await load_snapshot(redis, "DRAIN_02")
        assert snap1 is not None
        assert snap2 is not None
        assert snap1.snapshot_tick == 30
        assert snap2.snapshot_tick == 60

    @pytest.mark.asyncio
    async def test_drain_skips_finished_games(self, redis, game_service) -> None:
        """Finished games are not snapshotted during drain."""
        mg = _make_playing_game("FIN_0001")
        mg.state.status = GameStatus.FINISHED
        mg.state.winner = 1
        game_service.games["FIN_0001"] = mg

        snapshot_count = 0
        for gid, managed_game in game_service.games.items():
            if managed_game.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
                snapshot = _make_snapshot_from_game(gid, managed_game, "drain-server")
                await save_snapshot(redis, snapshot)
                snapshot_count += 1

        assert snapshot_count == 0
        assert await load_snapshot(redis, "FIN_0001") is None

    @pytest.mark.asyncio
    async def test_drain_stops_heartbeat_and_preserves_routing(
        self, redis
    ) -> None:
        """Drain stops heartbeat but routing keys persist for crash recovery."""
        await start_heartbeat(redis, "drain-svr")
        await asyncio.sleep(0.05)
        assert await is_server_alive(redis, "drain-svr") is True

        await register_game_routing(redis, "G_0001", "drain-svr")
        await register_game_routing(redis, "G_0002", "drain-svr")

        # Drain step: stop heartbeat
        await stop_heartbeat()
        await asyncio.sleep(0.05)

        # Heartbeat gone
        assert await is_server_alive(redis, "drain-svr") is False
        # Routing keys preserved (intentionally NOT deleted during drain)
        assert await get_game_server(redis, "G_0001") == "drain-svr"
        assert await get_game_server(redis, "G_0002") == "drain-svr"


class TestCrashRecovery:
    """On-demand crash recovery via handle_websocket()."""

    @pytest.mark.asyncio
    async def test_dead_server_game_restored_on_reconnect(
        self, fake_redis_server, game_service
    ) -> None:
        """Client reconnects to dead server's game — CAS claims and restores."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        mg = _make_playing_game("CRASH001", tick_count=40)
        snapshot = _make_snapshot_from_game("CRASH001", mg, "dead-server")
        await save_snapshot(redis, snapshot)
        await register_game_routing(redis, "CRASH001", "dead-server")
        # No heartbeat for dead-server → is_server_alive returns False

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_text = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=Exception("disconnect"))

        get_redis_fn = _get_redis_factory(fake_redis_server)

        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch("kfchess.ws.handler.get_game_service", return_value=game_service),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="new-server"),
            ),
            patch("kfchess.ws.handler.connection_manager") as mock_cm,
            patch(
                "kfchess.ws.handler.start_game_loop_if_needed",
                new_callable=AsyncMock,
            ),
            patch("kfchess.ws.handler.register_restored_game"),
        ):
            mock_cm.connect = AsyncMock()
            mock_cm.disconnect = AsyncMock()

            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "CRASH001", "p1_testkey123")

        # Game restored in service
        restored = game_service.get_game("CRASH001")
        assert restored is not None
        assert restored.current_tick == 40
        assert restored.status == GameStatus.PLAYING

        # Routing updated to new server
        redis2 = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )
        assert await get_game_server(redis2, "CRASH001") == "new-server"

        # WS was NOT closed with an error code (it proceeded to join flow)
        for call in mock_ws.close.call_args_list:
            code = call.kwargs.get("code") or call.args[0] if call.args else None
            assert code not in (4004, 4302), f"Unexpected close code: {code}"

    @pytest.mark.asyncio
    async def test_alive_server_game_redirects(
        self, fake_redis_server
    ) -> None:
        """Game on alive server sends 4302 redirect, no crash recovery."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        await register_game_routing(redis, "REDIR001", "alive-server")
        # Write heartbeat key directly (avoids occupying global _heartbeat_task)
        await redis.set(
            "server:alive-server:heartbeat", str(time.time()), ex=5
        )

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_text = AsyncMock()

        get_redis_fn = _get_redis_factory(fake_redis_server)

        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch(
                "kfchess.ws.handler.get_game_service",
                return_value=GameService(),
            ),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "REDIR001", None)

        mock_ws.close.assert_called_once_with(code=4302, reason="alive-server")


class TestStartupRestore:
    """CAS-based startup restore pipeline."""

    @pytest.mark.asyncio
    async def test_claims_orphaned_games(self, fake_redis_server) -> None:
        """Startup restore claims all orphaned games from dead server."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        for i in range(3):
            gid = f"ORPH{i:04d}"
            mg = _make_playing_game(gid, tick_count=20 + i * 10)
            snapshot = _make_snapshot_from_game(gid, mg, "dead-server")
            await save_snapshot(redis, snapshot)
            await register_game_routing(redis, gid, "dead-server")

        service = GameService()
        restored = await _run_startup_restore(redis, service, "new-server")

        assert restored == 3

        for i in range(3):
            gid = f"ORPH{i:04d}"
            assert service.get_game(gid) is not None
            assert service.get_game(gid).current_tick == 20 + i * 10
            assert await get_game_server(redis, gid) == "new-server"

    @pytest.mark.asyncio
    async def test_skips_live_server_games(self, fake_redis_server) -> None:
        """Games from alive server are not claimed during startup restore."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        mg = _make_playing_game("LIVE0001", tick_count=25)
        snapshot = _make_snapshot_from_game("LIVE0001", mg, "alive-server")
        await save_snapshot(redis, snapshot)
        await register_game_routing(redis, "LIVE0001", "alive-server")
        # Write heartbeat key directly
        await redis.set(
            "server:alive-server:heartbeat", str(time.time()), ex=5
        )

        service = GameService()
        restored = await _run_startup_restore(redis, service, "new-server")

        assert restored == 0
        assert service.get_game("LIVE0001") is None
        assert await get_game_server(redis, "LIVE0001") == "alive-server"


class TestConcurrentCAS:
    """Concurrent CAS claim race — exactly one server wins."""

    @pytest.mark.asyncio
    async def test_exactly_one_server_wins_race(
        self, fake_redis_server
    ) -> None:
        """Two servers racing to claim the same game — only one succeeds."""
        redis_setup = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )
        await register_game_routing(redis_setup, "RACE0001", "dead-server")

        # Two separate Redis clients from the same shared server
        r1 = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )
        r2 = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        result_a, result_b = await asyncio.gather(
            claim_game_routing(r1, "RACE0001", "dead-server", "server-A"),
            claim_game_routing(r2, "RACE0001", "dead-server", "server-B"),
        )

        # Exactly one should succeed
        assert (result_a is True) != (result_b is True)

        owner = await get_game_server(redis_setup, "RACE0001")
        if result_a:
            assert owner == "server-A"
        else:
            assert owner == "server-B"


class TestFullFailoverCycle:
    """Full failover: server A creates game, crashes, server B restores."""

    @pytest.mark.asyncio
    async def test_server_a_to_server_b_handoff(
        self, fake_redis_server
    ) -> None:
        """Complete failover cycle with state continuity."""
        # ── Phase 1: Server A creates and runs game ──
        service_a = GameService()
        mg = _make_playing_game("FAIL0001", tick_count=50)
        service_a.games["FAIL0001"] = mg

        redis_a = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        snapshot = _make_snapshot_from_game("FAIL0001", mg, "server-A")
        await save_snapshot(redis_a, snapshot)
        await register_game_routing(redis_a, "FAIL0001", "server-A")
        await start_heartbeat(redis_a, "server-A")
        await asyncio.sleep(0.05)

        assert await is_server_alive(redis_a, "server-A") is True
        assert await get_game_server(redis_a, "FAIL0001") == "server-A"

        # ── Phase 2: Server A "crashes" ──
        await stop_heartbeat()
        await asyncio.sleep(0.05)

        assert await is_server_alive(redis_a, "server-A") is False
        # Routing key still points to A (preserved for crash recovery)
        assert await get_game_server(redis_a, "FAIL0001") == "server-A"

        # ── Phase 3: Server B discovers and claims ──
        service_b = GameService()
        redis_b = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        loaded = await load_snapshot(redis_b, "FAIL0001")
        assert loaded is not None
        assert await is_server_alive(redis_b, "server-A") is False

        claimed = await claim_game_routing(
            redis_b, "FAIL0001", "server-A", "server-B"
        )
        assert claimed is True

        result = service_b.restore_game(loaded)
        assert result is True

        # ── Phase 4: Verify restored state and continue ──
        restored = service_b.get_game("FAIL0001")
        assert restored is not None
        assert restored.current_tick == 50
        assert restored.status == GameStatus.PLAYING
        assert restored.players == {1: "u:1", 2: "bot:novice"}

        assert await get_game_server(redis_b, "FAIL0001") == "server-B"

        # Continue ticking on server B
        for _ in range(10):
            service_b.tick("FAIL0001")

        assert service_b.get_game("FAIL0001").current_tick == 60
        assert service_b.get_game("FAIL0001").status == GameStatus.PLAYING


class TestCampaignGameRecovery:
    """Campaign game crash recovery preserves campaign-specific fields."""

    @pytest.mark.asyncio
    async def test_campaign_game_round_trip(self, redis, game_service) -> None:
        """Campaign game snapshot preserves level_id, user_id, initial_board_str."""
        level = get_level(0)
        assert level is not None

        game_id, player_key, player_num = game_service.create_campaign_game(
            level=level, user_id=42,
        )

        mg = game_service.get_managed_game(game_id)
        assert mg is not None
        assert mg.campaign_level_id == level.level_id
        assert mg.campaign_user_id == 42
        assert mg.initial_board_str == level.board_str

        # Tick a few times
        for _ in range(20):
            game_service.tick(game_id)

        # Build snapshot, save to Redis, restore on fresh service
        snapshot = _make_snapshot_from_game(game_id, mg, "server-A")
        await save_snapshot(redis, snapshot)

        loaded = await load_snapshot(redis, game_id)
        assert loaded is not None
        assert loaded.campaign_level_id == level.level_id
        assert loaded.campaign_user_id == 42
        assert loaded.initial_board_str == level.board_str

        service_b = GameService()
        assert service_b.restore_game(loaded) is True

        restored = service_b.get_managed_game(game_id)
        assert restored is not None
        assert restored.campaign_level_id == level.level_id
        assert restored.campaign_user_id == 42
        assert restored.initial_board_str == level.board_str
        assert restored.state.current_tick == 20

        # AI rebuilt for campaign
        for pnum in loaded.ai_config:
            assert pnum in restored.ai_players


class TestWaitingStatusDrain:
    """WAITING status games are snapshotted during drain."""

    @pytest.mark.asyncio
    async def test_drain_snapshots_waiting_game(self, redis) -> None:
        """A game in WAITING status is included in drain snapshots."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board_type=BoardType.STANDARD,
            game_id="WAIT0001",
        )
        # Only player 1 ready — game stays in WAITING
        GameEngine.set_player_ready(state, 1)
        assert state.status == GameStatus.WAITING

        mg = ManagedGame(
            state=state,
            player_keys={1: "p1_key", 2: "p2_key"},
            ai_config={},
        )

        service = GameService()
        service.games["WAIT0001"] = mg

        # Drain snapshot loop includes WAITING
        snapshot_count = 0
        for gid, managed_game in service.games.items():
            if managed_game.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
                snapshot = _make_snapshot_from_game(gid, managed_game, "drain-svr")
                await save_snapshot(redis, snapshot)
                snapshot_count += 1

        assert snapshot_count == 1

        loaded = await load_snapshot(redis, "WAIT0001")
        assert loaded is not None
        assert loaded.player_keys == {1: "p1_key", 2: "p2_key"}

        # Restore and verify WAITING status preserved
        service_b = GameService()
        assert service_b.restore_game(loaded) is True
        assert service_b.get_game("WAIT0001").status == GameStatus.WAITING


class TestRestoreFailureCleanup:
    """CAS claim + restore failure cleans up routing key."""

    @pytest.mark.asyncio
    async def test_restore_failure_deletes_routing_key(
        self, fake_redis_server
    ) -> None:
        """If CAS succeeds but restore fails, routing key is deleted."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        # Set up routing key for dead server but no snapshot
        await register_game_routing(redis, "BADRSTR1", "dead-server")

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_text = AsyncMock()

        get_redis_fn = _get_redis_factory(fake_redis_server)

        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch(
                "kfchess.ws.handler.get_game_service",
                return_value=GameService(),
            ),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "BADRSTR1", None)

        # Client gets 4004
        mock_ws.close.assert_called_once_with(code=4004, reason="Game not found")

        # Routing key should be DELETED (not orphaned pointing to my-server)
        assert await get_game_server(redis, "BADRSTR1") is None

    @pytest.mark.asyncio
    async def test_corrupted_snapshot_deletes_routing_key(
        self, fake_redis_server
    ) -> None:
        """If CAS succeeds but snapshot is corrupted, routing key is deleted."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )

        await register_game_routing(redis, "CORRUPT1", "dead-server")
        # Write corrupted snapshot data directly
        await redis.set("game:CORRUPT1:snapshot", "not valid json", ex=7200)

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_text = AsyncMock()

        get_redis_fn = _get_redis_factory(fake_redis_server)

        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch(
                "kfchess.ws.handler.get_game_service",
                return_value=GameService(),
            ),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "CORRUPT1", None)

        mock_ws.close.assert_called_once_with(code=4004, reason="Game not found")

        # Routing key should be deleted, not orphaned
        assert await get_game_server(redis, "CORRUPT1") is None


class TestSplitBrainProtection:
    """Routing ownership check detects when another server claimed our game."""

    @pytest.mark.asyncio
    async def test_ownership_check_passes_when_we_own_game(
        self, fake_redis_server
    ) -> None:
        """Ownership check returns True when routing key points to us."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )
        await register_game_routing(redis, "OWN_0001", "my-server")

        get_redis_fn = _get_redis_factory(fake_redis_server)
        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            assert await _check_routing_ownership("OWN_0001") is True

    @pytest.mark.asyncio
    async def test_ownership_check_fails_when_another_server_claimed(
        self, fake_redis_server
    ) -> None:
        """Ownership check returns False when another server CAS-claimed the game."""
        redis = fakeredis.aioredis.FakeRedis(
            server=fake_redis_server, decode_responses=True, version=(7,)
        )
        # Another server has claimed this game
        await register_game_routing(redis, "STOLEN01", "other-server")

        get_redis_fn = _get_redis_factory(fake_redis_server)
        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            assert await _check_routing_ownership("STOLEN01") is False

    @pytest.mark.asyncio
    async def test_ownership_check_passes_when_key_missing(
        self, fake_redis_server
    ) -> None:
        """Ownership check returns True when routing key is missing (don't kill loop)."""
        get_redis_fn = _get_redis_factory(fake_redis_server)
        with (
            patch("kfchess.ws.handler.get_redis", get_redis_fn),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            # No routing key exists at all — keep running
            assert await _check_routing_ownership("NOKEY001") is True

    @pytest.mark.asyncio
    async def test_ownership_check_passes_on_redis_failure(self) -> None:
        """Ownership check returns True when Redis is unreachable (don't kill loop)."""
        async def _broken_redis():
            raise ConnectionError("Redis down")

        with (
            patch("kfchess.ws.handler.get_redis", _broken_redis),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
        ):
            # Redis failure — keep running (don't compound transient failures)
            assert await _check_routing_ownership("FAIL0001") is True

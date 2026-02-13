"""Tests for on-demand crash recovery in handle_websocket()."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.snapshot import GameSnapshot
from kfchess.game.state import Speed
from kfchess.services.game_service import GameService


def _make_snapshot(
    game_id: str = "CRASH001",
    server_id: str = "dead-server",
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


@pytest.fixture
def redis():
    """Create a fakeredis async client with Lua support."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def game_service():
    """Create a fresh GameService."""
    return GameService()


@pytest.fixture
def mock_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock(side_effect=Exception("disconnect"))
    return ws


class TestCrashRecovery:
    """Tests for on-demand crash recovery when client reconnects."""

    @pytest.mark.asyncio
    async def test_dead_server_triggers_recovery(self, redis, game_service, mock_ws) -> None:
        """Game on dead server is recovered when client reconnects."""
        from kfchess.redis.routing import register_game_routing
        from kfchess.redis.snapshot_store import save_snapshot

        # Set up: game on dead server (no heartbeat)
        snapshot = _make_snapshot("CRASH001", "dead-server")
        await save_snapshot(redis, snapshot)
        await register_game_routing(redis, "CRASH001", "dead-server")

        # Handle websocket — should recover the game
        with (
            patch("kfchess.ws.handler.get_redis", return_value=redis),
            patch("kfchess.ws.handler.get_game_service", return_value=game_service),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
            patch("kfchess.ws.handler.connection_manager") as mock_cm,
            patch("kfchess.ws.handler.start_game_loop_if_needed", new_callable=AsyncMock),
            patch("kfchess.ws.handler.register_restored_game"),
        ):
            mock_cm.connect = AsyncMock()
            mock_cm.disconnect = AsyncMock()

            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "CRASH001", "p1_key123")

        # Game should now be in the game service
        assert game_service.get_game("CRASH001") is not None

        # Routing key should point to us
        from kfchess.redis.routing import get_game_server

        owner = await get_game_server(redis, "CRASH001")
        assert owner == "my-server"

    @pytest.mark.asyncio
    async def test_alive_server_triggers_redirect(self, redis, mock_ws) -> None:
        """Game on alive server sends 4302 redirect."""
        from kfchess.redis.heartbeat import start_heartbeat, stop_heartbeat
        from kfchess.redis.routing import register_game_routing

        await register_game_routing(redis, "REDIR001", "alive-server")
        await start_heartbeat(redis, "alive-server")
        import asyncio
        await asyncio.sleep(0.05)

        try:
            with (
                patch("kfchess.ws.handler.get_redis", return_value=redis),
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
        finally:
            await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_cas_race_lost_redirects_to_winner(self, redis, mock_ws) -> None:
        """When CAS race is lost, redirect to the winner."""
        from kfchess.redis.routing import register_game_routing

        # Set up: game on dead server, but another server claims it first
        await register_game_routing(redis, "RACE0001", "dead-server")

        # Simulate the CAS race: claim_game_routing returns False,
        # and get_game_server returns the winner
        with (
            patch("kfchess.ws.handler.get_redis", return_value=redis),
            patch(
                "kfchess.ws.handler.get_game_service",
                return_value=GameService(),
            ),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
            patch("kfchess.ws.handler.is_server_alive", return_value=False),
            patch("kfchess.ws.handler.claim_game_routing", return_value=False),
            patch("kfchess.ws.handler.get_game_server", side_effect=[
                "dead-server",  # First call in the routing check
                "winner-server",  # Second call after CAS fails
            ]),
        ):
            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "RACE0001", None)

        mock_ws.close.assert_called_once_with(code=4302, reason="winner-server")

    @pytest.mark.asyncio
    async def test_no_snapshot_after_cas_returns_4004(self, redis, mock_ws) -> None:
        """CAS succeeds but snapshot is gone — returns 4004."""
        from kfchess.redis.routing import register_game_routing

        # Set up: routing key exists but no snapshot
        await register_game_routing(redis, "NOSNA001", "dead-server")

        with (
            patch("kfchess.ws.handler.get_redis", return_value=redis),
            patch(
                "kfchess.ws.handler.get_game_service",
                return_value=GameService(),
            ),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="my-server"),
            ),
            patch("kfchess.ws.handler.is_server_alive", return_value=False),
            patch("kfchess.ws.handler.claim_game_routing", return_value=True),
            patch("kfchess.ws.handler.load_snapshot", return_value=None),
        ):
            from kfchess.ws.handler import handle_websocket

            await handle_websocket(mock_ws, "NOSNA001", None)

        mock_ws.close.assert_called_once_with(code=4004, reason="Game not found")

    @pytest.mark.asyncio
    async def test_no_routing_key_returns_4004(self, redis, mock_ws) -> None:
        """No routing key at all returns 4004."""
        with (
            patch("kfchess.ws.handler.get_redis", return_value=redis),
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

            await handle_websocket(mock_ws, "NOEXIST1", None)

        mock_ws.close.assert_called_once_with(code=4004, reason="Game not found")

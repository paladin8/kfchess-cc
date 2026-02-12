"""Tests for game loop snapshot helpers in ws/handler.py."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.state import Speed
from kfchess.services.game_service import ManagedGame
from kfchess.ws.handler import (
    SNAPSHOT_INTERVAL_TICKS,
    _build_snapshot,
    _delete_snapshot_and_routing,
    _save_snapshot_fire_and_forget,
)


class TestBuildSnapshot:
    """Tests for _build_snapshot helper."""

    def _make_managed_game(
        self,
        game_id: str = "SNAP1234",
        speed: Speed = Speed.STANDARD,
        board_type: BoardType = BoardType.STANDARD,
    ) -> ManagedGame:
        """Create a ManagedGame for testing."""
        players = {1: "u:1", 2: "bot:novice"}
        state = GameEngine.create_game(
            speed=speed, players=players, board_type=board_type, game_id=game_id
        )
        GameEngine.set_player_ready(state, 1)
        GameEngine.set_player_ready(state, 2)
        for _ in range(30):
            GameEngine.tick(state)

        return ManagedGame(
            state=state,
            player_keys={1: "p1_key123"},
            ai_config={2: "novice"},
        )

    def test_build_snapshot_basic(self) -> None:
        """Build snapshot captures core fields."""
        mg = self._make_managed_game()
        snapshot = _build_snapshot("SNAP1234", mg)

        assert snapshot.game_id == "SNAP1234"
        assert snapshot.snapshot_tick == 30
        assert snapshot.player_keys == {1: "p1_key123"}
        assert snapshot.state["game_id"] == "SNAP1234"
        assert snapshot.state["status"] == "playing"

    def test_build_snapshot_extracts_ai_config(self) -> None:
        """AI config is extracted from player IDs."""
        mg = self._make_managed_game()
        snapshot = _build_snapshot("SNAP1234", mg)

        assert snapshot.ai_config == {2: "novice"}

    def test_build_snapshot_no_ai_for_humans(self) -> None:
        """Human players are not in ai_config."""
        mg = self._make_managed_game()
        snapshot = _build_snapshot("SNAP1234", mg)

        assert 1 not in snapshot.ai_config

    def test_build_snapshot_campaign_fields(self) -> None:
        """Campaign fields are included."""
        mg = self._make_managed_game()
        mg.campaign_level_id = 3
        mg.campaign_user_id = 99
        mg.initial_board_str = "custom"

        snapshot = _build_snapshot("SNAP1234", mg)

        assert snapshot.campaign_level_id == 3
        assert snapshot.campaign_user_id == 99
        assert snapshot.initial_board_str == "custom"

    def test_build_snapshot_draw_offers(self) -> None:
        """Draw offers are captured."""
        mg = self._make_managed_game()
        mg.draw_offers = {1, 2}

        snapshot = _build_snapshot("SNAP1234", mg)
        assert snapshot.draw_offers == {1, 2}

    def test_build_snapshot_resigned_piece_ids(self) -> None:
        """Resigned piece IDs are captured."""
        mg = self._make_managed_game()
        mg.resigned_piece_ids = ["k3"]

        snapshot = _build_snapshot("SNAP1234", mg)
        assert snapshot.resigned_piece_ids == ["k3"]

    def test_build_snapshot_force_broadcast(self) -> None:
        """force_broadcast flag is captured."""
        mg = self._make_managed_game()
        mg.force_broadcast = True

        snapshot = _build_snapshot("SNAP1234", mg)
        assert snapshot.force_broadcast is True

    def test_build_snapshot_server_id(self) -> None:
        """Server ID is set from settings."""
        mg = self._make_managed_game()
        snapshot = _build_snapshot("SNAP1234", mg)

        # Should have a non-empty server ID
        assert snapshot.server_id != ""

    def test_build_snapshot_state_is_serialized(self) -> None:
        """State is a dict (serialized), not a GameState object."""
        mg = self._make_managed_game()
        snapshot = _build_snapshot("SNAP1234", mg)

        assert isinstance(snapshot.state, dict)
        assert "pieces" in snapshot.state
        assert "active_moves" in snapshot.state

    def test_build_snapshot_4player_ai_config(self) -> None:
        """4-player game extracts all AI configs."""
        players = {
            1: "u:1",
            2: "bot:novice",
            3: "bot:intermediate",
            4: "bot:advanced",
        }
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players=players,
            board_type=BoardType.FOUR_PLAYER,
            game_id="FOUR1234",
        )
        for p in players:
            GameEngine.set_player_ready(state, p)

        mg = ManagedGame(
            state=state,
            player_keys={1: "p1_key"},
            ai_config={2: "novice", 3: "intermediate", 4: "advanced"},
        )

        snapshot = _build_snapshot("FOUR1234", mg)
        assert snapshot.ai_config == {
            2: "novice",
            3: "intermediate",
            4: "advanced",
        }

    def test_build_snapshot_snapshot_time_is_recent(self) -> None:
        """snapshot_time is approximately current time."""
        mg = self._make_managed_game()
        before = time.time()
        snapshot = _build_snapshot("SNAP1234", mg)
        after = time.time()

        assert before <= snapshot.snapshot_time <= after

    def test_build_snapshot_reads_ai_config_from_managed_game(self) -> None:
        """ai_config comes from ManagedGame.ai_config, not player ID strings."""
        players = {1: "u:1", 2: "bot:novice"}
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players=players,
            board_type=BoardType.STANDARD,
            game_id="AICONF01",
        )
        GameEngine.set_player_ready(state, 1)
        GameEngine.set_player_ready(state, 2)

        # ai_config on ManagedGame differs from what you'd parse from player IDs
        mg = ManagedGame(
            state=state,
            player_keys={1: "p1_key"},
            ai_config={2: "intermediate"},  # Not "novice" like in player ID
        )

        snapshot = _build_snapshot("AICONF01", mg)
        # Should use ManagedGame.ai_config, not derived from "bot:novice"
        assert snapshot.ai_config == {2: "intermediate"}


class TestSnapshotInterval:
    """Tests for snapshot interval constant."""

    def test_snapshot_interval_is_30_ticks(self) -> None:
        """Snapshot interval is 30 ticks (once per second at 30 Hz)."""
        assert SNAPSHOT_INTERVAL_TICKS == 30

    def test_tick_0_triggers_snapshot(self) -> None:
        """Tick 0 triggers a snapshot (0 % 30 == 0)."""
        assert 0 % SNAPSHOT_INTERVAL_TICKS == 0

    def test_tick_29_does_not_trigger(self) -> None:
        """Tick 29 does not trigger a snapshot."""
        assert 29 % SNAPSHOT_INTERVAL_TICKS != 0

    def test_tick_30_triggers_snapshot(self) -> None:
        """Tick 30 triggers a snapshot."""
        assert 30 % SNAPSHOT_INTERVAL_TICKS == 0


class TestFireAndForget:
    """Tests for fire-and-forget snapshot operations."""

    @pytest.mark.asyncio
    async def test_save_snapshot_fire_and_forget_calls_redis(self) -> None:
        """Fire-and-forget save writes to Redis."""
        mock_redis = AsyncMock()
        snapshot = _build_snapshot(
            "FF_SAVE1",
            ManagedGame(
                state=GameEngine.create_game(
                    speed=Speed.STANDARD,
                    players={1: "u:1", 2: "bot:novice"},
                    board_type=BoardType.STANDARD,
                    game_id="FF_SAVE1",
                ),
                player_keys={1: "p1_key"},
                ai_config={2: "novice"},
            ),
        )

        with patch("kfchess.ws.handler.get_redis", return_value=mock_redis):
            _save_snapshot_fire_and_forget(snapshot)
            # Let the fire-and-forget task run
            await asyncio.sleep(0.05)

        # Snapshot save + routing key refresh = 2 SET calls
        assert mock_redis.set.call_count == 2
        # First call is the snapshot, second is the routing key
        snapshot_call = mock_redis.set.call_args_list[0]
        assert "game:FF_SAVE1:snapshot" in str(snapshot_call)
        routing_call = mock_redis.set.call_args_list[1]
        assert "game:FF_SAVE1:server" in str(routing_call)

    @pytest.mark.asyncio
    async def test_save_snapshot_error_does_not_propagate(self) -> None:
        """Redis error in fire-and-forget save doesn't crash."""
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = ConnectionError("Redis down")

        snapshot = _build_snapshot(
            "FF_ERR01",
            ManagedGame(
                state=GameEngine.create_game(
                    speed=Speed.STANDARD,
                    players={1: "u:1", 2: "bot:novice"},
                    board_type=BoardType.STANDARD,
                    game_id="FF_ERR01",
                ),
                player_keys={1: "p1_key"},
                ai_config={2: "novice"},
            ),
        )

        with patch("kfchess.ws.handler.get_redis", return_value=mock_redis):
            _save_snapshot_fire_and_forget(snapshot)
            await asyncio.sleep(0.05)
            # Should not raise — error is logged and swallowed

    @pytest.mark.asyncio
    async def test_delete_snapshot_and_routing_calls_redis(self) -> None:
        """Delete calls Redis for both snapshot and routing key."""
        mock_redis = AsyncMock()

        with patch("kfchess.ws.handler.get_redis", return_value=mock_redis):
            await _delete_snapshot_and_routing("DEL_TEST")

        # Snapshot delete + routing key delete = 2 DELETE calls
        assert mock_redis.delete.call_count == 2
        delete_calls = [str(c) for c in mock_redis.delete.call_args_list]
        assert any("game:DEL_TEST:snapshot" in c for c in delete_calls)
        assert any("game:DEL_TEST:server" in c for c in delete_calls)

    @pytest.mark.asyncio
    async def test_delete_snapshot_error_does_not_propagate(self) -> None:
        """Redis error in delete doesn't crash."""
        mock_redis = AsyncMock()
        mock_redis.delete.side_effect = ConnectionError("Redis down")

        with patch("kfchess.ws.handler.get_redis", return_value=mock_redis):
            await _delete_snapshot_and_routing("DEL_ERR1")
            # Should not raise

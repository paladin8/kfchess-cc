"""Tests for game restoration from snapshots."""

from __future__ import annotations

import time

from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.snapshot import GameSnapshot
from kfchess.game.state import GameStatus, Speed, WinReason
from kfchess.services.game_service import GameService


def _create_test_snapshot(
    game_id: str = "RESTORE1",
    speed: Speed = Speed.STANDARD,
    board_type: BoardType = BoardType.STANDARD,
    with_ai: bool = True,
    campaign: bool = False,
) -> GameSnapshot:
    """Create a snapshot from an actual game for testing restore."""
    players = {1: "u:1", 2: "bot:novice"}
    state = GameEngine.create_game(
        speed=speed,
        players=players,
        board_type=board_type,
        game_id=game_id,
    )
    # Advance the game: mark players ready
    GameEngine.set_player_ready(state, 1)
    GameEngine.set_player_ready(state, 2)

    if campaign:
        state.is_campaign = True

    # Run a few ticks
    for _ in range(10):
        GameEngine.tick(state)

    ai_config = {2: "novice"} if with_ai else {}

    return GameSnapshot(
        game_id=game_id,
        state=state.to_snapshot_dict(),
        player_keys={1: "p1_testkey123"},
        ai_config=ai_config,
        campaign_level_id=5 if campaign else None,
        campaign_user_id=42 if campaign else None,
        initial_board_str="custom_board" if campaign else None,
        server_id="worker1",
        snapshot_tick=state.current_tick,
        snapshot_time=time.time(),
    )


class TestRestoreGame:
    """Tests for GameService.restore_game."""

    def test_restore_basic_game(self) -> None:
        """Basic game restoration works."""
        service = GameService()
        snapshot = _create_test_snapshot()

        result = service.restore_game(snapshot)
        assert result is True

        # Verify game is in service
        state = service.get_game("RESTORE1")
        assert state is not None
        assert state.game_id == "RESTORE1"
        assert state.status == GameStatus.PLAYING
        assert state.current_tick == 10

    def test_restore_preserves_player_keys(self) -> None:
        """Player keys are restored."""
        service = GameService()
        snapshot = _create_test_snapshot()

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.player_keys == {1: "p1_testkey123"}

    def test_restore_preserves_ai_config(self) -> None:
        """AI config dict is restored on ManagedGame."""
        service = GameService()
        snapshot = _create_test_snapshot(with_ai=True)

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.ai_config == {2: "novice"}

    def test_restore_creates_ai_instances(self) -> None:
        """AI instances are recreated from ai_config."""
        service = GameService()
        snapshot = _create_test_snapshot(with_ai=True)

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert 2 in managed.ai_players
        # AI player should be functional
        ai = managed.ai_players[2]
        assert ai is not None

    def test_restore_without_ai(self) -> None:
        """Human-only game has no AI instances."""
        service = GameService()
        snapshot = _create_test_snapshot(with_ai=False)

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert len(managed.ai_players) == 0

    def test_restore_campaign_fields(self) -> None:
        """Campaign metadata is restored."""
        service = GameService()
        snapshot = _create_test_snapshot(campaign=True)

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.campaign_level_id == 5
        assert managed.campaign_user_id == 42
        assert managed.initial_board_str == "custom_board"

    def test_restore_campaign_is_campaign_flag(self) -> None:
        """is_campaign flag on GameState survives snapshot restore."""
        service = GameService()
        snapshot = _create_test_snapshot(campaign=True)

        service.restore_game(snapshot)

        state = service.get_game("RESTORE1")
        assert state is not None
        assert state.is_campaign is True

    def test_restore_non_campaign_is_campaign_false(self) -> None:
        """Non-campaign games have is_campaign=False after restore."""
        service = GameService()
        snapshot = _create_test_snapshot(campaign=False)

        service.restore_game(snapshot)

        state = service.get_game("RESTORE1")
        assert state is not None
        assert state.is_campaign is False

    def test_restore_draw_offers(self) -> None:
        """Draw offers are restored."""
        service = GameService()
        snapshot = _create_test_snapshot()
        snapshot.draw_offers = {1}

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.draw_offers == {1}

    def test_restore_resigned_piece_ids(self) -> None:
        """Resigned piece IDs are restored."""
        service = GameService()
        snapshot = _create_test_snapshot()
        snapshot.resigned_piece_ids = ["k3"]

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.resigned_piece_ids == ["k3"]

    def test_restore_force_broadcast(self) -> None:
        """force_broadcast flag is restored."""
        service = GameService()
        snapshot = _create_test_snapshot()
        snapshot.force_broadcast = True

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.force_broadcast is True

    def test_restore_duplicate_game_returns_false(self) -> None:
        """Cannot restore a game that already exists."""
        service = GameService()
        snapshot = _create_test_snapshot()

        assert service.restore_game(snapshot) is True
        assert service.restore_game(snapshot) is False

    def test_restore_preserves_board_state(self) -> None:
        """Board pieces are fully preserved."""
        service = GameService()
        snapshot = _create_test_snapshot()

        service.restore_game(snapshot)

        state = service.get_game("RESTORE1")
        assert state is not None
        # Should have all standard chess pieces
        assert len(state.board.pieces) == 32

    def test_restore_speed_config(self) -> None:
        """Game speed is restored correctly."""
        service = GameService()
        snapshot = _create_test_snapshot(speed=Speed.LIGHTNING)

        service.restore_game(snapshot)

        state = service.get_game("RESTORE1")
        assert state is not None
        assert state.speed == Speed.LIGHTNING

    def test_restore_no_loop_task(self) -> None:
        """Restored game has no loop_task (starts when player reconnects)."""
        service = GameService()
        snapshot = _create_test_snapshot()

        service.restore_game(snapshot)

        managed = service.get_managed_game("RESTORE1")
        assert managed is not None
        assert managed.loop_task is None

    def test_restore_validate_player_key(self) -> None:
        """Player keys work for authentication after restore."""
        service = GameService()
        snapshot = _create_test_snapshot()

        service.restore_game(snapshot)

        player_num = service.validate_player_key("RESTORE1", "p1_testkey123")
        assert player_num == 1

        bad = service.validate_player_key("RESTORE1", "wrong_key")
        assert bad is None

    def test_restore_game_can_continue_ticking(self) -> None:
        """Restored game can continue ticking without errors."""
        service = GameService()
        snapshot = _create_test_snapshot()

        service.restore_game(snapshot)

        # Tick the restored game
        state, events, finished, _, _ = service.tick("RESTORE1")
        assert state is not None
        assert state.current_tick == 11  # Was at 10, now 11

    def test_restore_4player_game(self) -> None:
        """4-player game with multiple AIs restores correctly."""
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

        snapshot = GameSnapshot(
            game_id="FOUR1234",
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_key"},
            ai_config={2: "novice", 3: "intermediate", 4: "advanced"},
            server_id="worker1",
            snapshot_tick=0,
            snapshot_time=time.time(),
        )

        service = GameService()
        assert service.restore_game(snapshot) is True

        managed = service.get_managed_game("FOUR1234")
        assert managed is not None
        assert len(managed.ai_players) == 3
        assert 2 in managed.ai_players
        assert 3 in managed.ai_players
        assert 4 in managed.ai_players

    def test_restore_skips_finished_game(self) -> None:
        """Finished games are not restored (stale snapshot)."""
        players = {1: "u:1", 2: "bot:novice"}
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players=players,
            board_type=BoardType.STANDARD,
            game_id="FINISH01",
        )
        GameEngine.set_player_ready(state, 1)
        GameEngine.set_player_ready(state, 2)
        # Manually mark as finished
        state.status = GameStatus.FINISHED
        state.winner = 1
        state.win_reason = WinReason.KING_CAPTURED

        snapshot = GameSnapshot(
            game_id="FINISH01",
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_key"},
            ai_config={2: "novice"},
            server_id="worker1",
            snapshot_tick=100,
            snapshot_time=time.time(),
        )

        service = GameService()
        assert service.restore_game(snapshot) is False
        assert service.get_game("FINISH01") is None

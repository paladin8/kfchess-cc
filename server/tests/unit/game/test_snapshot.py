"""Tests for game state snapshot serialization (Phase 1 of multi-server).

Tests round-trip serialization for all game data classes:
- Piece, Move, Cooldown, ReplayMove (individual types)
- GameState (to_snapshot_dict / from_snapshot_dict)
- GameSnapshot (wrapper with metadata)
- JSON round-trip (serialize to JSON string and back)
"""

import json
from datetime import datetime

from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.moves import Cooldown, Move
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.snapshot import GameSnapshot
from kfchess.game.state import (
    GameState,
    GameStatus,
    ReplayMove,
    Speed,
    WinReason,
)

# ---------------------------------------------------------------------------
# Piece serialization
# ---------------------------------------------------------------------------


class TestPieceSerialization:
    def test_basic_piece_round_trip(self):
        piece = Piece.create(PieceType.PAWN, player=1, row=6, col=3)
        data = piece.to_dict()
        restored = Piece.from_dict(data)

        assert restored.id == piece.id
        assert restored.type == piece.type
        assert restored.player == piece.player
        assert restored.row == piece.row
        assert restored.col == piece.col
        assert restored.captured == piece.captured
        assert restored.moved == piece.moved
        assert restored.cooldown_end_tick == piece.cooldown_end_tick

    def test_captured_moved_piece(self):
        piece = Piece.create(PieceType.QUEEN, player=2, row=0, col=3)
        piece.captured = True
        piece.moved = True
        piece.cooldown_end_tick = 150

        data = piece.to_dict()
        restored = Piece.from_dict(data)

        assert restored.captured is True
        assert restored.moved is True
        assert restored.cooldown_end_tick == 150

    def test_piece_with_float_position(self):
        """Piece mid-movement has float row/col."""
        piece = Piece.create(PieceType.KNIGHT, player=1, row=7, col=1)
        piece.row = 5.5
        piece.col = 2.5

        data = piece.to_dict()
        restored = Piece.from_dict(data)

        assert restored.row == 5.5
        assert restored.col == 2.5

    def test_all_piece_types(self):
        for piece_type in PieceType:
            piece = Piece.create(piece_type, player=1, row=0, col=0)
            data = piece.to_dict()
            restored = Piece.from_dict(data)
            assert restored.type == piece_type

    def test_piece_dict_keys(self):
        piece = Piece.create(PieceType.ROOK, player=1, row=7, col=0)
        data = piece.to_dict()
        expected_keys = {"id", "type", "player", "row", "col", "captured", "moved", "cooldown_end_tick"}
        assert set(data.keys()) == expected_keys

    def test_piece_json_round_trip(self):
        piece = Piece.create(PieceType.BISHOP, player=2, row=0, col=5)
        json_str = json.dumps(piece.to_dict())
        restored = Piece.from_dict(json.loads(json_str))
        assert restored.id == piece.id
        assert restored.type == piece.type


# ---------------------------------------------------------------------------
# Move serialization
# ---------------------------------------------------------------------------


class TestMoveSerialization:
    def test_basic_move_round_trip(self):
        move = Move(
            piece_id="R:1:7:0",
            path=[(7.0, 0.0), (6.0, 0.0), (5.0, 0.0)],
            start_tick=10,
        )
        data = move.to_dict()
        restored = Move.from_dict(data)

        assert restored.piece_id == move.piece_id
        assert restored.path == move.path
        assert restored.start_tick == move.start_tick
        assert restored.extra_move is None

    def test_move_with_extra_move(self):
        """Castling: king move has an extra_move for the rook."""
        rook_move = Move(
            piece_id="R:1:7:7",
            path=[(7.0, 7.0), (7.0, 6.0), (7.0, 5.0)],
            start_tick=50,
        )
        king_move = Move(
            piece_id="K:1:7:4",
            path=[(7.0, 4.0), (7.0, 5.0), (7.0, 6.0)],
            start_tick=50,
            extra_move=rook_move,
        )

        data = king_move.to_dict()
        restored = Move.from_dict(data)

        assert restored.extra_move is not None
        assert restored.extra_move.piece_id == "R:1:7:7"
        assert restored.extra_move.path == rook_move.path
        assert restored.extra_move.start_tick == 50

    def test_knight_move_with_float_midpoint(self):
        """Knight paths have float midpoints."""
        move = Move(
            piece_id="N:1:7:1",
            path=[(7.0, 1.0), (6.0, 2.0), (5.0, 3.0)],
            start_tick=20,
        )
        data = move.to_dict()
        restored = Move.from_dict(data)

        assert restored.path == [(7.0, 1.0), (6.0, 2.0), (5.0, 3.0)]

    def test_move_path_serialized_as_lists(self):
        """Path tuples become lists in JSON; from_dict converts back."""
        move = Move(piece_id="P:1:6:0", path=[(6.0, 0.0), (5.0, 0.0)], start_tick=5)
        data = move.to_dict()
        # Path should be lists (JSON-compatible)
        assert isinstance(data["path"][0], list)

        # JSON round-trip
        json_str = json.dumps(data)
        restored = Move.from_dict(json.loads(json_str))
        # Should be tuples again
        assert isinstance(restored.path[0], tuple)
        assert restored.path == move.path

    def test_move_dict_keys(self):
        move = Move(piece_id="P:1:6:0", path=[(6.0, 0.0), (5.0, 0.0)], start_tick=5)
        data = move.to_dict()
        expected_keys = {"piece_id", "path", "start_tick", "extra_move"}
        assert set(data.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Cooldown serialization
# ---------------------------------------------------------------------------


class TestCooldownSerialization:
    def test_cooldown_round_trip(self):
        cd = Cooldown(piece_id="R:1:7:0", start_tick=100, duration=300)
        data = cd.to_dict()
        restored = Cooldown.from_dict(data)

        assert restored.piece_id == cd.piece_id
        assert restored.start_tick == cd.start_tick
        assert restored.duration == cd.duration

    def test_cooldown_is_active_preserved(self):
        cd = Cooldown(piece_id="Q:2:0:3", start_tick=50, duration=100)
        restored = Cooldown.from_dict(cd.to_dict())

        assert restored.is_active(100) is True
        assert restored.is_active(150) is False

    def test_cooldown_dict_keys(self):
        cd = Cooldown(piece_id="P:1:6:0", start_tick=10, duration=300)
        data = cd.to_dict()
        assert set(data.keys()) == {"piece_id", "start_tick", "duration"}


# ---------------------------------------------------------------------------
# ReplayMove serialization
# ---------------------------------------------------------------------------


class TestReplayMoveSerialization:
    def test_replay_move_round_trip(self):
        rm = ReplayMove(tick=42, piece_id="P:1:6:4", to_row=4, to_col=4, player=1)
        data = rm.to_dict()
        restored = ReplayMove.from_dict(data)

        assert restored.tick == rm.tick
        assert restored.piece_id == rm.piece_id
        assert restored.to_row == rm.to_row
        assert restored.to_col == rm.to_col
        assert restored.player == rm.player

    def test_replay_move_dict_keys(self):
        rm = ReplayMove(tick=0, piece_id="K:1:7:4", to_row=6, to_col=4, player=1)
        data = rm.to_dict()
        assert set(data.keys()) == {"tick", "piece_id", "to_row", "to_col", "player"}


# ---------------------------------------------------------------------------
# GameState snapshot serialization
# ---------------------------------------------------------------------------


class TestGameStateSnapshotSerialization:
    def _create_initial_game(self) -> GameState:
        """Create a standard initial game state."""
        return GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:100", 2: "bot:novice"},
            board_type=BoardType.STANDARD,
            game_id="TEST1234",
        )

    def _create_mid_game_state(self) -> GameState:
        """Create a game state with active moves, cooldowns, and replay moves."""
        state = self._create_initial_game()
        state.status = GameStatus.PLAYING
        state.current_tick = 150
        state.started_at = datetime(2025, 6, 15, 12, 0, 0)
        state.ready_players = {1, 2}
        state.last_move_tick = 140
        state.last_capture_tick = 100

        # Add an active move
        state.active_moves.append(
            Move(piece_id="P:1:6:4", path=[(6.0, 4.0), (4.0, 4.0)], start_tick=145)
        )

        # Add a cooldown
        state.cooldowns.append(
            Cooldown(piece_id="N:1:7:1", start_tick=120, duration=300)
        )

        # Add some replay moves
        state.replay_moves.append(
            ReplayMove(tick=10, piece_id="P:1:6:4", to_row=4, to_col=4, player=1)
        )
        state.replay_moves.append(
            ReplayMove(tick=15, piece_id="P:2:1:3", to_row=3, to_col=3, player=2)
        )

        return state

    def _create_finished_game_state(self) -> GameState:
        """Create a finished game state."""
        state = self._create_mid_game_state()
        state.status = GameStatus.FINISHED
        state.winner = 1
        state.win_reason = WinReason.KING_CAPTURED
        state.finished_at = datetime(2025, 6, 15, 12, 15, 0)
        state.active_moves.clear()
        state.cooldowns.clear()
        return state

    def test_initial_game_round_trip(self):
        state = self._create_initial_game()
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert restored.game_id == state.game_id
        assert restored.speed == state.speed
        assert restored.board.board_type == state.board.board_type
        assert restored.board.width == state.board.width
        assert restored.board.height == state.board.height
        assert len(restored.board.pieces) == len(state.board.pieces)
        assert restored.status == state.status
        assert restored.current_tick == 0
        assert restored.winner is None
        assert restored.win_reason is None

    def test_mid_game_round_trip(self):
        state = self._create_mid_game_state()
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert restored.game_id == "TEST1234"
        assert restored.status == GameStatus.PLAYING
        assert restored.current_tick == 150
        assert restored.started_at == datetime(2025, 6, 15, 12, 0, 0)
        assert restored.ready_players == {1, 2}
        assert restored.last_move_tick == 140
        assert restored.last_capture_tick == 100

        # Active moves
        assert len(restored.active_moves) == 1
        assert restored.active_moves[0].piece_id == "P:1:6:4"
        assert restored.active_moves[0].start_tick == 145

        # Cooldowns
        assert len(restored.cooldowns) == 1
        assert restored.cooldowns[0].piece_id == "N:1:7:1"
        assert restored.cooldowns[0].duration == 300

        # Replay moves
        assert len(restored.replay_moves) == 2
        assert restored.replay_moves[0].tick == 10
        assert restored.replay_moves[1].player == 2

    def test_finished_game_round_trip(self):
        state = self._create_finished_game_state()
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert restored.status == GameStatus.FINISHED
        assert restored.winner == 1
        assert restored.win_reason == WinReason.KING_CAPTURED
        assert restored.finished_at == datetime(2025, 6, 15, 12, 15, 0)
        assert len(restored.active_moves) == 0
        assert len(restored.cooldowns) == 0

    def test_players_dict_preserved(self):
        state = self._create_initial_game()
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert restored.players == {1: "u:100", 2: "bot:novice"}

    def test_players_dict_keys_are_ints_after_json(self):
        """JSON converts int keys to strings; from_snapshot_dict must handle this."""
        state = self._create_initial_game()
        json_str = json.dumps(state.to_snapshot_dict())
        data = json.loads(json_str)
        # After JSON, player keys are strings
        assert "1" in data["players"]

        restored = GameState.from_snapshot_dict(data)
        # Must be ints again
        assert 1 in restored.players
        assert 2 in restored.players

    def test_pieces_fully_preserved(self):
        state = self._create_initial_game()
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        for orig, rest in zip(state.board.pieces, restored.board.pieces, strict=True):
            assert rest.id == orig.id
            assert rest.type == orig.type
            assert rest.player == orig.player
            assert rest.row == orig.row
            assert rest.col == orig.col
            assert rest.captured == orig.captured
            assert rest.moved == orig.moved

    def test_castling_move_with_extra_move(self):
        """Verify that castling (king+rook) move serialization works."""
        state = self._create_mid_game_state()
        rook_move = Move(
            piece_id="R:1:7:7",
            path=[(7.0, 7.0), (7.0, 6.0), (7.0, 5.0)],
            start_tick=150,
        )
        king_move = Move(
            piece_id="K:1:7:4",
            path=[(7.0, 4.0), (7.0, 5.0), (7.0, 6.0)],
            start_tick=150,
            extra_move=rook_move,
        )
        state.active_moves = [king_move]

        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert len(restored.active_moves) == 1
        king = restored.active_moves[0]
        assert king.piece_id == "K:1:7:4"
        assert king.extra_move is not None
        assert king.extra_move.piece_id == "R:1:7:7"

    def test_draw_win_reason(self):
        state = self._create_initial_game()
        state.status = GameStatus.FINISHED
        state.winner = 0
        state.win_reason = WinReason.DRAW

        restored = GameState.from_snapshot_dict(state.to_snapshot_dict())
        assert restored.winner == 0
        assert restored.win_reason == WinReason.DRAW

    def test_resignation_win_reason(self):
        state = self._create_initial_game()
        state.status = GameStatus.FINISHED
        state.winner = 2
        state.win_reason = WinReason.RESIGNATION

        restored = GameState.from_snapshot_dict(state.to_snapshot_dict())
        assert restored.win_reason == WinReason.RESIGNATION

    def test_invalid_win_reason(self):
        state = self._create_initial_game()
        state.status = GameStatus.FINISHED
        state.winner = 0
        state.win_reason = WinReason.INVALID

        restored = GameState.from_snapshot_dict(state.to_snapshot_dict())
        assert restored.win_reason == WinReason.INVALID
        assert restored.win_reason.is_rated() is False

    def test_multiple_simultaneous_active_moves(self):
        """Typical mid-game: several pieces moving at once."""
        state = self._create_initial_game()
        state.status = GameStatus.PLAYING
        state.current_tick = 200

        state.active_moves = [
            Move(piece_id="P:1:6:4", path=[(6.0, 4.0), (5.0, 4.0)], start_tick=195),
            Move(piece_id="N:1:7:1", path=[(7.0, 1.0), (6.0, 2.0), (5.0, 3.0)], start_tick=198),
            Move(piece_id="R:2:0:0", path=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)], start_tick=190),
            Move(
                piece_id="K:1:7:4",
                path=[(7.0, 4.0), (7.0, 5.0), (7.0, 6.0)],
                start_tick=200,
                extra_move=Move(
                    piece_id="R:1:7:7",
                    path=[(7.0, 7.0), (7.0, 6.0), (7.0, 5.0)],
                    start_tick=200,
                ),
            ),
        ]

        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert len(restored.active_moves) == 4
        assert restored.active_moves[0].piece_id == "P:1:6:4"
        assert restored.active_moves[1].piece_id == "N:1:7:1"
        # Knight path has 3 points
        assert len(restored.active_moves[1].path) == 3
        # Rook path has 4 points
        assert len(restored.active_moves[2].path) == 4
        # Castling move has extra_move
        assert restored.active_moves[3].extra_move is not None
        assert restored.active_moves[3].extra_move.piece_id == "R:1:7:7"

    def test_config_property_works_after_restore(self):
        """Verify that speed config is accessible after deserialization."""
        state = self._create_initial_game()
        restored = GameState.from_snapshot_dict(state.to_snapshot_dict())

        assert restored.config.seconds_per_square == 1.0
        assert restored.config.cooldown_seconds == 10.0

    def test_full_json_round_trip(self):
        """Full serialize -> JSON -> deserialize round trip."""
        state = self._create_mid_game_state()
        json_str = json.dumps(state.to_snapshot_dict())
        data = json.loads(json_str)
        restored = GameState.from_snapshot_dict(data)

        assert restored.game_id == state.game_id
        assert restored.speed == state.speed
        assert restored.status == state.status
        assert restored.current_tick == state.current_tick
        assert len(restored.board.pieces) == len(state.board.pieces)
        assert len(restored.active_moves) == len(state.active_moves)
        assert len(restored.cooldowns) == len(state.cooldowns)
        assert len(restored.replay_moves) == len(state.replay_moves)

    def test_snapshot_dict_keys(self):
        state = self._create_initial_game()
        data = state.to_snapshot_dict()
        expected_keys = {
            "game_id", "speed", "board_type", "board_width", "board_height",
            "players", "current_tick", "status", "winner", "win_reason",
            "ready_players", "pieces", "active_moves", "cooldowns",
            "replay_moves", "last_move_tick", "last_capture_tick",
            "started_at", "finished_at", "is_campaign",
        }
        assert set(data.keys()) == expected_keys

    def test_is_campaign_false_by_default(self):
        state = self._create_initial_game()
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)
        assert restored.is_campaign is False

    def test_is_campaign_round_trip(self):
        state = self._create_initial_game()
        state.is_campaign = True
        data = state.to_snapshot_dict()
        assert data["is_campaign"] is True

        restored = GameState.from_snapshot_dict(data)
        assert restored.is_campaign is True

    def test_is_campaign_missing_defaults_false(self):
        """Snapshots from before is_campaign was added should default to False."""
        state = self._create_initial_game()
        data = state.to_snapshot_dict()
        del data["is_campaign"]

        restored = GameState.from_snapshot_dict(data)
        assert restored.is_campaign is False

    def test_is_campaign_preserved_in_copy(self):
        state = self._create_initial_game()
        state.is_campaign = True
        copied = state.copy()
        assert copied.is_campaign is True


# ---------------------------------------------------------------------------
# 4-player game serialization
# ---------------------------------------------------------------------------


class TestFourPlayerSerialization:
    def test_4player_with_eliminated_players(self):
        """4-player game where some players have been eliminated (kings captured)."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
            game_id="4PELIM01",
        )
        state.status = GameStatus.PLAYING
        state.current_tick = 500

        # Eliminate players 3 and 4 by capturing their kings
        for piece in state.board.pieces:
            if piece.type == PieceType.KING and piece.player in (3, 4):
                piece.captured = True
        state.board.invalidate_position_map()

        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        # Verify eliminated kings are still captured
        captured_kings = [
            p for p in restored.board.pieces
            if p.type == PieceType.KING and p.captured
        ]
        assert len(captured_kings) == 2
        assert {k.player for k in captured_kings} == {3, 4}

        # Verify surviving kings are not captured
        surviving_kings = [
            p for p in restored.board.pieces
            if p.type == PieceType.KING and not p.captured
        ]
        assert len(surviving_kings) == 2
        assert {k.player for k in surviving_kings} == {1, 2}

    def test_4player_game_round_trip(self):
        state = GameEngine.create_game(
            speed=Speed.LIGHTNING,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
            game_id="4PTEST01",
        )
        data = state.to_snapshot_dict()
        restored = GameState.from_snapshot_dict(data)

        assert restored.board.board_type == BoardType.FOUR_PLAYER
        assert restored.board.width == 12
        assert restored.board.height == 12
        assert restored.speed == Speed.LIGHTNING
        assert len(restored.players) == 4
        # 4-player board has 64 pieces (16 per player)
        assert len(restored.board.pieces) == len(state.board.pieces)


# ---------------------------------------------------------------------------
# GameSnapshot wrapper serialization
# ---------------------------------------------------------------------------


class TestGameSnapshotSerialization:
    def test_basic_snapshot_round_trip(self):
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:100", 2: "bot:novice"},
            board_type=BoardType.STANDARD,
            game_id="SNAP0001",
        )
        snapshot = GameSnapshot(
            game_id="SNAP0001",
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_secretkey123"},
            ai_config={2: "novice"},
            server_id="worker1",
            snapshot_tick=0,
            snapshot_time=1718448000.0,
        )

        data = snapshot.to_dict()
        restored = GameSnapshot.from_dict(data)

        assert restored.game_id == "SNAP0001"
        assert restored.player_keys == {1: "p1_secretkey123"}
        assert restored.ai_config == {2: "novice"}
        assert restored.server_id == "worker1"
        assert restored.snapshot_tick == 0
        assert restored.snapshot_time == 1718448000.0
        assert restored.campaign_level_id is None
        assert restored.campaign_user_id is None
        assert restored.initial_board_str is None

    def test_campaign_snapshot(self):
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:42", 2: "bot:campaign"},
            board_type=BoardType.STANDARD,
            game_id="CAMP0001",
        )
        snapshot = GameSnapshot(
            game_id="CAMP0001",
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_campkey"},
            ai_config={2: "campaign"},
            campaign_level_id=5,
            campaign_user_id=42,
            initial_board_str="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
            server_id="worker2",
            snapshot_tick=300,
            snapshot_time=1718448300.0,
        )

        data = snapshot.to_dict()
        restored = GameSnapshot.from_dict(data)

        assert restored.campaign_level_id == 5
        assert restored.campaign_user_id == 42
        assert restored.initial_board_str == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

    def test_snapshot_json_round_trip(self):
        """Full JSON round trip for GameSnapshot."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "bot:novice"},
            board_type=BoardType.STANDARD,
            game_id="JSON0001",
        )
        snapshot = GameSnapshot(
            game_id="JSON0001",
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_key"},
            ai_config={2: "novice"},
            server_id="worker1",
            snapshot_tick=60,
            snapshot_time=1718448060.0,
        )

        json_str = json.dumps(snapshot.to_dict())
        data = json.loads(json_str)
        restored = GameSnapshot.from_dict(data)

        # Verify snapshot metadata
        assert restored.game_id == "JSON0001"
        assert restored.player_keys == {1: "p1_key"}
        assert restored.ai_config == {2: "novice"}

        # Verify the state can be deserialized
        game_state = GameState.from_snapshot_dict(restored.state)
        assert game_state.game_id == "JSON0001"
        assert game_state.speed == Speed.STANDARD
        assert len(game_state.board.pieces) == 32

    def test_snapshot_int_key_preservation_through_json(self):
        """Ensure int keys survive JSON serialization."""
        snapshot = GameSnapshot(
            game_id="KEYS0001",
            state={"game_id": "KEYS0001"},
            player_keys={1: "key1", 2: "key2", 3: "key3", 4: "key4"},
            ai_config={2: "novice", 3: "intermediate", 4: "advanced"},
        )

        json_str = json.dumps(snapshot.to_dict())
        restored = GameSnapshot.from_dict(json.loads(json_str))

        assert all(isinstance(k, int) for k in restored.player_keys)
        assert all(isinstance(k, int) for k in restored.ai_config)
        assert restored.player_keys[1] == "key1"
        assert restored.ai_config[4] == "advanced"

    def test_snapshot_dict_keys(self):
        snapshot = GameSnapshot(
            game_id="TEST",
            state={},
        )
        data = snapshot.to_dict()
        expected_keys = {
            "game_id", "state", "player_keys", "ai_config",
            "campaign_level_id", "campaign_user_id", "initial_board_str",
            "resigned_piece_ids", "draw_offers", "force_broadcast",
            "server_id", "snapshot_tick", "snapshot_time",
        }
        assert set(data.keys()) == expected_keys

    def test_snapshot_with_resigned_piece_ids(self):
        snapshot = GameSnapshot(
            game_id="RESN0001",
            state={"game_id": "RESN0001"},
            resigned_piece_ids=["K:3:5:0", "K:4:0:5"],
        )

        json_str = json.dumps(snapshot.to_dict())
        restored = GameSnapshot.from_dict(json.loads(json_str))

        assert restored.resigned_piece_ids == ["K:3:5:0", "K:4:0:5"]

    def test_snapshot_with_draw_offers(self):
        snapshot = GameSnapshot(
            game_id="DRAW0001",
            state={"game_id": "DRAW0001"},
            draw_offers={1, 3},
        )

        json_str = json.dumps(snapshot.to_dict())
        restored = GameSnapshot.from_dict(json.loads(json_str))

        assert restored.draw_offers == {1, 3}

    def test_snapshot_with_force_broadcast(self):
        snapshot = GameSnapshot(
            game_id="FBRC0001",
            state={"game_id": "FBRC0001"},
            force_broadcast=True,
        )

        data = snapshot.to_dict()
        assert data["force_broadcast"] is True

        restored = GameSnapshot.from_dict(data)
        assert restored.force_broadcast is True

    def test_snapshot_defaults_for_new_fields(self):
        """from_dict with missing new fields should use safe defaults."""
        data = {
            "game_id": "OLD00001",
            "state": {},
            "player_keys": {},
            "ai_config": {},
        }
        restored = GameSnapshot.from_dict(data)

        assert restored.resigned_piece_ids == []
        assert restored.draw_offers == set()
        assert restored.force_broadcast is False


# ---------------------------------------------------------------------------
# End-to-end: ManagedGame -> Snapshot -> Restore
# ---------------------------------------------------------------------------


class TestEndToEndSnapshot:
    def test_full_pipeline(self):
        """Simulate the full snapshot pipeline:
        1. Create a game via engine
        2. Apply some moves
        3. Snapshot the state
        4. Serialize to JSON (as Redis would store it)
        5. Deserialize from JSON
        6. Restore the GameState
        7. Verify the state is functionally equivalent
        """
        # 1. Create game
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:100", 2: "bot:novice"},
            board_type=BoardType.STANDARD,
            game_id="E2E00001",
        )

        # Mark ready and start
        GameEngine.set_player_ready(state, 1)
        GameEngine.set_player_ready(state, 2)
        assert state.status == GameStatus.PLAYING

        # 2. Make a move (pawn e2-e4)
        move = GameEngine.validate_move(state, 1, "P:1:6:4", 4, 4)
        assert move is not None
        GameEngine.apply_move(state, move)

        # Tick a few times
        for _ in range(5):
            GameEngine.tick(state)

        # 3. Create snapshot
        snapshot = GameSnapshot(
            game_id=state.game_id,
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_secret"},
            ai_config={2: "novice"},
            server_id="worker1",
            snapshot_tick=state.current_tick,
        )

        # 4. Serialize to JSON
        json_str = json.dumps(snapshot.to_dict())

        # 5. Deserialize from JSON
        snapshot_data = json.loads(json_str)
        restored_snapshot = GameSnapshot.from_dict(snapshot_data)

        # 6. Restore GameState
        restored_state = GameState.from_snapshot_dict(restored_snapshot.state)

        # 7. Verify
        assert restored_state.game_id == "E2E00001"
        assert restored_state.status == GameStatus.PLAYING
        assert restored_state.current_tick == state.current_tick
        assert len(restored_state.board.pieces) == 32
        assert len(restored_state.replay_moves) == len(state.replay_moves)
        assert restored_state.ready_players == {1, 2}

        # Verify the game can continue ticking after restore
        GameEngine.tick(restored_state)
        assert restored_state.current_tick == state.current_tick + 1

    def test_snapshot_size_reasonable(self):
        """Verify snapshot size is within expected bounds."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "bot:novice"},
            board_type=BoardType.STANDARD,
            game_id="SIZE0001",
        )
        snapshot = GameSnapshot(
            game_id=state.game_id,
            state=state.to_snapshot_dict(),
            player_keys={1: "p1_key"},
            ai_config={2: "novice"},
            server_id="worker1",
            snapshot_tick=0,
        )
        json_str = json.dumps(snapshot.to_dict())
        size_kb = len(json_str) / 1024

        # Initial state should be well under 20 KB
        assert size_kb < 20, f"Snapshot size {size_kb:.1f} KB exceeds expected bounds"

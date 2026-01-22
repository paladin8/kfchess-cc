"""Tests for the replay system."""

from datetime import datetime, UTC

import pytest

from kfchess.game.board import Board, BoardType
from kfchess.game.engine import GameEngine, GameEventType
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.replay import Replay, ReplayEngine, _convert_v1_to_v2
from kfchess.game.state import GameState, GameStatus, ReplayMove, Speed


class TestReplayDataclass:
    """Tests for the Replay dataclass."""

    def test_from_game_state(self):
        """Test creating a replay from a finished game state."""
        # Create a simple game
        board = Board.create_empty()
        board.add_piece(Piece.create(PieceType.KING, player=1, row=7, col=4))
        board.add_piece(Piece.create(PieceType.KING, player=2, row=0, col=4))
        board.add_piece(Piece.create(PieceType.QUEEN, player=1, row=6, col=4))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "player1", 2: "player2"},
            board=board,
            game_id="TESTGAME",
        )

        # Start the game
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Make a move
        move = GameEngine.validate_move(state, 1, "Q:1:6:4", 1, 4)
        assert move is not None
        GameEngine.apply_move(state, move)

        # Simulate to completion (capture the king)
        config = state.config
        total_move_ticks = 5 * config.ticks_per_square  # 5 squares to move
        for _ in range(total_move_ticks + 1):
            GameEngine.tick(state)

        # Mark as finished for test purposes
        state.status = GameStatus.FINISHED
        state.winner = 1
        state.finished_at = datetime.now(UTC)

        # Create replay from state
        replay = Replay.from_game_state(state)

        assert replay.version == 2
        assert replay.speed == Speed.STANDARD
        assert replay.board_type == BoardType.STANDARD
        assert replay.players == {1: "player1", 2: "player2"}
        assert len(replay.moves) >= 1  # At least the queen move
        assert replay.winner == 1
        assert replay.win_reason == "king_captured"
        assert replay.created_at is not None

    def test_to_dict(self):
        """Test serializing a replay to a dictionary."""
        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "player1", 2: "player2"},
            moves=[
                ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
                ReplayMove(tick=8, piece_id="P:2:1:4", to_row=3, to_col=4, player=2),
            ],
            total_ticks=1500,
            winner=1,
            win_reason="king_captured",
            created_at=datetime(2025, 1, 21, 12, 0, 0),
        )

        data = replay.to_dict()

        assert data["version"] == 2
        assert data["speed"] == "standard"
        assert data["board_type"] == "standard"
        assert data["players"] == {"1": "player1", "2": "player2"}
        assert len(data["moves"]) == 2
        assert data["moves"][0]["tick"] == 5
        assert data["moves"][0]["piece_id"] == "P:1:6:4"
        assert data["total_ticks"] == 1500
        assert data["winner"] == 1
        assert data["win_reason"] == "king_captured"
        assert data["created_at"] == "2025-01-21T12:00:00"

    def test_from_dict_v2(self):
        """Test loading a v2 replay from a dictionary."""
        data = {
            "version": 2,
            "speed": "standard",
            "board_type": "standard",
            "players": {"1": "player1", "2": "player2"},
            "moves": [
                {"tick": 5, "piece_id": "P:1:6:4", "to_row": 4, "to_col": 4, "player": 1},
                {"tick": 8, "piece_id": "P:2:1:4", "to_row": 3, "to_col": 4, "player": 2},
            ],
            "total_ticks": 1500,
            "winner": 1,
            "win_reason": "king_captured",
            "created_at": "2025-01-21T12:00:00",
        }

        replay = Replay.from_dict(data)

        assert replay.version == 2
        assert replay.speed == Speed.STANDARD
        assert replay.board_type == BoardType.STANDARD
        assert replay.players == {1: "player1", 2: "player2"}
        assert len(replay.moves) == 2
        assert replay.moves[0].tick == 5
        assert replay.moves[0].piece_id == "P:1:6:4"
        assert replay.total_ticks == 1500
        assert replay.winner == 1
        assert replay.created_at == datetime(2025, 1, 21, 12, 0, 0)

    def test_get_moves_at_tick(self):
        """Test getting moves at a specific tick."""
        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "p1", 2: "p2"},
            moves=[
                ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
                ReplayMove(tick=5, piece_id="P:2:1:4", to_row=3, to_col=4, player=2),
                ReplayMove(tick=10, piece_id="P:1:6:0", to_row=5, to_col=0, player=1),
            ],
            total_ticks=100,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        moves_at_5 = replay.get_moves_at_tick(5)
        assert len(moves_at_5) == 2

        moves_at_10 = replay.get_moves_at_tick(10)
        assert len(moves_at_10) == 1

        moves_at_15 = replay.get_moves_at_tick(15)
        assert len(moves_at_15) == 0

    def test_get_moves_in_range(self):
        """Test getting moves in a tick range."""
        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "p1", 2: "p2"},
            moves=[
                ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
                ReplayMove(tick=10, piece_id="P:2:1:4", to_row=3, to_col=4, player=2),
                ReplayMove(tick=15, piece_id="P:1:6:0", to_row=5, to_col=0, player=1),
            ],
            total_ticks=100,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        moves_5_10 = replay.get_moves_in_range(5, 10)
        assert len(moves_5_10) == 2

        moves_5_15 = replay.get_moves_in_range(5, 15)
        assert len(moves_5_15) == 3

        moves_20_30 = replay.get_moves_in_range(20, 30)
        assert len(moves_20_30) == 0


class TestV1Conversion:
    """Tests for converting v1 replays to v2 format."""

    def test_convert_v1_to_v2(self):
        """Test converting a v1 replay to v2 format."""
        v1_data = {
            "speed": "standard",
            "players": {"1": "player1", "2": "player2"},
            "moves": [
                {"pieceId": "P:1:6:4", "player": 1, "row": 4, "col": 4, "tick": 5},
                {"pieceId": "P:2:1:4", "player": 2, "row": 3, "col": 4, "tick": 8},
            ],
            "ticks": 1500,
        }

        replay = _convert_v1_to_v2(v1_data)

        assert replay.version == 2
        assert replay.speed == Speed.STANDARD
        assert replay.board_type == BoardType.STANDARD  # V1 only supported standard
        assert replay.players == {1: "player1", 2: "player2"}
        assert len(replay.moves) == 2
        assert replay.moves[0].tick == 5
        assert replay.moves[0].piece_id == "P:1:6:4"
        assert replay.moves[0].to_row == 4
        assert replay.moves[0].to_col == 4
        assert replay.moves[0].player == 1
        assert replay.total_ticks == 1500
        assert replay.winner is None  # V1 didn't store winner
        assert replay.win_reason is None
        assert replay.created_at is None

    def test_from_dict_auto_detects_v1(self):
        """Test that from_dict automatically detects v1 format."""
        v1_data = {
            "speed": "lightning",
            "players": {"1": "p1", "2": "p2"},
            "moves": [
                {"pieceId": "N:1:7:1", "player": 1, "row": 5, "col": 2, "tick": 3},
            ],
            "ticks": 500,
        }

        replay = Replay.from_dict(v1_data)

        assert replay.version == 2
        assert replay.speed == Speed.LIGHTNING
        assert len(replay.moves) == 1
        assert replay.moves[0].piece_id == "N:1:7:1"

    def test_roundtrip_conversion(self):
        """Test that a replay can be serialized and deserialized."""
        original = Replay(
            version=2,
            speed=Speed.LIGHTNING,
            board_type=BoardType.FOUR_PLAYER,
            players={1: "p1", 2: "p2", 3: "p3", 4: "p4"},
            moves=[
                ReplayMove(tick=1, piece_id="P:1:10:2", to_row=8, to_col=2, player=1),
                ReplayMove(tick=2, piece_id="P:2:1:3", to_row=3, to_col=3, player=2),
            ],
            total_ticks=200,
            winner=3,
            win_reason="king_captured",
            created_at=datetime(2025, 1, 21, 15, 30, 0),
        )

        data = original.to_dict()
        restored = Replay.from_dict(data)

        assert restored.version == original.version
        assert restored.speed == original.speed
        assert restored.board_type == original.board_type
        assert restored.players == original.players
        assert len(restored.moves) == len(original.moves)
        assert restored.total_ticks == original.total_ticks
        assert restored.winner == original.winner
        assert restored.win_reason == original.win_reason
        assert restored.created_at == original.created_at


class TestReplayEngine:
    """Tests for the ReplayEngine class."""

    def test_get_initial_state(self):
        """Test getting the initial state of a replay."""
        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "player1", 2: "player2"},
            moves=[
                ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
            ],
            total_ticks=100,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        engine = ReplayEngine(replay)
        state = engine.get_initial_state()

        assert state.current_tick == 0
        assert state.status == GameStatus.PLAYING
        assert len(state.board.pieces) == 32
        assert len(state.active_moves) == 0

    def test_get_state_at_tick_with_move(self):
        """Test getting state at a tick after a move was made."""
        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "player1", 2: "player2"},
            moves=[
                ReplayMove(tick=0, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
            ],
            total_ticks=100,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        engine = ReplayEngine(replay)

        # Get state at tick 5 (move should be in progress)
        state = engine.get_state_at_tick(5)
        assert state.current_tick == 5
        assert len(state.active_moves) == 1
        assert state.active_moves[0].piece_id == "P:1:6:4"

    def test_get_state_at_tick_after_move_complete(self):
        """Test getting state at a tick after a move completed."""
        config_standard = {
            "ticks_per_square": 10,
        }

        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "player1", 2: "player2"},
            moves=[
                ReplayMove(tick=0, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
            ],
            total_ticks=100,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        engine = ReplayEngine(replay)

        # Get state at tick 30 (2 squares * 10 ticks = 20, so move should be done)
        state = engine.get_state_at_tick(30)
        assert state.current_tick == 30

        # The move should be completed
        assert len(state.active_moves) == 0

        # The pawn should be at the destination
        pawn = state.board.get_piece_by_id("P:1:6:4")
        assert pawn is not None
        assert int(pawn.row) == 4
        assert int(pawn.col) == 4

    def test_moves_indexed_by_tick(self):
        """Test that moves are properly indexed by tick."""
        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "p1", 2: "p2"},
            moves=[
                ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
                ReplayMove(tick=5, piece_id="P:2:1:4", to_row=3, to_col=4, player=2),
                ReplayMove(tick=10, piece_id="P:1:6:0", to_row=5, to_col=0, player=1),
            ],
            total_ticks=100,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        engine = ReplayEngine(replay)

        assert 5 in engine._moves_by_tick
        assert len(engine._moves_by_tick[5]) == 2

        assert 10 in engine._moves_by_tick
        assert len(engine._moves_by_tick[10]) == 1


class TestReplayMoveRecording:
    """Tests for replay move recording in the game engine."""

    def test_moves_are_recorded(self):
        """Test that moves are recorded in the game state."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )

        # Start the game
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Make a pawn move
        move = GameEngine.validate_move(state, 1, "P:1:6:4", 4, 4)
        assert move is not None
        GameEngine.apply_move(state, move)

        # Check the move was recorded
        assert len(state.replay_moves) == 1
        assert state.replay_moves[0].piece_id == "P:1:6:4"
        assert state.replay_moves[0].to_row == 4
        assert state.replay_moves[0].to_col == 4
        assert state.replay_moves[0].player == 1
        assert state.replay_moves[0].tick == 0  # Move was made at tick 0

    def test_multiple_moves_recorded(self):
        """Test that multiple moves are recorded in order."""
        state = GameEngine.create_game(
            speed=Speed.LIGHTNING,  # Faster for testing
            players={1: "u:1", 2: "u:2"},
        )

        # Start the game
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Make moves for both players
        move1 = GameEngine.validate_move(state, 1, "P:1:6:0", 4, 0)
        assert move1 is not None
        GameEngine.apply_move(state, move1)

        move2 = GameEngine.validate_move(state, 2, "P:2:1:7", 3, 7)
        assert move2 is not None
        GameEngine.apply_move(state, move2)

        # Check both moves were recorded
        assert len(state.replay_moves) == 2
        assert state.replay_moves[0].piece_id == "P:1:6:0"
        assert state.replay_moves[1].piece_id == "P:2:1:7"

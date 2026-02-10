"""Tests for MoveGen."""


from kfchess.ai.move_gen import _INF_TRAVEL, MoveGen, compute_travel_ticks
from kfchess.ai.state_extractor import StateExtractor
from kfchess.game.board import Board, BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import GameState, GameStatus, Speed


def _make_game(speed: Speed = Speed.STANDARD) -> GameState:
    state = GameEngine.create_game(
        speed=speed,
        players={1: "bot:test1", 2: "bot:test2"},
        board_type=BoardType.STANDARD,
    )
    state.status = GameStatus.PLAYING
    return state


class TestMoveGen:
    def test_generates_candidates_initial_board(self):
        """Should generate candidates from initial board position."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)
        candidates = MoveGen.generate_candidates(state, ai_state, 1)
        assert len(candidates) > 0
        # All should be positional (no captures possible initially)
        for c in candidates:
            assert c.capture_type is None

    def test_respects_max_pieces(self):
        """Should limit number of pieces considered."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)
        candidates_1 = MoveGen.generate_candidates(
            state, ai_state, 1, max_pieces=1, max_candidates_per_piece=100
        )
        candidates_2 = MoveGen.generate_candidates(
            state, ai_state, 1, max_pieces=16, max_candidates_per_piece=100
        )
        # With 1 piece, should have fewer candidates
        piece_ids_1 = {c.piece_id for c in candidates_1}
        piece_ids_2 = {c.piece_id for c in candidates_2}
        assert len(piece_ids_1) <= 1
        assert len(piece_ids_2) >= 1

    def test_respects_max_candidates_per_piece(self):
        """Should limit candidates per piece."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)
        candidates = MoveGen.generate_candidates(
            state, ai_state, 1, max_pieces=1, max_candidates_per_piece=2
        )
        piece_ids = {c.piece_id for c in candidates}
        for pid in piece_ids:
            count = sum(1 for c in candidates if c.piece_id == pid)
            assert count <= 2

    def test_captures_detected(self):
        """Should detect capture opportunities."""
        # Create a board with a capture opportunity
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        # White rook that can capture black pawn
        board.pieces.append(Piece.create(PieceType.ROOK, 1, 4, 4))
        board.pieces.append(Piece.create(PieceType.PAWN, 2, 4, 7))
        # Kings (required)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING

        ai_state = StateExtractor.extract(state, ai_player=1)
        candidates = MoveGen.generate_candidates(
            state, ai_state, 1, max_pieces=16, max_candidates_per_piece=100
        )
        captures = [c for c in candidates if c.capture_type is not None]
        assert len(captures) > 0
        # One capture should be the rook taking the pawn
        assert any(
            c.piece_id == "R:1:4:4" and c.to_row == 4 and c.to_col == 7
            for c in captures
        )

    def test_no_candidates_when_all_on_cooldown(self):
        """Should return empty list when all pieces are on cooldown."""
        state = _make_game()
        # Put all player 1 pieces on cooldown
        from kfchess.game.moves import Cooldown

        for piece in state.board.get_pieces_for_player(1):
            state.cooldowns.append(
                Cooldown(piece_id=piece.id, start_tick=0, duration=300)
            )

        ai_state = StateExtractor.extract(state, ai_player=1)
        candidates = MoveGen.generate_candidates(state, ai_state, 1)
        assert len(candidates) == 0


class TestComputeTravelTicks:
    """Tests for compute_travel_ticks piece movement constraints."""

    # -- Rook -----------------------------------------------------------

    def test_rook_same_rank(self):
        """Rook on same rank returns correct distance."""
        assert compute_travel_ticks(3, 0, 3, 7, PieceType.ROOK, 6) == 7 * 6

    def test_rook_same_file(self):
        """Rook on same file returns correct distance."""
        assert compute_travel_ticks(0, 4, 7, 4, PieceType.ROOK, 6) == 7 * 6

    def test_rook_off_axis_returns_inf(self):
        """Rook not on same rank or file cannot reach target in one move."""
        result = compute_travel_ticks(3, 0, 0, 4, PieceType.ROOK, 6)
        assert result == _INF_TRAVEL

    def test_rook_diagonal_returns_inf(self):
        """Rook on a diagonal (dr == dc) still can't reach in one move."""
        result = compute_travel_ticks(0, 0, 3, 3, PieceType.ROOK, 6)
        assert result == _INF_TRAVEL

    # -- Bishop ---------------------------------------------------------

    def test_bishop_same_diagonal(self):
        """Bishop on same diagonal returns correct distance."""
        assert compute_travel_ticks(0, 0, 5, 5, PieceType.BISHOP, 6) == 5 * 6

    def test_bishop_off_diagonal_returns_inf(self):
        """Bishop not on same diagonal cannot reach target in one move."""
        result = compute_travel_ticks(0, 0, 3, 4, PieceType.BISHOP, 6)
        assert result == _INF_TRAVEL

    def test_bishop_same_rank_returns_inf(self):
        """Bishop on same rank but not diagonal cannot reach."""
        result = compute_travel_ticks(3, 0, 3, 5, PieceType.BISHOP, 6)
        assert result == _INF_TRAVEL

    # -- King -----------------------------------------------------------

    def test_king_adjacent(self):
        """King can reach adjacent square."""
        assert compute_travel_ticks(4, 4, 3, 5, PieceType.KING, 6) == 1 * 6

    def test_king_two_squares_returns_inf(self):
        """King cannot reach a square 2+ away in one move."""
        result = compute_travel_ticks(4, 4, 2, 4, PieceType.KING, 6)
        assert result == _INF_TRAVEL

    # -- Queen / Knight (unchanged behavior) ----------------------------

    def test_queen_any_direction(self):
        """Queen uses Chebyshev distance for any direction."""
        assert compute_travel_ticks(0, 0, 3, 3, PieceType.QUEEN, 6) == 3 * 6
        assert compute_travel_ticks(0, 0, 0, 5, PieceType.QUEEN, 6) == 5 * 6

    def test_knight_fixed_cost(self):
        """Knight returns 2 * tps for valid L-shape moves, INF otherwise."""
        assert compute_travel_ticks(0, 0, 2, 1, PieceType.KNIGHT, 6) == 2 * 6
        assert compute_travel_ticks(0, 0, 1, 2, PieceType.KNIGHT, 6) == 2 * 6
        # Non-L-shape targets are unreachable in a single move
        assert compute_travel_ticks(0, 0, 7, 7, PieceType.KNIGHT, 6) == 999_999
        assert compute_travel_ticks(0, 0, 0, 3, PieceType.KNIGHT, 6) == 999_999

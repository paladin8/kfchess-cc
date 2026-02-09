"""Tests for Eval scoring function."""

import pytest

from kfchess.ai.arrival_field import ArrivalField
from kfchess.ai.eval import (
    SAFETY_WEIGHT,
    Eval,
    _compute_development_urgency,
    _compute_pawn_data,
    _count_pawn_support,
    _is_isolated_pawn,
)
from kfchess.ai.move_gen import CandidateMove
from kfchess.ai.state_extractor import StateExtractor
from kfchess.game.board import Board, BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.moves import Move
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import GameStatus, Speed


def _make_simple_board() -> tuple:
    """Create a simple board with capture opportunities."""
    board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
    board.pieces.append(Piece.create(PieceType.ROOK, 1, 4, 0))
    board.pieces.append(Piece.create(PieceType.PAWN, 2, 4, 5))
    board.pieces.append(Piece.create(PieceType.QUEEN, 2, 4, 7))
    board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
    board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))

    state = GameEngine.create_game_from_board(
        speed=Speed.STANDARD,
        players={1: "bot:test1", 2: "bot:test2"},
        board=board,
    )
    state.status = GameStatus.PLAYING
    ai_state = StateExtractor.extract(state, ai_player=1)
    return state, ai_state


class TestEval:
    def test_capture_queen_scores_higher_than_pawn(self):
        """Capturing a queen should score higher than capturing a pawn."""
        _, ai_state = _make_simple_board()
        rook_piece = ai_state.pieces_by_id["R:1:4:0"]

        capture_pawn = CandidateMove(
            "R:1:4:0", 4, 5,
            capture_type=PieceType.PAWN, ai_piece=rook_piece,
        )
        capture_queen = CandidateMove(
            "R:1:4:0", 4, 7,
            capture_type=PieceType.QUEEN, ai_piece=rook_piece,
        )
        quiet_move = CandidateMove(
            "R:1:4:0", 4, 3, ai_piece=rook_piece,
        )

        scored = Eval.score_candidates(
            [capture_pawn, capture_queen, quiet_move], ai_state, noise=False
        )

        # Queen capture should be first
        assert scored[0][0].capture_type == PieceType.QUEEN
        # Pawn capture should be second
        assert scored[1][0].capture_type == PieceType.PAWN
        # Quiet move last
        assert scored[2][0].capture_type is None

    def test_captures_beat_quiet_moves(self):
        """Any capture should score higher than a quiet move."""
        _, ai_state = _make_simple_board()
        rook_piece = ai_state.pieces_by_id["R:1:4:0"]

        capture = CandidateMove(
            "R:1:4:0", 4, 5,
            capture_type=PieceType.PAWN, ai_piece=rook_piece,
        )
        quiet = CandidateMove(
            "R:1:4:0", 3, 0, ai_piece=rook_piece,
        )

        scored = Eval.score_candidates([capture, quiet], ai_state, noise=False)
        assert scored[0][0].capture_type is not None

    def test_noise_can_change_ordering(self):
        """With noise, ordering may differ between runs (statistical test)."""
        _, ai_state = _make_simple_board()

        # Two moves with similar scores
        move_a = CandidateMove("R:1:4:0", 4, 3)
        move_b = CandidateMove("R:1:4:0", 4, 2)

        # Run many times and check if ordering ever changes
        orderings = set()
        for _ in range(50):
            scored = Eval.score_candidates([move_a, move_b], ai_state, noise=True)
            first_col = scored[0][0].to_col
            orderings.add(first_col)

        # With noise, we should see both orderings at least once
        assert len(orderings) > 1

    def test_center_preference(self):
        """Moves toward center should score higher than edge moves (no noise)."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board_type=BoardType.STANDARD,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        knight_piece = ai_state.pieces_by_id["N:1:7:1"]

        # Knight to center vs knight to edge
        center_move = CandidateMove(
            "N:1:7:1", 5, 2, ai_piece=knight_piece,
        )
        edge_move = CandidateMove(
            "N:1:7:1", 5, 0, ai_piece=knight_piece,
        )

        scored = Eval.score_candidates(
            [center_move, edge_move], ai_state, noise=False
        )
        # Center move should score higher
        assert scored[0][0].to_col == 2


def _make_opening_board() -> tuple:
    """Create a board in opening position with all pieces on back ranks."""
    state = GameEngine.create_game(
        speed=Speed.STANDARD,
        players={1: "bot:test1", 2: "bot:test2"},
        board_type=BoardType.STANDARD,
    )
    state.status = GameStatus.PLAYING
    ai_state = StateExtractor.extract(state, ai_player=1)
    return state, ai_state


def _make_development_board(developed_count: int = 0) -> tuple:
    """Create a board with some pieces developed.

    Args:
        developed_count: Number of developable pieces already off back ranks (0-5).
    """
    board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
    # Always add kings
    board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
    board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))

    # Developable pieces: 2 knights + 2 bishops + 1 queen
    dev_positions_back = [(7, 1), (7, 6), (7, 2), (7, 5), (7, 3)]  # back ranks
    dev_positions_out = [(5, 2), (5, 5), (4, 3), (4, 4), (4, 6)]   # developed
    dev_types = [
        PieceType.KNIGHT, PieceType.KNIGHT,
        PieceType.BISHOP, PieceType.BISHOP,
        PieceType.QUEEN,
    ]

    for i, ptype in enumerate(dev_types):
        if i < developed_count:
            r, c = dev_positions_out[i]
            p = Piece.create(ptype, 1, r, c)
            p.moved = True
        else:
            r, c = dev_positions_back[i]
            p = Piece.create(ptype, 1, r, c)
        board.pieces.append(p)

    # Add some pawns for player 1
    for col in range(8):
        board.pieces.append(Piece.create(PieceType.PAWN, 1, 6, col))

    # Enemy pieces
    board.pieces.append(Piece.create(PieceType.KNIGHT, 2, 0, 1))

    state = GameEngine.create_game_from_board(
        speed=Speed.STANDARD,
        players={1: "bot:test1", 2: "bot:test2"},
        board=board,
    )
    state.status = GameStatus.PLAYING
    ai_state = StateExtractor.extract(state, ai_player=1)
    return state, ai_state


class TestDevelopmentUrgency:
    def test_full_urgency_when_all_undeveloped(self):
        """All developable pieces on back ranks → urgency = 1.0."""
        _, ai_state = _make_development_board(developed_count=0)
        assert _compute_development_urgency(ai_state) == 1.0

    def test_no_urgency_when_all_developed(self):
        """All developable pieces off back ranks → urgency = 0.0."""
        _, ai_state = _make_development_board(developed_count=5)
        assert _compute_development_urgency(ai_state) == 0.0

    def test_partial_urgency(self):
        """2 of 5 developed → urgency = 3/5."""
        _, ai_state = _make_development_board(developed_count=2)
        assert _compute_development_urgency(ai_state) == pytest.approx(3 / 5)

    def test_no_developable_pieces_zero_urgency(self):
        """No developable pieces at all → urgency = 0.0."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        assert _compute_development_urgency(ai_state) == 0.0

    def test_development_beats_pawn_push_in_opening(self):
        """Knight development should outscore pawn push when pieces are undeveloped."""
        _, ai_state = _make_development_board(developed_count=0)
        knight = ai_state.pieces_by_id["N:1:7:1"]

        # Knight from back rank to center
        knight_move = CandidateMove("N:1:7:1", 5, 2, ai_piece=knight)

        # Pawn push 2 squares
        pawn = ai_state.pieces_by_id["P:1:6:4"]
        pawn_move = CandidateMove("P:1:6:4", 4, 4, ai_piece=pawn)

        scored = Eval.score_candidates(
            [knight_move, pawn_move], ai_state, noise=False
        )
        # Knight development should win
        assert scored[0][0].piece_id == "N:1:7:1"

    def test_pawn_advance_dampened_in_opening(self):
        """Pawn advance score should be lower when urgency is high."""
        _, ai_state_opening = _make_development_board(developed_count=0)
        _, ai_state_developed = _make_development_board(developed_count=5)

        pawn_opening = ai_state_opening.pieces_by_id["P:1:6:4"]
        pawn_developed = ai_state_developed.pieces_by_id["P:1:6:4"]

        move_opening = CandidateMove("P:1:6:4", 4, 4, ai_piece=pawn_opening)
        move_developed = CandidateMove("P:1:6:4", 4, 4, ai_piece=pawn_developed)

        scored_opening = Eval.score_candidates([move_opening], ai_state_opening, noise=False)
        scored_developed = Eval.score_candidates([move_developed], ai_state_developed, noise=False)

        # Pawn advance should score lower when urgency is high
        assert scored_opening[0][1] < scored_developed[0][1]


class TestFirstMoveBonus:
    def test_unmoved_piece_scores_higher(self):
        """An unmoved knight should score higher than one that's already moved."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))

        # Unmoved knight on back rank
        unmoved = Piece.create(PieceType.KNIGHT, 1, 7, 1)
        board.pieces.append(unmoved)

        # Moved knight on back rank (returned to back rank after moving)
        moved = Piece.create(PieceType.KNIGHT, 1, 7, 6)
        moved.moved = True
        board.pieces.append(moved)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)

        unmoved_piece = ai_state.pieces_by_id["N:1:7:1"]
        moved_piece = ai_state.pieces_by_id["N:1:7:6"]

        # Both move to equivalent center positions
        unmoved_move = CandidateMove("N:1:7:1", 5, 2, ai_piece=unmoved_piece)
        moved_move = CandidateMove("N:1:7:6", 5, 5, ai_piece=moved_piece)

        scored = Eval.score_candidates(
            [unmoved_move, moved_move], ai_state, noise=False
        )
        # Unmoved knight should score higher due to first-move bonus
        assert scored[0][0].piece_id == "N:1:7:1"


class TestPawnStructure:
    def _make_pawn_board(self, pawn_cols: list[int]) -> tuple:
        """Create a board with pawns on specified columns for player 1."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))

        for col in pawn_cols:
            board.pieces.append(Piece.create(PieceType.PAWN, 1, 6, col))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        return state, ai_state

    def test_pawn_chain_bonus(self):
        """Pawn with diagonal support should score higher than unsupported."""
        # Pawns on d and e files (cols 3 and 4)
        _, ai_state = self._make_pawn_board([3, 4])
        pawn_positions, pawn_files = _compute_pawn_data(ai_state)

        # Moving d-pawn to d5 (row 5, col 3) — e-pawn on (6,4) supports diagonally
        support = _count_pawn_support(5, 3, ai_state, pawn_positions)
        assert support == 1

    def test_pawn_no_support(self):
        """Pawn with no adjacent pawns has no support."""
        _, ai_state = self._make_pawn_board([0, 7])
        pawn_positions, _ = _compute_pawn_data(ai_state)

        # a-pawn advancing — h-pawn is too far away
        support = _count_pawn_support(5, 0, ai_state, pawn_positions)
        assert support == 0

    def test_pawn_double_support(self):
        """Pawn supported by two pawns behind it."""
        # Pawns on c, d, e
        _, ai_state = self._make_pawn_board([2, 3, 4])
        pawn_positions, _ = _compute_pawn_data(ai_state)

        # d-pawn advances to d5 — c-pawn (6,2) and e-pawn (6,4) both support
        support = _count_pawn_support(5, 3, ai_state, pawn_positions)
        assert support == 2

    def test_isolated_pawn_detected(self):
        """A pawn with no friendly pawns on adjacent files is isolated."""
        _, ai_state = self._make_pawn_board([0, 4])  # a and e pawns
        _, pawn_files = _compute_pawn_data(ai_state)

        # a-pawn (file 0): no pawn on file 1 → isolated
        assert _is_isolated_pawn(0, pawn_files) is True

    def test_non_isolated_pawn(self):
        """A pawn with a neighbor on an adjacent file is not isolated."""
        _, ai_state = self._make_pawn_board([3, 4])  # d and e pawns
        _, pawn_files = _compute_pawn_data(ai_state)

        # d-pawn (file 3): e-pawn on file 4 → not isolated
        assert _is_isolated_pawn(3, pawn_files) is False

    def test_supported_pawn_push_beats_isolated(self):
        """Pushing a supported pawn should score better than pushing an isolated one."""
        # Pawns on b, c, g (a-pawn is isolated, c-pawn is supported by b)
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.PAWN, 1, 6, 0))  # a-pawn (isolated)
        board.pieces.append(Piece.create(PieceType.PAWN, 1, 6, 1))  # b-pawn
        board.pieces.append(Piece.create(PieceType.PAWN, 1, 6, 2))  # c-pawn

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)

        a_pawn = ai_state.pieces_by_id["P:1:6:0"]
        c_pawn = ai_state.pieces_by_id["P:1:6:2"]

        # Both advance 1 square (same advancement distance)
        a_push = CandidateMove("P:1:6:0", 5, 0, ai_piece=a_pawn)
        c_push = CandidateMove("P:1:6:2", 5, 2, ai_piece=c_pawn)

        scored = Eval.score_candidates([a_push, c_push], ai_state, noise=False)
        # c-pawn push should score higher (supported by b-pawn, not isolated)
        assert scored[0][0].piece_id == "P:1:6:2"


class TestKingThreatCaptureSafety:
    def test_bishop_preferred_over_queen_on_unsafe_square(self):
        """When capturing a king-threatening piece on an unsafe square,
        a lower-value piece should be preferred over a higher-value one.

        Setup:
        - Black knight at (5, 3) threatens white king at (7, 4)
        - Black pawn at (4, 4) supports the knight (can recapture on (5, 3))
        - White queen at (5, 0) can capture the knight
        - White bishop at (3, 1) can capture the knight (diagonal)

        Both get the king threat bonus, but the queen capture has a much
        higher safety cost (losing 9.0 vs 3.0), so bishop should score higher.
        """
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.QUEEN, 1, 5, 0))
        board.pieces.append(Piece.create(PieceType.BISHOP, 1, 3, 1))
        board.pieces.append(Piece.create(PieceType.KNIGHT, 2, 5, 3))  # threatens king
        board.pieces.append(Piece.create(PieceType.PAWN, 2, 4, 4))    # supports knight

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        arrival_data = ArrivalField.compute(ai_state, state.config)

        queen = ai_state.pieces_by_id["Q:1:5:0"]
        bishop = ai_state.pieces_by_id["B:1:3:1"]

        queen_capture = CandidateMove(
            "Q:1:5:0", 5, 3, capture_type=PieceType.KNIGHT, ai_piece=queen,
        )
        bishop_capture = CandidateMove(
            "B:1:3:1", 5, 3, capture_type=PieceType.KNIGHT, ai_piece=bishop,
        )

        scored = Eval.score_candidates(
            [queen_capture, bishop_capture], ai_state, noise=False,
            level=2, arrival_data=arrival_data,
        )
        # Bishop capture should rank higher — same material + threat bonus,
        # but much lower safety cost (losing bishop=3 vs queen=9)
        assert scored[0][0].piece_id == "B:1:3:1"


class TestPawnTravelingThreat:
    """Pawns should not advance into the ray of a traveling enemy piece."""

    def test_pawn_into_traveling_rook_ray_penalized(self):
        """A pawn moving into a traveling rook's path should get full safety penalty."""
        # Minimal board: P1 pawn at (5,4) can advance to (4,4).
        # Enemy rook is traveling down col 4 and will pass through (4,4).
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        pawn = Piece.create(PieceType.PAWN, 1, 5, 4)
        board.pieces.append(pawn)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 0))
        enemy_rook = Piece.create(PieceType.ROOK, 2, 0, 4)
        board.pieces.append(enemy_rook)
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 7))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING

        # Set up rook traveling from (0,4) to (7,4)
        rook_move = Move(
            piece_id=enemy_rook.id,
            path=[(0.0, 4.0), (1.0, 4.0), (2.0, 4.0), (3.0, 4.0),
                  (4.0, 4.0), (5.0, 4.0), (6.0, 4.0), (7.0, 4.0)],
            start_tick=0,
        )
        state.active_moves.append(rook_move)
        tps = state.config.ticks_per_square
        state.current_tick = 2 * tps  # Rook at ~row 2, heading toward row 4

        ai_state = StateExtractor.extract(state, ai_player=1)
        arrival_data = ArrivalField.compute(ai_state, state.config)

        # The destination (4,4) should have a traveling threat
        assert arrival_data.has_traveling_threat(4, 4)

        pawn_ai = ai_state.pieces_by_id[pawn.id]
        advance = CandidateMove(
            pawn.id, 4, 4, capture_type=None, ai_piece=pawn_ai,
        )

        scored = Eval.score_candidates(
            [advance], ai_state, noise=False, level=2, arrival_data=arrival_data,
        )

        # The pawn advance should have a strongly negative score due to
        # full safety penalty (no pawn discount for committed threats)
        score = scored[0][1]
        assert score < -SAFETY_WEIGHT * 0.5, (
            f"Pawn into traveling rook ray should be heavily penalized, got {score}"
        )

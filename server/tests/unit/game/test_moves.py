"""Tests for move validation and path computation."""


from kfchess.game.board import Board
from kfchess.game.moves import (
    Cooldown,
    Move,
    _compute_bishop_path,
    _compute_king_path,
    _compute_knight_path,
    _compute_pawn_path,
    _compute_queen_path,
    _compute_rook_path,
    build_path_clear_context,
    check_castling,
    compute_move_path,
)
from kfchess.game.pieces import Piece, PieceType


class TestMove:
    """Tests for the Move dataclass."""

    def test_move_properties(self):
        """Test Move dataclass properties."""
        move = Move(
            piece_id="P:1:6:4",
            path=[(6, 4), (5, 4), (4, 4)],
            start_tick=10,
        )

        assert move.start_position == (6, 4)
        assert move.end_position == (4, 4)
        assert move.num_squares == 2

    def test_move_single_square(self):
        """Test single square move."""
        move = Move(
            piece_id="K:1:7:4",
            path=[(7, 4), (6, 4)],
            start_tick=0,
        )

        assert move.num_squares == 1


class TestCooldown:
    """Tests for the Cooldown dataclass."""

    def test_cooldown_active(self):
        """Test cooldown active checking."""
        cooldown = Cooldown(piece_id="P:1:6:4", start_tick=10, duration=100)

        assert cooldown.is_active(10) is True
        assert cooldown.is_active(50) is True
        assert cooldown.is_active(109) is True
        assert cooldown.is_active(110) is False
        assert cooldown.is_active(200) is False


class TestPawnPath:
    """Tests for pawn movement."""

    def test_pawn_forward_one(self):
        """Test pawn moving forward one square."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        board.add_piece(pawn)

        path = _compute_pawn_path(pawn, board, 6, 4, 5, 4, [])

        assert path == [(6, 4), (5, 4)]

    def test_pawn_forward_two_from_start(self):
        """Test pawn moving forward two squares from starting position."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        board.add_piece(pawn)

        path = _compute_pawn_path(pawn, board, 6, 4, 4, 4, [])

        assert path == [(6, 4), (5, 4), (4, 4)]

    def test_pawn_forward_two_not_from_start(self):
        """Test pawn cannot move two squares if not on starting row."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=5, col=4)
        board.add_piece(pawn)

        path = _compute_pawn_path(pawn, board, 5, 4, 3, 4, [])

        assert path is None

    def test_pawn_blocked(self):
        """Test pawn cannot move forward if blocked."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        blocker = Piece.create(PieceType.PAWN, player=2, row=5, col=4)
        board.add_piece(pawn)
        board.add_piece(blocker)

        path = _compute_pawn_path(pawn, board, 6, 4, 5, 4, [])

        assert path is None

    def test_pawn_diagonal_capture(self):
        """Test pawn diagonal move requires stationary opponent piece."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        target_right = Piece.create(PieceType.PAWN, player=2, row=5, col=5)
        target_left = Piece.create(PieceType.PAWN, player=2, row=5, col=3)
        board.add_piece(pawn)
        board.add_piece(target_right)
        board.add_piece(target_left)

        # Diagonal move allowed when opponent piece at destination
        path = _compute_pawn_path(pawn, board, 6, 4, 5, 5, [])
        assert path == [(6, 4), (5, 5)]

        path = _compute_pawn_path(pawn, board, 6, 4, 5, 3, [])
        assert path == [(6, 4), (5, 3)]

        # Diagonal move NOT allowed if no piece at destination
        board2 = Board.create_empty()
        pawn2 = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        board2.add_piece(pawn2)
        path = _compute_pawn_path(pawn2, board2, 6, 4, 5, 5, [])
        assert path is None

    def test_pawn_backward_invalid(self):
        """Test pawn cannot move backward."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=5, col=4)
        board.add_piece(pawn)

        path = _compute_pawn_path(pawn, board, 5, 4, 6, 4, [])

        assert path is None

    def test_black_pawn_direction(self):
        """Test black pawn moves in opposite direction."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=2, row=1, col=4)
        board.add_piece(pawn)

        # Forward for black is increasing row
        path = _compute_pawn_path(pawn, board, 1, 4, 2, 4, [])
        assert path == [(1, 4), (2, 4)]

        # Two squares from start
        path = _compute_pawn_path(pawn, board, 1, 4, 3, 4, [])
        assert path == [(1, 4), (2, 4), (3, 4)]

        # Backward is invalid
        path = _compute_pawn_path(pawn, board, 1, 4, 0, 4, [])
        assert path is None


class TestKnightPath:
    """Tests for knight movement."""

    def test_knight_cannot_land_on_own_piece(self):
        """Test that knights cannot land on squares occupied by own pieces."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        # Own piece at knight's destination
        blocker = Piece.create(PieceType.PAWN, player=1, row=6, col=5)
        board.add_piece(knight)
        board.add_piece(blocker)

        # Knight tries to move to (6, 5) where own pawn is
        path = compute_move_path(knight, board, 6, 5, [])
        assert path is None  # Should be blocked

    def test_knight_cannot_land_on_own_moving_piece_destination(self):
        """Test that knights cannot land where own piece is moving to."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=6, col=0)
        board.add_piece(knight)
        board.add_piece(rook)

        # Rook is moving to (6, 5)
        rook_move = Move(
            piece_id=rook.id,
            path=[(6.0, 0.0), (6.0, 1.0), (6.0, 2.0), (6.0, 3.0), (6.0, 4.0), (6.0, 5.0)],
            start_tick=0,
        )

        # Knight tries to move to (6, 5) where rook will end up
        path = compute_move_path(knight, board, 6, 5, [rook_move])
        assert path is None  # Should be blocked

    def test_knight_can_land_on_enemy_piece(self):
        """Test that knights can land on squares occupied by enemy pieces."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        # Enemy piece at knight's destination
        enemy = Piece.create(PieceType.PAWN, player=2, row=6, col=5)
        board.add_piece(knight)
        board.add_piece(enemy)

        # Knight should be able to move to (6, 5) where enemy pawn is
        path = compute_move_path(knight, board, 6, 5, [])
        assert path is not None  # Should be allowed (collision will handle capture)

    def test_knight_can_land_on_vacating_square(self):
        """Test that knights can land on squares being vacated by own piece."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        # Own piece currently at destination but moving away
        moving_piece = Piece.create(PieceType.ROOK, player=1, row=6, col=5)
        board.add_piece(knight)
        board.add_piece(moving_piece)

        # Rook is moving away from (6, 5)
        rook_move = Move(
            piece_id=moving_piece.id,
            path=[(6.0, 5.0), (6.0, 6.0), (6.0, 7.0)],
            start_tick=0,
        )

        # Knight should be able to move to (6, 5) since rook is leaving
        path = compute_move_path(knight, board, 6, 5, [rook_move])
        assert path is not None  # Should be allowed

    def test_knight_l_moves(self):
        """Test all valid knight L-shaped moves with midpoint."""
        # All 8 possible knight moves from center
        from_row, from_col = 4, 4

        valid_destinations = [
            (2, 3),
            (2, 5),  # Up 2, left/right 1
            (3, 2),
            (3, 6),  # Up 1, left/right 2
            (5, 2),
            (5, 6),  # Down 1, left/right 2
            (6, 3),
            (6, 5),  # Down 2, left/right 1
        ]

        for to_row, to_col in valid_destinations:
            path = _compute_knight_path(from_row, from_col, to_row, to_col)
            # Knight paths have 3 points: start, midpoint, end
            assert path is not None, f"Failed for ({to_row}, {to_col})"
            assert len(path) == 3, f"Expected 3-point path for ({to_row}, {to_col})"
            assert path[0] == (float(from_row), float(from_col))
            # Midpoint should be average of start and end
            mid_row = (from_row + to_row) / 2.0
            mid_col = (from_col + to_col) / 2.0
            assert path[1] == (mid_row, mid_col), f"Midpoint wrong for ({to_row}, {to_col})"
            assert path[2] == (float(to_row), float(to_col))

    def test_knight_invalid_moves(self):
        """Test invalid knight moves."""
        # Straight moves
        assert _compute_knight_path(4, 4, 4, 5) is None
        assert _compute_knight_path(4, 4, 5, 4) is None

        # Diagonal moves
        assert _compute_knight_path(4, 4, 5, 5) is None
        assert _compute_knight_path(4, 4, 6, 6) is None

        # Same position
        assert _compute_knight_path(4, 4, 4, 4) is None


class TestBishopPath:
    """Tests for bishop movement."""

    def test_bishop_diagonal(self):
        """Test bishop diagonal moves."""
        # Northeast
        path = _compute_bishop_path(4, 4, 2, 6)
        assert path == [(4, 4), (3, 5), (2, 6)]

        # Southeast
        path = _compute_bishop_path(4, 4, 6, 6)
        assert path == [(4, 4), (5, 5), (6, 6)]

        # Southwest
        path = _compute_bishop_path(4, 4, 6, 2)
        assert path == [(4, 4), (5, 3), (6, 2)]

        # Northwest
        path = _compute_bishop_path(4, 4, 2, 2)
        assert path == [(4, 4), (3, 3), (2, 2)]

    def test_bishop_invalid_moves(self):
        """Test invalid bishop moves."""
        # Horizontal
        assert _compute_bishop_path(4, 4, 4, 6) is None

        # Vertical
        assert _compute_bishop_path(4, 4, 6, 4) is None

        # Not diagonal
        assert _compute_bishop_path(4, 4, 5, 6) is None


class TestRookPath:
    """Tests for rook movement."""

    def test_rook_horizontal(self):
        """Test rook horizontal moves."""
        path = _compute_rook_path(4, 4, 4, 7)
        assert path == [(4, 4), (4, 5), (4, 6), (4, 7)]

        path = _compute_rook_path(4, 4, 4, 0)
        assert path == [(4, 4), (4, 3), (4, 2), (4, 1), (4, 0)]

    def test_rook_vertical(self):
        """Test rook vertical moves."""
        path = _compute_rook_path(4, 4, 7, 4)
        assert path == [(4, 4), (5, 4), (6, 4), (7, 4)]

        path = _compute_rook_path(4, 4, 0, 4)
        assert path == [(4, 4), (3, 4), (2, 4), (1, 4), (0, 4)]

    def test_rook_invalid_moves(self):
        """Test invalid rook moves."""
        # Diagonal
        assert _compute_rook_path(4, 4, 5, 5) is None
        assert _compute_rook_path(4, 4, 6, 6) is None

        # Same position
        assert _compute_rook_path(4, 4, 4, 4) is None


class TestQueenPath:
    """Tests for queen movement."""

    def test_queen_diagonal(self):
        """Test queen diagonal moves (like bishop)."""
        path = _compute_queen_path(4, 4, 2, 6)
        assert path == [(4, 4), (3, 5), (2, 6)]

    def test_queen_horizontal(self):
        """Test queen horizontal moves (like rook)."""
        path = _compute_queen_path(4, 4, 4, 7)
        assert path == [(4, 4), (4, 5), (4, 6), (4, 7)]

    def test_queen_vertical(self):
        """Test queen vertical moves (like rook)."""
        path = _compute_queen_path(4, 4, 7, 4)
        assert path == [(4, 4), (5, 4), (6, 4), (7, 4)]

    def test_queen_invalid_moves(self):
        """Test invalid queen moves."""
        # Knight-like
        assert _compute_queen_path(4, 4, 6, 5) is None

        # Same position
        assert _compute_queen_path(4, 4, 4, 4) is None


class TestKingPath:
    """Tests for king movement."""

    def test_king_all_directions(self):
        """Test king can move one square in any direction."""
        from_row, from_col = 4, 4

        valid_destinations = [
            (3, 3),
            (3, 4),
            (3, 5),  # Up row
            (4, 3),
            (4, 5),  # Same row
            (5, 3),
            (5, 4),
            (5, 5),  # Down row
        ]

        for to_row, to_col in valid_destinations:
            path = _compute_king_path(from_row, from_col, to_row, to_col)
            assert path == [(from_row, from_col), (to_row, to_col)], f"Failed for ({to_row}, {to_col})"

    def test_king_invalid_moves(self):
        """Test invalid king moves (more than one square)."""
        assert _compute_king_path(4, 4, 2, 4) is None  # Two squares
        assert _compute_king_path(4, 4, 4, 6) is None  # Two squares
        assert _compute_king_path(4, 4, 6, 6) is None  # Two diagonal
        assert _compute_king_path(4, 4, 4, 4) is None  # Same position


class TestComputeMovePath:
    """Tests for the main move path computation."""

    def test_compute_move_path_pawn(self):
        """Test compute_move_path for a pawn."""
        board = Board.create_standard()
        pawn = board.get_piece_at(6, 4)

        path = compute_move_path(pawn, board, 5, 4, [])
        assert path == [(6, 4), (5, 4)]

    def test_compute_move_path_blocked(self):
        """Test move path is None when blocked by own piece."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=0)
        blocker = Piece.create(PieceType.PAWN, player=1, row=7, col=3)
        board.add_piece(rook)
        board.add_piece(blocker)

        path = compute_move_path(rook, board, 7, 7, [])
        assert path is None  # Blocked by own pawn

    def test_compute_move_path_invalid_destination(self):
        """Test move path is None for invalid destination."""
        board = Board.create_standard()
        pawn = board.get_piece_at(6, 4)

        # Off board
        path = compute_move_path(pawn, board, -1, 4, [])
        assert path is None

        # Same position
        path = compute_move_path(pawn, board, 6, 4, [])
        assert path is None


class TestCastling:
    """Tests for castling validation."""

    def test_kingside_castling(self):
        """Test kingside castling."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        result = check_castling(king, board, 7, 6, [])

        assert result is not None
        king_move, rook_move = result
        assert king_move.path == [(7, 4), (7, 5), (7, 6)]
        # Rook path now includes intermediate squares for consistent timing
        assert rook_move.path == [(7, 7), (7, 6), (7, 5)]

    def test_queenside_castling(self):
        """Test queenside castling."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=0)
        board.add_piece(king)
        board.add_piece(rook)

        result = check_castling(king, board, 7, 2, [])

        assert result is not None
        king_move, rook_move = result
        assert king_move.path == [(7, 4), (7, 3), (7, 2)]
        # Rook path now includes intermediate squares for consistent timing
        assert rook_move.path == [(7, 0), (7, 1), (7, 2), (7, 3)]

    def test_castling_king_moved(self):
        """Test castling fails if king has moved."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        king.moved = True
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        result = check_castling(king, board, 7, 6, [])
        assert result is None

    def test_castling_rook_moved(self):
        """Test castling fails if rook has moved."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        rook.moved = True
        board.add_piece(king)
        board.add_piece(rook)

        result = check_castling(king, board, 7, 6, [])
        assert result is None

    def test_castling_path_blocked(self):
        """Test castling fails if path is blocked."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        blocker = Piece.create(PieceType.BISHOP, player=1, row=7, col=5)
        board.add_piece(king)
        board.add_piece(rook)
        board.add_piece(blocker)

        result = check_castling(king, board, 7, 6, [])
        assert result is None

    def test_not_king(self):
        """Test castling only works for kings."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=0)
        board.add_piece(rook)

        result = check_castling(rook, board, 7, 2, [])
        assert result is None

    def test_castling_blocked_by_moving_piece(self):
        """Test castling fails if a piece is moving through the path."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        # A piece on row 2 is moving to f1 (row 7, col 5) which is in castling path
        moving_piece = Piece.create(PieceType.BISHOP, player=1, row=2, col=5)
        board.add_piece(king)
        board.add_piece(rook)
        board.add_piece(moving_piece)

        # Create an active move for the bishop ending at f1 (7, 5)
        active_move = Move(
            piece_id=moving_piece.id,
            path=[(2, 5), (3, 6), (4, 7), (5, 6), (6, 5), (7, 4)],  # Diagonal to e1
            start_tick=0,
        )
        # Actually let's make it end at f1 (7, 5) which is between king and rook
        active_move = Move(
            piece_id=moving_piece.id,
            path=[(2, 5), (7, 5)],  # Moving to f1
            start_tick=0,
        )

        result = check_castling(king, board, 7, 6, [active_move])
        assert result is None  # Castling should be blocked

    def test_castling_rook_on_cooldown(self):
        """Test castling fails if rook is on cooldown."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        # Rook is on cooldown
        cooldowns = [Cooldown(piece_id=rook.id, start_tick=0, duration=50)]

        result = check_castling(
            king, board, 7, 6, [],
            cooldowns=cooldowns, current_tick=10
        )
        assert result is None  # Castling should be blocked

    def test_castling_rook_on_cooldown_expired(self):
        """Test castling succeeds if rook's cooldown has expired."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        # Rook had a cooldown that expired
        cooldowns = [Cooldown(piece_id=rook.id, start_tick=0, duration=50)]

        result = check_castling(
            king, board, 7, 6, [],
            cooldowns=cooldowns, current_tick=60  # Cooldown expired at tick 50
        )
        assert result is not None  # Castling should succeed

    def test_castling_rook_moving(self):
        """Test castling fails if rook is currently moving."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        # Rook is currently moving (returning from somewhere)
        rook_move = Move(
            piece_id=rook.id,
            path=[(7, 5), (7, 6), (7, 7)],  # Moving back to h1
            start_tick=0,
        )

        result = check_castling(king, board, 7, 6, [rook_move])
        assert result is None  # Castling should be blocked


class TestPathBlocking:
    """Tests for path blocking rules with moving pieces."""

    def test_can_move_to_vacating_enemy_square(self):
        """Moving enemy has vacated - square is effectively empty."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy = Piece.create(PieceType.QUEEN, player=2, row=4, col=4)
        board.add_piece(rook)
        board.add_piece(enemy)

        # Enemy queen is moving away (vacating)
        enemy_move = Move(
            piece_id=enemy.id,
            path=[(4.0, 4.0), (4.0, 5.0), (4.0, 6.0), (4.0, 7.0)],
            start_tick=0,
        )

        # Rook can move to (4, 4) - enemy has vacated, square is empty
        # (collision detection handles any mid-path interactions)
        path = compute_move_path(rook, board, 4, 4, [enemy_move])
        assert path is not None  # Square is empty, move allowed

    def test_can_capture_stationary_enemy(self):
        """Can capture stationary enemy piece."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy = Piece.create(PieceType.QUEEN, player=2, row=4, col=4)
        board.add_piece(rook)
        board.add_piece(enemy)

        # No active moves - enemy is stationary
        path = compute_move_path(rook, board, 4, 4, [])
        assert path is not None  # Can capture stationary enemy

    def test_own_forward_path_blocks_own_pieces(self):
        """Rule 2: Own moving piece's forward path blocks own other pieces."""
        board = Board.create_empty()
        rook1 = Piece.create(PieceType.ROOK, player=1, row=4, col=0)  # Moving rook
        rook2 = Piece.create(PieceType.ROOK, player=1, row=0, col=4)  # Trying to move
        board.add_piece(rook1)
        board.add_piece(rook2)

        # Rook1 is moving from (4,0) to (4,7) - forward path includes (4,4)
        rook1_move = Move(
            piece_id=rook1.id,
            path=[(4.0, 0.0), (4.0, 1.0), (4.0, 2.0), (4.0, 3.0), (4.0, 4.0), (4.0, 5.0), (4.0, 6.0), (4.0, 7.0)],
            start_tick=0,
        )

        # Rook2 tries to move from (0,4) to (4,4) - blocked by rook1's forward path
        path = compute_move_path(rook2, board, 4, 4, [rook1_move], current_tick=0, ticks_per_square=30)
        assert path is None  # Blocked by own rook's forward path

    def test_own_backward_path_does_not_block(self):
        """Own moving piece's already-traversed path does NOT block."""
        board = Board.create_empty()
        rook1 = Piece.create(PieceType.ROOK, player=1, row=4, col=0)  # Moving rook
        rook2 = Piece.create(PieceType.ROOK, player=1, row=0, col=2)  # Trying to move
        board.add_piece(rook1)
        board.add_piece(rook2)

        # Rook1 is moving from (4,0) to (4,7)
        rook1_move = Move(
            piece_id=rook1.id,
            path=[(4.0, 0.0), (4.0, 1.0), (4.0, 2.0), (4.0, 3.0), (4.0, 4.0), (4.0, 5.0), (4.0, 6.0), (4.0, 7.0)],
            start_tick=0,
        )

        # At tick 90 (3 squares traversed), rook1 has passed (4,2)
        # Rook2 should be able to move to (4,2) - already traversed
        path = compute_move_path(rook2, board, 4, 2, [rook1_move], current_tick=90, ticks_per_square=30)
        assert path is not None  # Allowed - already traversed path doesn't block

    def test_enemy_forward_path_does_not_block(self):
        """Enemy moving piece's forward path does NOT block own pieces."""
        board = Board.create_empty()
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=0)  # Enemy moving
        own_rook = Piece.create(PieceType.ROOK, player=1, row=0, col=4)  # Trying to move
        board.add_piece(enemy_rook)
        board.add_piece(own_rook)

        # Enemy rook is moving from (4,0) to (4,7) - forward path includes (4,4)
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 0.0), (4.0, 1.0), (4.0, 2.0), (4.0, 3.0), (4.0, 4.0), (4.0, 5.0), (4.0, 6.0), (4.0, 7.0)],
            start_tick=0,
        )

        # Own rook can move through enemy's forward path
        path = compute_move_path(own_rook, board, 4, 4, [enemy_move], current_tick=0, ticks_per_square=30)
        assert path is not None  # Enemy forward path doesn't block us

    def test_knight_can_move_to_vacating_enemy_square(self):
        """Knight can move to square being vacated by enemy."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        enemy = Piece.create(PieceType.PAWN, player=2, row=6, col=5)
        board.add_piece(knight)
        board.add_piece(enemy)

        # Enemy pawn is moving away (vacating)
        enemy_move = Move(
            piece_id=enemy.id,
            path=[(6.0, 5.0), (5.0, 5.0)],
            start_tick=0,
        )

        # Knight can move to (6, 5) - enemy has vacated, square is empty
        path = compute_move_path(knight, board, 6, 5, [enemy_move])
        assert path is not None  # Square is empty, move allowed

    def test_knight_blocked_by_own_forward_path(self):
        """Knight cannot land on own piece's forward path."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=6, col=0)  # Moving rook
        board.add_piece(knight)
        board.add_piece(rook)

        # Rook is moving from (6,0) to (6,7) - forward path includes (6,5)
        rook_move = Move(
            piece_id=rook.id,
            path=[(6.0, 0.0), (6.0, 1.0), (6.0, 2.0), (6.0, 3.0), (6.0, 4.0), (6.0, 5.0), (6.0, 6.0), (6.0, 7.0)],
            start_tick=0,
        )

        # Knight tries to land on (6, 5) - blocked by rook's forward path
        path = compute_move_path(knight, board, 6, 5, [rook_move], current_tick=0, ticks_per_square=30)
        assert path is None  # Blocked by own rook's forward path

    def test_knight_forward_path_does_not_block(self):
        """Knight's forward path (including midpoints) does not block other pieces."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)  # Moving knight
        rook = Piece.create(PieceType.ROOK, player=1, row=0, col=5)  # Trying to move
        board.add_piece(knight)
        board.add_piece(rook)

        # Knight is moving from (4,4) to (6,5) - path includes midpoint (5.0, 4.5)
        # Knights jump, so their path should not block other pieces
        knight_move = Move(
            piece_id=knight.id,
            path=[(4.0, 4.0), (5.0, 4.5), (6.0, 5.0)],
            start_tick=0,
        )

        # Rook can move through knight's path - knights jump and don't block
        # Moving to (6,5) would be blocked by knight's destination, but (5,5) should be allowed
        path = compute_move_path(rook, board, 5, 5, [knight_move], current_tick=0, ticks_per_square=30)
        assert path is not None  # Knight's midpoint doesn't block

    def test_pawn_can_advance_to_vacating_own_square(self):
        """Pawn can move forward to a square being vacated by a friendly piece."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=3)
        knight = Piece.create(PieceType.KNIGHT, player=1, row=5, col=3)
        board.add_piece(pawn)
        board.add_piece(knight)

        # Knight is moving away from (5,3)
        knight_move = Move(
            piece_id=knight.id,
            path=[(5.0, 3.0), (4.0, 3.5), (3.0, 4.0)],
            start_tick=0,
        )

        # Pawn should be able to advance to (5,3) — knight has vacated
        path = compute_move_path(pawn, board, 5, 3, [knight_move])
        assert path is not None

    def test_pawn_cannot_advance_to_own_stationary_piece(self):
        """Pawn cannot move forward to a square occupied by a stationary friendly piece."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=3)
        knight = Piece.create(PieceType.KNIGHT, player=1, row=5, col=3)
        board.add_piece(pawn)
        board.add_piece(knight)

        # Knight is stationary — no active moves
        path = compute_move_path(pawn, board, 5, 3, [])
        assert path is None

    def test_pawn_double_advance_through_vacating_square(self):
        """Pawn can double-advance when the intermediate square is vacated."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=3)
        # Knight on the intermediate square (5,3)
        knight = Piece.create(PieceType.KNIGHT, player=1, row=5, col=3)
        board.add_piece(pawn)
        board.add_piece(knight)

        # Knight is moving away from (5,3) to (3,4)
        knight_move = Move(
            piece_id=knight.id,
            path=[(5.0, 3.0), (4.0, 3.5), (3.0, 4.0)],
            start_tick=0,
        )

        # Pawn should be able to double-advance through the vacated square
        path = compute_move_path(pawn, board, 4, 3, [knight_move])
        assert path is not None


class TestSameLineSliderBlocking:
    """Tests for same-line slider blocking of moving enemy pieces."""

    def test_rook_blocked_by_enemy_rook_same_rank(self):
        """Rook cannot move through enemy rook moving along same rank."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=7)
        board.add_piece(own_rook)
        board.add_piece(enemy_rook)

        # Enemy rook moving left along row 4
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 7.0), (4.0, 6.0), (4.0, 5.0), (4.0, 4.0)],
            start_tick=0,
        )

        # Own rook tries to move right along same row - blocked by enemy's forward path
        path = compute_move_path(
            own_rook, board, 4, 5, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_rook_blocked_by_enemy_rook_same_file(self):
        """Rook cannot move through enemy rook moving along same file."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=7, col=4)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=0, col=4)
        board.add_piece(own_rook)
        board.add_piece(enemy_rook)

        # Enemy rook moving down along col 4
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(0.0, 4.0), (1.0, 4.0), (2.0, 4.0), (3.0, 4.0)],
            start_tick=0,
        )

        # Own rook tries to move up along same file - blocked
        path = compute_move_path(
            own_rook, board, 3, 4, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_bishop_blocked_by_enemy_queen_same_diagonal(self):
        """Bishop cannot move through enemy queen on same diagonal (opposite direction)."""
        board = Board.create_empty()
        own_bishop = Piece.create(PieceType.BISHOP, player=1, row=7, col=0)
        enemy_queen = Piece.create(PieceType.QUEEN, player=2, row=3, col=4)
        board.add_piece(own_bishop)
        board.add_piece(enemy_queen)

        # Enemy queen moving down-left along same anti-diagonal (row+col=7)
        enemy_move = Move(
            piece_id=enemy_queen.id,
            path=[(3.0, 4.0), (4.0, 3.0), (5.0, 2.0), (6.0, 1.0)],
            start_tick=0,
        )

        # Bishop tries to move up-right along same diagonal - blocked
        path = compute_move_path(
            own_bishop, board, 4, 3, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_rook_not_blocked_by_enemy_rook_different_rank(self):
        """Rook CAN move when enemy rook is on a different rank (parallel but not same line)."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=3, col=4)
        board.add_piece(own_rook)
        board.add_piece(enemy_rook)

        # Enemy rook moving along row 3 (different rank)
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(3.0, 4.0), (3.0, 3.0), (3.0, 2.0), (3.0, 1.0)],
            start_tick=0,
        )

        # Own rook moves along row 4 - not blocked
        path = compute_move_path(
            own_rook, board, 4, 7, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is not None

    def test_rook_not_blocked_by_enemy_knight(self):
        """Rook NOT blocked by enemy knight (knight moves in L-shape, not along a line)."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_knight = Piece.create(PieceType.KNIGHT, player=2, row=4, col=6)
        board.add_piece(own_rook)
        board.add_piece(enemy_knight)

        # Knight moving away in an L-shape (not along the rank)
        enemy_move = Move(
            piece_id=enemy_knight.id,
            path=[(4.0, 6.0), (3.0, 6.5), (2.0, 7.0)],
            start_tick=0,
        )

        # Rook can move through - knight doesn't move along the same line
        path = compute_move_path(
            own_rook, board, 4, 7, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is not None

    def test_rook_blocked_by_enemy_pawn_same_rank(self):
        """Rook blocked by enemy pawn advancing along the same rank."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_pawn = Piece.create(PieceType.PAWN, player=2, row=4, col=6)
        board.add_piece(own_rook)
        board.add_piece(enemy_pawn)

        # Enemy pawn moving left along row 4 (e.g. 4-player board pawn)
        enemy_move = Move(
            piece_id=enemy_pawn.id,
            path=[(4.0, 6.0), (4.0, 5.0)],
            start_tick=0,
        )

        # Rook tries to move right along same row - blocked by pawn's forward path
        path = compute_move_path(
            own_rook, board, 4, 5, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_queen_blocked_by_enemy_king_same_file(self):
        """Queen blocked by enemy king moving along the same file."""
        board = Board.create_empty()
        own_queen = Piece.create(PieceType.QUEEN, player=1, row=7, col=3)
        enemy_king = Piece.create(PieceType.KING, player=2, row=2, col=3)
        board.add_piece(own_queen)
        board.add_piece(enemy_king)

        # Enemy king moving down along col 3
        enemy_move = Move(
            piece_id=enemy_king.id,
            path=[(2.0, 3.0), (3.0, 3.0)],
            start_tick=0,
        )

        # Queen tries to move up along same file - blocked
        path = compute_move_path(
            own_queen, board, 3, 3, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_perpendicular_enemy_rook_does_not_block(self):
        """Enemy rook moving perpendicularly does not trigger same-line blocking."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=0, col=4)
        board.add_piece(own_rook)
        board.add_piece(enemy_rook)

        # Enemy rook moving vertically on col 4
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(0.0, 4.0), (1.0, 4.0), (2.0, 4.0), (3.0, 4.0), (4.0, 4.0)],
            start_tick=0,
        )

        # Own rook moves horizontally on row 4 - perpendicular, not same-line
        path = compute_move_path(
            own_rook, board, 4, 7, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is not None

    def test_enemy_slider_completed_move_does_not_block(self):
        """Enemy slider whose move is complete (forward path empty) does not block."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=7)
        board.add_piece(own_rook)
        board.add_piece(enemy_rook)

        # Enemy rook was moving left along row 4
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 7.0), (4.0, 6.0), (4.0, 5.0), (4.0, 4.0)],
            start_tick=0,
        )

        # At tick 90 (3 segments * 30 ticks), enemy has completed the move
        path = compute_move_path(
            own_rook, board, 4, 5, [enemy_move], current_tick=90, ticks_per_square=30
        )
        assert path is not None

    def test_rook_can_move_short_behind_enemy_moving_away(self):
        """Rook can move to a short destination behind enemy moving away on same line."""
        board = Board.create_empty()
        own_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=3)
        board.add_piece(own_rook)
        board.add_piece(enemy_rook)

        # Enemy rook moving right (away from us) along row 4
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 3.0), (4.0, 4.0), (4.0, 5.0), (4.0, 6.0), (4.0, 7.0)],
            start_tick=0,
        )

        # At tick 60 (2 segments), enemy has passed (4,5) and forward path is {(4,5),(4,6),(4,7)}
        # Own rook moves to (4,2) - behind enemy, no overlap with forward path
        path = compute_move_path(
            own_rook, board, 4, 2, [enemy_move], current_tick=60, ticks_per_square=30
        )
        assert path is not None


class TestPawnOncomingEnemyBlocking:
    """Tests for pawn forward moves blocked by oncoming enemy pieces."""

    def test_pawn_blocked_by_oncoming_king(self):
        """Pawn forward move blocked by king moving toward it on same file."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        enemy_king = Piece.create(PieceType.KING, player=2, row=4, col=4)
        board.add_piece(pawn)
        board.add_piece(enemy_king)

        # Enemy king moving down toward pawn on same file
        enemy_move = Move(
            piece_id=enemy_king.id,
            path=[(4.0, 4.0), (5.0, 4.0)],
            start_tick=0,
        )

        # Pawn tries to move forward (up) - blocked by oncoming enemy
        path = compute_move_path(
            pawn, board, 5, 4, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_pawn_blocked_by_oncoming_queen(self):
        """Pawn forward move blocked by queen moving toward it on same file."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=3)
        enemy_queen = Piece.create(PieceType.QUEEN, player=2, row=3, col=3)
        board.add_piece(pawn)
        board.add_piece(enemy_queen)

        # Enemy queen moving down toward pawn on same file
        enemy_move = Move(
            piece_id=enemy_queen.id,
            path=[(3.0, 3.0), (4.0, 3.0), (5.0, 3.0)],
            start_tick=0,
        )

        # Pawn tries to move forward - blocked
        path = compute_move_path(
            pawn, board, 5, 3, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None

    def test_pawn_not_blocked_when_enemy_moving_away(self):
        """Pawn can move forward when enemy on same file is moving away."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=4)
        board.add_piece(pawn)
        board.add_piece(enemy_rook)

        # Enemy rook moving UP (away from pawn) on same file
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 4.0), (3.0, 4.0), (2.0, 4.0)],
            start_tick=0,
        )

        # Pawn moves forward - not blocked (enemy is moving away)
        path = compute_move_path(
            pawn, board, 5, 4, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is not None

    def test_pawn_not_blocked_when_enemy_on_different_file(self):
        """Pawn can move forward when oncoming enemy is on adjacent file."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=5)
        board.add_piece(pawn)
        board.add_piece(enemy_rook)

        # Enemy rook moving down on adjacent file (col 5)
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 5.0), (5.0, 5.0), (6.0, 5.0)],
            start_tick=0,
        )

        # Pawn moves forward - not blocked (different file)
        path = compute_move_path(
            pawn, board, 5, 4, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is not None

    def test_pawn_diagonal_capture_not_blocked(self):
        """Diagonal pawn capture is not affected by the straight-line check."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        enemy_piece = Piece.create(PieceType.PAWN, player=2, row=5, col=5)
        board.add_piece(pawn)
        board.add_piece(enemy_piece)

        # No active moves - enemy is stationary, pawn can capture diagonally
        path = compute_move_path(
            pawn, board, 5, 5, [], current_tick=0, ticks_per_square=30
        )
        assert path is not None

    def test_pawn_double_forward_blocked(self):
        """Double pawn push blocked by oncoming enemy on same file."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        enemy_knight = Piece.create(PieceType.KNIGHT, player=2, row=3, col=4)
        board.add_piece(pawn)
        board.add_piece(enemy_knight)

        # Enemy knight moving down on same file (unusual but possible in kung fu chess)
        enemy_move = Move(
            piece_id=enemy_knight.id,
            path=[(3.0, 4.0), (5.0, 4.0)],
            start_tick=0,
        )

        # Pawn tries double push - blocked
        path = compute_move_path(
            pawn, board, 4, 4, [enemy_move], current_tick=0, ticks_per_square=30
        )
        assert path is None


class TestPathClearContext:
    """Tests that PathClearContext produces identical results to inline computation."""

    def test_context_matches_inline_for_slider_blocking(self):
        """Slider blocked by enemy same-line move: context vs inline match."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=7)
        board.add_piece(rook)
        board.add_piece(enemy_rook)

        # Enemy rook moving left along the same rank
        enemy_move = Move(
            piece_id=enemy_rook.id,
            path=[(4.0, 7.0), (4.0, 6.0), (4.0, 5.0)],
            start_tick=0,
        )
        active_moves = [enemy_move]

        # Without context (inline computation)
        result_inline = compute_move_path(
            rook, board, 4, 5, active_moves, current_tick=0, ticks_per_square=10
        )

        # With context (precomputed)
        ctx = build_path_clear_context(1, board, active_moves, 0, 10)
        result_ctx = compute_move_path(
            rook, board, 4, 5, active_moves, current_tick=0, ticks_per_square=10,
            path_context=ctx,
        )

        assert result_inline == result_ctx

    def test_context_matches_inline_for_own_forward_blocking(self):
        """Own moving piece's forward path blocks: context vs inline match."""
        board = Board.create_empty()
        rook1 = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        rook2 = Piece.create(PieceType.ROOK, player=1, row=4, col=5)
        board.add_piece(rook1)
        board.add_piece(rook2)

        # Own rook2 moving right, forward path includes (4,6), (4,7)
        own_move = Move(
            piece_id=rook2.id,
            path=[(4.0, 5.0), (4.0, 6.0), (4.0, 7.0)],
            start_tick=0,
        )
        active_moves = [own_move]

        # Rook1 tries to reach (4,6) which is in rook2's forward path
        result_inline = compute_move_path(
            rook1, board, 4, 6, active_moves, current_tick=0, ticks_per_square=10
        )
        ctx = build_path_clear_context(1, board, active_moves, 0, 10)
        result_ctx = compute_move_path(
            rook1, board, 4, 6, active_moves, current_tick=0, ticks_per_square=10,
            path_context=ctx,
        )

        assert result_inline is None
        assert result_ctx is None

    def test_context_matches_inline_for_knight_destination(self):
        """Knight destination validity: context vs inline match."""
        board = Board.create_empty()
        knight = Piece.create(PieceType.KNIGHT, player=1, row=4, col=4)
        own_rook = Piece.create(PieceType.ROOK, player=1, row=2, col=3)
        board.add_piece(knight)
        board.add_piece(own_rook)

        # Own rook moving, forward path includes (2,3)
        own_move = Move(
            piece_id=own_rook.id,
            path=[(2.0, 3.0), (2.0, 4.0), (2.0, 5.0)],
            start_tick=0,
        )
        active_moves = [own_move]

        # Knight tries to jump to (2,5) which is in forward path
        result_inline = compute_move_path(
            knight, board, 2, 5, active_moves, current_tick=0, ticks_per_square=10
        )
        ctx = build_path_clear_context(1, board, active_moves, 0, 10)
        result_ctx = compute_move_path(
            knight, board, 2, 5, active_moves, current_tick=0, ticks_per_square=10,
            path_context=ctx,
        )

        assert result_inline == result_ctx

    def test_context_matches_inline_for_unblocked_move(self):
        """Unblocked move: context vs inline produce same valid result."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        board.add_piece(rook)

        active_moves: list[Move] = []

        result_inline = compute_move_path(
            rook, board, 4, 5, active_moves, current_tick=0, ticks_per_square=10
        )
        ctx = build_path_clear_context(1, board, active_moves, 0, 10)
        result_ctx = compute_move_path(
            rook, board, 4, 5, active_moves, current_tick=0, ticks_per_square=10,
            path_context=ctx,
        )

        assert result_inline is not None
        assert result_inline == result_ctx

    def test_context_moving_piece_ids(self):
        """Verify moving_piece_ids is built correctly."""
        board = Board.create_empty()
        rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        enemy = Piece.create(PieceType.QUEEN, player=2, row=0, col=0)
        board.add_piece(rook)
        board.add_piece(enemy)

        move1 = Move(piece_id=rook.id, path=[(4.0, 0.0), (4.0, 1.0)], start_tick=0)
        move2 = Move(piece_id=enemy.id, path=[(0.0, 0.0), (0.0, 1.0)], start_tick=0)

        ctx = build_path_clear_context(1, board, [move1, move2], 0, 10)

        assert rook.id in ctx.moving_piece_ids
        assert enemy.id in ctx.moving_piece_ids

    def test_context_pawn_oncoming_enemy(self):
        """Pawn blocked by oncoming enemy: context vs inline match."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=6, col=4)
        enemy = Piece.create(PieceType.PAWN, player=2, row=3, col=4)
        board.add_piece(pawn)
        board.add_piece(enemy)

        enemy_move = Move(
            piece_id=enemy.id,
            path=[(3.0, 4.0), (4.0, 4.0), (5.0, 4.0)],
            start_tick=0,
        )
        active_moves = [enemy_move]

        result_inline = compute_move_path(
            pawn, board, 5, 4, active_moves, current_tick=0, ticks_per_square=10
        )
        ctx = build_path_clear_context(1, board, active_moves, 0, 10)
        result_ctx = compute_move_path(
            pawn, board, 5, 4, active_moves, current_tick=0, ticks_per_square=10,
            path_context=ctx,
        )

        assert result_inline == result_ctx

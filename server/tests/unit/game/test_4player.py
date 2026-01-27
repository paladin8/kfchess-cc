"""Tests for 4-player mode game engine functionality."""

import pytest

from kfchess.game.board import Board, BoardType
from kfchess.game.engine import GameEngine, GameEventType
from kfchess.game.moves import (
    FOUR_PLAYER_ORIENTATIONS,
    check_castling,
    compute_move_path,
    should_promote_pawn,
)
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import SPEED_CONFIGS, GameStatus, Speed, WinReason


class TestBoard4Player:
    """Tests for 4-player board creation."""

    def test_create_4player_board(self):
        """Test creating a 4-player board."""
        board = Board.create_4player()

        assert board.board_type == BoardType.FOUR_PLAYER
        assert board.width == 12
        assert board.height == 12

    def test_4player_piece_count(self):
        """Test 4-player board has correct piece count."""
        board = Board.create_4player()

        # Each player: 8 pawns + 8 back row pieces = 16 pieces
        # 4 players = 64 pieces total
        assert len(board.pieces) == 64

    def test_4player_pieces_per_player(self):
        """Test each player has 16 pieces."""
        board = Board.create_4player()

        for player in [1, 2, 3, 4]:
            player_pieces = board.get_pieces_for_player(player)
            assert len(player_pieces) == 16, f"Player {player} should have 16 pieces"

    def test_4player_each_player_has_king(self):
        """Test each player has exactly one king."""
        board = Board.create_4player()

        for player in [1, 2, 3, 4]:
            king = board.get_king(player)
            assert king is not None, f"Player {player} should have a king"
            assert king.type == PieceType.KING

    def test_4player_player_positions(self):
        """Test players are positioned correctly on the board."""
        board = Board.create_4player()

        # Player 1 (East): pieces at cols 10-11, rows 2-9
        p1_pieces = board.get_pieces_for_player(1)
        for piece in p1_pieces:
            assert 2 <= piece.row <= 9, f"P1 piece at wrong row: {piece.row}"
            assert piece.col in [10, 11], f"P1 piece at wrong col: {piece.col}"

        # Player 2 (South): pieces at rows 10-11, cols 2-9
        p2_pieces = board.get_pieces_for_player(2)
        for piece in p2_pieces:
            assert piece.row in [10, 11], f"P2 piece at wrong row: {piece.row}"
            assert 2 <= piece.col <= 9, f"P2 piece at wrong col: {piece.col}"

        # Player 3 (West): pieces at cols 0-1, rows 2-9
        p3_pieces = board.get_pieces_for_player(3)
        for piece in p3_pieces:
            assert 2 <= piece.row <= 9, f"P3 piece at wrong row: {piece.row}"
            assert piece.col in [0, 1], f"P3 piece at wrong col: {piece.col}"

        # Player 4 (North): pieces at rows 0-1, cols 2-9
        p4_pieces = board.get_pieces_for_player(4)
        for piece in p4_pieces:
            assert piece.row in [0, 1], f"P4 piece at wrong row: {piece.row}"
            assert 2 <= piece.col <= 9, f"P4 piece at wrong col: {piece.col}"

    def test_4player_corners_invalid(self):
        """Test that corners are invalid squares on 4-player board."""
        board = Board.create_4player()

        # All 4 corner 2x2 regions should be invalid
        corners = [
            # Top-left
            (0, 0), (0, 1), (1, 0), (1, 1),
            # Top-right
            (0, 10), (0, 11), (1, 10), (1, 11),
            # Bottom-left
            (10, 0), (10, 1), (11, 0), (11, 1),
            # Bottom-right
            (10, 10), (10, 11), (11, 10), (11, 11),
        ]

        for row, col in corners:
            assert not board.is_valid_square(row, col), f"Corner ({row}, {col}) should be invalid"

    def test_4player_center_valid(self):
        """Test that center squares are valid on 4-player board."""
        board = Board.create_4player()

        # Center 8x8 region should be valid
        for row in range(2, 10):
            for col in range(2, 10):
                assert board.is_valid_square(row, col), f"Center ({row}, {col}) should be valid"


class TestPawnMovement4Player:
    """Tests for pawn movement in 4-player mode."""

    def test_player1_pawn_moves_left(self):
        """Test Player 1 (East) pawns move left (decreasing col)."""
        board = Board.create_4player()
        # Get a Player 1 pawn (at col 10)
        p1_pawns = [p for p in board.get_pieces_for_player(1) if p.type == PieceType.PAWN]
        pawn = p1_pawns[0]

        # Should be able to move left (col 10 -> 9)
        path = compute_move_path(pawn, board, int(pawn.row), 9, [])
        assert path is not None, "P1 pawn should move left"

        # Should be able to move 2 squares from start
        path = compute_move_path(pawn, board, int(pawn.row), 8, [])
        assert path is not None, "P1 pawn should move 2 left from start"

    def test_player2_pawn_moves_up(self):
        """Test Player 2 (South) pawns move up (decreasing row)."""
        board = Board.create_4player()
        # Get a Player 2 pawn (at row 10)
        p2_pawns = [p for p in board.get_pieces_for_player(2) if p.type == PieceType.PAWN]
        pawn = p2_pawns[0]

        # Should be able to move up (row 10 -> 9)
        path = compute_move_path(pawn, board, 9, int(pawn.col), [])
        assert path is not None, "P2 pawn should move up"

        # Should be able to move 2 squares from start
        path = compute_move_path(pawn, board, 8, int(pawn.col), [])
        assert path is not None, "P2 pawn should move 2 up from start"

    def test_player3_pawn_moves_right(self):
        """Test Player 3 (West) pawns move right (increasing col)."""
        board = Board.create_4player()
        # Get a Player 3 pawn (at col 1)
        p3_pawns = [p for p in board.get_pieces_for_player(3) if p.type == PieceType.PAWN]
        pawn = p3_pawns[0]

        # Should be able to move right (col 1 -> 2)
        path = compute_move_path(pawn, board, int(pawn.row), 2, [])
        assert path is not None, "P3 pawn should move right"

        # Should be able to move 2 squares from start
        path = compute_move_path(pawn, board, int(pawn.row), 3, [])
        assert path is not None, "P3 pawn should move 2 right from start"

    def test_player4_pawn_moves_down(self):
        """Test Player 4 (North) pawns move down (increasing row)."""
        board = Board.create_4player()
        # Get a Player 4 pawn (at row 1)
        p4_pawns = [p for p in board.get_pieces_for_player(4) if p.type == PieceType.PAWN]
        pawn = p4_pawns[0]

        # Should be able to move down (row 1 -> 2)
        path = compute_move_path(pawn, board, 2, int(pawn.col), [])
        assert path is not None, "P4 pawn should move down"

        # Should be able to move 2 squares from start
        path = compute_move_path(pawn, board, 3, int(pawn.col), [])
        assert path is not None, "P4 pawn should move 2 down from start"

    def test_pawn_cannot_move_backward(self):
        """Test pawns cannot move backward in 4-player mode."""
        board = Board.create_4player()

        # Player 1 cannot move right (backward)
        p1_pawn = [p for p in board.get_pieces_for_player(1) if p.type == PieceType.PAWN][0]
        path = compute_move_path(p1_pawn, board, int(p1_pawn.row), 11, [])
        assert path is None, "P1 pawn should not move backward (right)"

        # Player 2 cannot move down (backward)
        p2_pawn = [p for p in board.get_pieces_for_player(2) if p.type == PieceType.PAWN][0]
        path = compute_move_path(p2_pawn, board, 11, int(p2_pawn.col), [])
        assert path is None, "P2 pawn should not move backward (down)"

    def test_pawn_diagonal_capture_4player(self):
        """Test pawn diagonal capture in 4-player mode."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)

        # Player 1 pawn at (5, 9) - already moved one square left from start
        pawn = Piece.create(PieceType.PAWN, player=1, row=5, col=9)
        # Enemy piece diagonally ahead (left and up/down)
        enemy = Piece.create(PieceType.PAWN, player=2, row=4, col=8)
        board.add_piece(pawn)
        board.add_piece(enemy)

        # Should be able to capture diagonally (forward-left + up)
        path = compute_move_path(pawn, board, 4, 8, [])
        assert path is not None, "P1 pawn should capture diagonally"


class TestPawnPromotion4Player:
    """Tests for pawn promotion in 4-player mode."""

    def test_player1_promotion_at_col2(self):
        """Test Player 1 pawn promotes at column 2."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        pawn = Piece.create(PieceType.PAWN, player=1, row=5, col=3)
        board.add_piece(pawn)

        # Not at promotion yet
        assert not should_promote_pawn(pawn, board, 5, 3)

        # At promotion column
        assert should_promote_pawn(pawn, board, 5, 2)

    def test_player2_promotion_at_row2(self):
        """Test Player 2 pawn promotes at row 2."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        pawn = Piece.create(PieceType.PAWN, player=2, row=3, col=5)
        board.add_piece(pawn)

        # Not at promotion yet
        assert not should_promote_pawn(pawn, board, 3, 5)

        # At promotion row
        assert should_promote_pawn(pawn, board, 2, 5)

    def test_player3_promotion_at_col9(self):
        """Test Player 3 pawn promotes at column 9."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        pawn = Piece.create(PieceType.PAWN, player=3, row=5, col=8)
        board.add_piece(pawn)

        # Not at promotion yet
        assert not should_promote_pawn(pawn, board, 5, 8)

        # At promotion column
        assert should_promote_pawn(pawn, board, 5, 9)

    def test_player4_promotion_at_row9(self):
        """Test Player 4 pawn promotes at row 9."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        pawn = Piece.create(PieceType.PAWN, player=4, row=8, col=5)
        board.add_piece(pawn)

        # Not at promotion yet
        assert not should_promote_pawn(pawn, board, 8, 5)

        # At promotion row
        assert should_promote_pawn(pawn, board, 9, 5)


class TestCastling4Player:
    """Tests for castling in 4-player mode."""

    def test_player2_horizontal_castling(self):
        """Test Player 2 (South) can castle horizontally."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        # Player 2 king at (11, 5), rooks at (11, 2) and (11, 9)
        king = Piece.create(PieceType.KING, player=2, row=11, col=5)
        rook_left = Piece.create(PieceType.ROOK, player=2, row=11, col=2)
        rook_right = Piece.create(PieceType.ROOK, player=2, row=11, col=9)
        board.add_piece(king)
        board.add_piece(rook_left)
        board.add_piece(rook_right)

        # Castle toward left rook
        result = check_castling(king, board, 11, 3, [])
        assert result is not None, "P2 should castle left"
        king_move, rook_move = result
        assert king_move.end_position == (11, 3)

        # Castle toward right rook
        result = check_castling(king, board, 11, 7, [])
        assert result is not None, "P2 should castle right"

    def test_player4_horizontal_castling(self):
        """Test Player 4 (North) can castle horizontally."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        # Player 4 king at (0, 4), rooks at (0, 2) and (0, 9)
        king = Piece.create(PieceType.KING, player=4, row=0, col=4)
        rook_left = Piece.create(PieceType.ROOK, player=4, row=0, col=2)
        rook_right = Piece.create(PieceType.ROOK, player=4, row=0, col=9)
        board.add_piece(king)
        board.add_piece(rook_left)
        board.add_piece(rook_right)

        # Castle toward right rook
        result = check_castling(king, board, 0, 6, [])
        assert result is not None, "P4 should castle right"

    def test_player1_vertical_castling(self):
        """Test Player 1 (East) can castle vertically."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        # Player 1 king at (5, 11), rooks at (2, 11) and (9, 11)
        king = Piece.create(PieceType.KING, player=1, row=5, col=11)
        rook_top = Piece.create(PieceType.ROOK, player=1, row=2, col=11)
        rook_bottom = Piece.create(PieceType.ROOK, player=1, row=9, col=11)
        board.add_piece(king)
        board.add_piece(rook_top)
        board.add_piece(rook_bottom)

        # Castle toward top rook (row decreases)
        result = check_castling(king, board, 3, 11, [])
        assert result is not None, "P1 should castle up"
        king_move, rook_move = result
        assert king_move.end_position == (3, 11)

        # Castle toward bottom rook (row increases)
        result = check_castling(king, board, 7, 11, [])
        assert result is not None, "P1 should castle down"

    def test_player3_vertical_castling(self):
        """Test Player 3 (West) can castle vertically."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        # Player 3 king at (5, 0), rooks at (2, 0) and (9, 0)
        king = Piece.create(PieceType.KING, player=3, row=5, col=0)
        rook_top = Piece.create(PieceType.ROOK, player=3, row=2, col=0)
        rook_bottom = Piece.create(PieceType.ROOK, player=3, row=9, col=0)
        board.add_piece(king)
        board.add_piece(rook_top)
        board.add_piece(rook_bottom)

        # Castle toward top rook
        result = check_castling(king, board, 3, 0, [])
        assert result is not None, "P3 should castle up"

        # Castle toward bottom rook
        result = check_castling(king, board, 7, 0, [])
        assert result is not None, "P3 should castle down"

    def test_castling_blocked_by_piece(self):
        """Test castling fails when path is blocked."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        king = Piece.create(PieceType.KING, player=1, row=5, col=11)
        rook = Piece.create(PieceType.ROOK, player=1, row=2, col=11)
        blocker = Piece.create(PieceType.BISHOP, player=1, row=4, col=11)
        board.add_piece(king)
        board.add_piece(rook)
        board.add_piece(blocker)

        result = check_castling(king, board, 3, 11, [])
        assert result is None, "Castling should be blocked"


class TestGameEngine4Player:
    """Tests for game engine with 4-player mode."""

    def test_create_4player_game(self):
        """Test creating a 4-player game."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )

        assert state.board.board_type == BoardType.FOUR_PLAYER
        assert len(state.players) == 4
        assert len(state.board.pieces) == 64

    def test_create_4player_game_with_2_players(self):
        """Test 4-player board can be used with 2 players."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board_type=BoardType.FOUR_PLAYER,
        )

        assert state.board.board_type == BoardType.FOUR_PLAYER
        assert len(state.players) == 2

    def test_create_4player_game_with_3_players(self):
        """Test 4-player board can be used with 3 players."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3"},
            board_type=BoardType.FOUR_PLAYER,
        )

        assert len(state.players) == 3

    def test_create_standard_game_requires_2_players(self):
        """Test standard board requires exactly 2 players."""
        with pytest.raises(ValueError):
            GameEngine.create_game(
                speed=Speed.STANDARD,
                players={1: "u:1"},
            )

        with pytest.raises(ValueError):
            GameEngine.create_game(
                speed=Speed.STANDARD,
                players={1: "u:1", 2: "u:2", 3: "u:3"},
            )

    def test_4player_game_start(self):
        """Test 4-player game starts when all ready."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )

        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)
        state, _ = GameEngine.set_player_ready(state, 3)
        state, events = GameEngine.set_player_ready(state, 4)

        assert state.status == GameStatus.PLAYING
        assert any(e.type == GameEventType.GAME_STARTED for e in events)

    def test_4player_winner_detection(self):
        """Test winner detection with 4 players."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )
        for p in [1, 2, 3, 4]:
            state, _ = GameEngine.set_player_ready(state, p)

        # No winner initially
        winner, win_reason = GameEngine.check_winner(state)
        assert winner is None
        assert win_reason is None

        # Eliminate players 2, 3, 4
        state.board.get_king(2).captured = True
        winner, _ = GameEngine.check_winner(state)
        assert winner is None  # Still 3 kings

        state.board.get_king(3).captured = True
        winner, _ = GameEngine.check_winner(state)
        assert winner is None  # Still 2 kings

        state.board.get_king(4).captured = True
        winner, win_reason = GameEngine.check_winner(state)
        assert winner == 1  # Player 1 wins
        assert win_reason == WinReason.KING_CAPTURED

    def test_4player_draw_all_kings_captured(self):
        """Test draw when all kings captured simultaneously."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )
        for p in [1, 2, 3, 4]:
            state, _ = GameEngine.set_player_ready(state, p)

        # Capture all kings
        for p in [1, 2, 3, 4]:
            state.board.get_king(p).captured = True

        winner, win_reason = GameEngine.check_winner(state)
        assert winner == 0  # Draw
        assert win_reason == WinReason.DRAW

    def test_4player_pawn_promotion_engine(self):
        """Test pawn promotion through the engine in 4-player mode."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        # Player 1 pawn about to promote (one square from col 2)
        pawn = Piece.create(PieceType.PAWN, player=1, row=5, col=3)
        king1 = Piece.create(PieceType.KING, player=1, row=5, col=11)
        king2 = Piece.create(PieceType.KING, player=2, row=11, col=5)
        board.add_piece(pawn)
        board.add_piece(king1)
        board.add_piece(king2)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Move pawn to promotion column
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 2)
        assert move is not None
        state, _ = GameEngine.apply_move(state, move)

        # Tick until move completes (1 square move)
        config = SPEED_CONFIGS[Speed.STANDARD]
        promotion_event = None
        for _ in range(config.ticks_per_square + 5):
            state, events = GameEngine.tick(state)
            for e in events:
                if e.type == GameEventType.PROMOTION:
                    promotion_event = e

        assert promotion_event is not None
        pawn_piece = state.board.get_piece_by_id(pawn.id)
        assert pawn_piece.type == PieceType.QUEEN


class TestCollisionDetection4Player:
    """Tests for collision detection in 4-player mode."""

    def test_collision_between_different_players(self):
        """Test collision detection works between any two different players."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        # Player 1 piece moving toward player 3 piece
        p1_rook = Piece.create(PieceType.ROOK, player=1, row=5, col=8)
        p3_pawn = Piece.create(PieceType.PAWN, player=3, row=5, col=4)
        king1 = Piece.create(PieceType.KING, player=1, row=2, col=11)
        king3 = Piece.create(PieceType.KING, player=3, row=5, col=0)
        board.add_piece(p1_rook)
        board.add_piece(p3_pawn)
        board.add_piece(king1)
        board.add_piece(king3)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 3: "u:3"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 3)

        # Move rook TO pawn's position (capture move)
        # Note: can't move THROUGH enemy piece, only TO it
        move = GameEngine.validate_move(state, 1, p1_rook.id, 5, 4)
        assert move is not None
        state, _ = GameEngine.apply_move(state, move)

        # Tick until collision (4 square move)
        config = SPEED_CONFIGS[Speed.STANDARD]
        capture_event = None
        for _ in range(4 * config.ticks_per_square + 10):
            state, events = GameEngine.tick(state)
            for e in events:
                if e.type == GameEventType.CAPTURE:
                    capture_event = e
                    break
            if capture_event:
                break

        assert capture_event is not None
        assert capture_event.data["captured_piece_id"] == p3_pawn.id

    def test_no_friendly_fire(self):
        """Test pieces of same player don't capture each other."""
        board = Board.create_empty(BoardType.FOUR_PLAYER)
        p1_rook = Piece.create(PieceType.ROOK, player=1, row=5, col=8)
        p1_pawn = Piece.create(PieceType.PAWN, player=1, row=5, col=6)
        king1 = Piece.create(PieceType.KING, player=1, row=2, col=11)
        king2 = Piece.create(PieceType.KING, player=2, row=11, col=5)
        board.add_piece(p1_rook)
        board.add_piece(p1_pawn)
        board.add_piece(king1)
        board.add_piece(king2)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Rook can't move through own pawn
        move = GameEngine.validate_move(state, 1, p1_rook.id, 5, 4)
        assert move is None, "Rook shouldn't move through own pawn"


class TestPlayerOrientations:
    """Tests for player orientation configuration."""

    def test_all_players_have_orientations(self):
        """Test all 4 players have orientation config."""
        for player in [1, 2, 3, 4]:
            assert player in FOUR_PLAYER_ORIENTATIONS

    def test_orientations_are_distinct(self):
        """Test each player has a unique forward direction."""
        forwards = [FOUR_PLAYER_ORIENTATIONS[p].forward for p in [1, 2, 3, 4]]
        assert len(set(forwards)) == 4, "Each player should have unique forward direction"

    def test_opposite_players_move_opposite(self):
        """Test opposite players move in opposite directions."""
        # Players 1 and 3 are opposite (East/West)
        p1_fwd = FOUR_PLAYER_ORIENTATIONS[1].forward
        p3_fwd = FOUR_PLAYER_ORIENTATIONS[3].forward
        assert p1_fwd[0] == -p3_fwd[0] and p1_fwd[1] == -p3_fwd[1], \
            "P1 and P3 should move opposite"

        # Players 2 and 4 are opposite (South/North)
        p2_fwd = FOUR_PLAYER_ORIENTATIONS[2].forward
        p4_fwd = FOUR_PLAYER_ORIENTATIONS[4].forward
        assert p2_fwd[0] == -p4_fwd[0] and p2_fwd[1] == -p4_fwd[1], \
            "P2 and P4 should move opposite"


class TestLegalMoves4Player:
    """Tests for legal move generation in 4-player mode."""

    def test_get_legal_moves_4player(self):
        """Test getting legal moves for a player in 4-player mode."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )
        for p in [1, 2, 3, 4]:
            state, _ = GameEngine.set_player_ready(state, p)

        # Each player should have legal moves
        for player in [1, 2, 3, 4]:
            moves = GameEngine.get_legal_moves(state, player)
            assert len(moves) > 0, f"Player {player} should have legal moves"

    def test_legal_moves_include_pawn_moves(self):
        """Test legal moves include pawn forward moves."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )
        for p in [1, 2, 3, 4]:
            state, _ = GameEngine.set_player_ready(state, p)

        # Player 1 pawns at col 10 should be able to move to col 9 and 8
        moves = GameEngine.get_legal_moves(state, 1)
        pawn_moves = [m for m in moves if m[0].startswith("P:1:")]
        assert len(pawn_moves) >= 16, "P1 should have pawn moves (8 pawns x 2 squares)"


class TestStateSerialization4Player:
    """Tests for state serialization in 4-player mode."""

    def test_to_dict_4player_board(self):
        """Test serialization includes 4-player board info."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board_type=BoardType.FOUR_PLAYER,
        )

        state_dict = state.to_dict()

        assert state_dict["board"]["board_type"] == "four_player"
        assert state_dict["board"]["width"] == 12
        assert state_dict["board"]["height"] == 12
        assert len(state_dict["board"]["pieces"]) == 64

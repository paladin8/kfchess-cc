"""Tests for board representation."""


from kfchess.game.board import Board, BoardType
from kfchess.game.pieces import Piece, PieceType


class TestBoard:
    """Tests for the Board class."""

    def test_create_standard_board(self):
        """Test creating a standard chess board."""
        board = Board.create_standard()

        assert board.board_type == BoardType.STANDARD
        assert board.width == 8
        assert board.height == 8
        assert len(board.pieces) == 32  # 16 pieces per player

    def test_standard_board_layout(self):
        """Test the initial piece layout."""
        board = Board.create_standard()

        # Check player 2 (black) back row
        assert board.get_piece_at(0, 0).type == PieceType.ROOK
        assert board.get_piece_at(0, 0).player == 2
        assert board.get_piece_at(0, 1).type == PieceType.KNIGHT
        assert board.get_piece_at(0, 4).type == PieceType.KING
        assert board.get_piece_at(0, 3).type == PieceType.QUEEN

        # Check player 2 (black) pawns
        for col in range(8):
            piece = board.get_piece_at(1, col)
            assert piece.type == PieceType.PAWN
            assert piece.player == 2

        # Check empty middle
        for row in range(2, 6):
            for col in range(8):
                assert board.get_piece_at(row, col) is None

        # Check player 1 (white) pawns
        for col in range(8):
            piece = board.get_piece_at(6, col)
            assert piece.type == PieceType.PAWN
            assert piece.player == 1

        # Check player 1 (white) back row
        assert board.get_piece_at(7, 0).type == PieceType.ROOK
        assert board.get_piece_at(7, 0).player == 1
        assert board.get_piece_at(7, 4).type == PieceType.KING
        assert board.get_piece_at(7, 3).type == PieceType.QUEEN

    def test_create_empty_board(self):
        """Test creating an empty board."""
        board = Board.create_empty()

        assert board.board_type == BoardType.STANDARD
        assert len(board.pieces) == 0

    def test_get_piece_by_id(self):
        """Test finding a piece by ID."""
        board = Board.create_standard()

        # Find a specific piece
        piece = board.get_piece_by_id("K:1:7:4")
        assert piece is not None
        assert piece.type == PieceType.KING
        assert piece.player == 1

        # Non-existent piece
        assert board.get_piece_by_id("X:9:9:9") is None

    def test_get_piece_at(self):
        """Test finding a piece at a position."""
        board = Board.create_standard()

        # Existing piece
        piece = board.get_piece_at(7, 4)
        assert piece is not None
        assert piece.type == PieceType.KING
        assert piece.player == 1

        # Empty square
        assert board.get_piece_at(4, 4) is None

        # Captured pieces should not be found
        piece.captured = True
        board.invalidate_position_map()
        assert board.get_piece_at(7, 4) is None

    def test_get_pieces_for_player(self):
        """Test getting all pieces for a player."""
        board = Board.create_standard()

        player1_pieces = board.get_pieces_for_player(1)
        player2_pieces = board.get_pieces_for_player(2)

        assert len(player1_pieces) == 16
        assert len(player2_pieces) == 16

        for piece in player1_pieces:
            assert piece.player == 1

        # Test with captured pieces
        board.pieces[0].captured = True  # Capture a black rook
        player2_pieces = board.get_pieces_for_player(2)
        assert len(player2_pieces) == 15

    def test_get_king(self):
        """Test finding a player's king."""
        board = Board.create_standard()

        king1 = board.get_king(1)
        king2 = board.get_king(2)

        assert king1 is not None
        assert king1.type == PieceType.KING
        assert king1.player == 1
        assert king1.grid_position == (7, 4)

        assert king2 is not None
        assert king2.player == 2
        assert king2.grid_position == (0, 4)

        # Test with captured king
        king1.captured = True
        board.invalidate_position_map()
        assert board.get_king(1) is None

    def test_get_active_pieces(self):
        """Test getting all uncaptured pieces."""
        board = Board.create_standard()

        active = board.get_active_pieces()
        assert len(active) == 32

        # Capture some pieces
        board.pieces[0].captured = True
        board.pieces[1].captured = True

        active = board.get_active_pieces()
        assert len(active) == 30

    def test_is_valid_square(self):
        """Test valid square checking."""
        board = Board.create_standard()

        # Valid squares
        assert board.is_valid_square(0, 0) is True
        assert board.is_valid_square(7, 7) is True
        assert board.is_valid_square(4, 4) is True

        # Invalid squares
        assert board.is_valid_square(-1, 0) is False
        assert board.is_valid_square(0, -1) is False
        assert board.is_valid_square(8, 0) is False
        assert board.is_valid_square(0, 8) is False

    def test_board_copy(self):
        """Test deep copying a board."""
        original = Board.create_standard()
        original.pieces[0].captured = True

        copy = original.copy()

        assert len(copy.pieces) == len(original.pieces)
        assert copy.pieces[0].captured == original.pieces[0].captured

        # Should be independent
        copy.pieces[1].captured = True
        assert original.pieces[1].captured is False

    def test_add_piece(self):
        """Test adding a piece to the board."""
        board = Board.create_empty()
        piece = Piece.create(PieceType.QUEEN, player=1, row=4, col=4)

        board.add_piece(piece)

        assert len(board.pieces) == 1
        assert board.get_piece_at(4, 4) == piece

    def test_remove_piece(self):
        """Test removing a piece from the board."""
        board = Board.create_standard()
        piece = board.get_piece_at(7, 4)  # White king

        result = board.remove_piece(piece.id)

        assert result is True
        assert board.get_piece_at(7, 4) is None
        assert len(board.pieces) == 31

        # Try removing non-existent piece
        result = board.remove_piece("X:9:9:9")
        assert result is False

    def test_get_piece_by_id_uses_cache(self):
        """Test that get_piece_by_id uses a cached map for O(1) lookups."""
        board = Board.create_standard()

        # First call builds the cache
        king = board.get_piece_by_id("K:1:7:4")
        assert king is not None
        assert king.type == PieceType.KING
        assert board._id_map is not None

        # Second call uses the cache
        king2 = board.get_piece_by_id("K:1:7:4")
        assert king2 is king

        # Non-existent piece returns None
        assert board.get_piece_by_id("X:9:9:9") is None

    def test_id_map_invalidated_on_add(self):
        """Test that _id_map is invalidated when a piece is added."""
        board = Board.create_empty()
        piece = Piece.create(PieceType.QUEEN, player=1, row=4, col=4)

        board.add_piece(piece)
        found = board.get_piece_by_id(piece.id)
        assert found is piece

    def test_id_map_invalidated_on_remove(self):
        """Test that _id_map is invalidated when a piece is removed."""
        board = Board.create_standard()
        king = board.get_piece_by_id("K:1:7:4")
        assert king is not None

        board.remove_piece("K:1:7:4")
        assert board.get_piece_by_id("K:1:7:4") is None

    def test_id_map_includes_captured_pieces(self):
        """Test that _id_map includes captured pieces (unlike _position_map)."""
        board = Board.create_standard()
        king = board.get_piece_by_id("K:1:7:4")
        king.captured = True
        board.invalidate_position_map()

        # position_map should not find captured king
        assert board.get_piece_at(7, 4) is None

        # id_map should still find captured king
        found = board.get_piece_by_id("K:1:7:4")
        assert found is king
        assert found.captured is True

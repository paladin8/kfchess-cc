"""Tests for StateExtractor."""


from kfchess.ai.state_extractor import AIState, PieceStatus, StateExtractor
from kfchess.game.board import Board, BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.moves import Cooldown
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import TICK_RATE_HZ, GameState, GameStatus, Speed


def _make_game(speed: Speed = Speed.STANDARD) -> GameState:
    """Create a standard game in PLAYING state."""
    state = GameEngine.create_game(
        speed=speed,
        players={1: "bot:test1", 2: "bot:test2"},
        board_type=BoardType.STANDARD,
    )
    state.status = GameStatus.PLAYING
    return state


class TestStateExtractor:
    def test_extract_initial_board(self):
        """All pieces should be IDLE on initial board."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)

        assert isinstance(ai_state, AIState)
        assert ai_state.ai_player == 1
        assert ai_state.board_width == 8
        assert ai_state.board_height == 8

        # All 32 pieces should be present (none captured)
        assert len(ai_state.pieces) == 32

        # All should be idle
        for p in ai_state.pieces:
            assert p.status == PieceStatus.IDLE
            assert p.cooldown_remaining == 0
            assert p.destination is None
            assert p.travel_direction is None

    def test_movable_pieces_initial(self):
        """Player 1 should have 16 movable pieces initially."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)
        movable = ai_state.get_movable_pieces()
        # All 16 player 1 pieces are idle
        assert len(movable) == 16

    def test_traveling_piece_shows_destination_for_own(self):
        """AI's own traveling piece should have destination set."""
        state = _make_game()
        # Move a pawn
        move = GameEngine.validate_move(state, 1, "P:1:6:4", 5, 4)
        assert move is not None
        GameEngine.apply_move(state, move)

        ai_state = StateExtractor.extract(state, ai_player=1)
        pawn = next(p for p in ai_state.pieces if p.piece.id == "P:1:6:4")
        assert pawn.status == PieceStatus.TRAVELING
        assert pawn.destination == (5, 4)

    def test_traveling_enemy_slider_hides_destination(self):
        """Enemy traveling slider should show direction but not destination."""
        state = _make_game()
        # Move player 2's pawn (a non-knight)
        move = GameEngine.validate_move(state, 2, "P:2:1:4", 2, 4)
        assert move is not None
        GameEngine.apply_move(state, move)

        # Extract from player 1's perspective
        ai_state = StateExtractor.extract(state, ai_player=1)
        pawn = next(p for p in ai_state.pieces if p.piece.id == "P:2:1:4")
        assert pawn.status == PieceStatus.TRAVELING
        assert pawn.destination is None  # Non-knight: no destination
        assert pawn.travel_direction is not None
        # Moving from row 1 to row 2 = direction (1.0, 0.0)
        assert pawn.travel_direction == (1.0, 0.0)
        assert pawn.travel_remaining_ticks > 0

    def test_cooldown_piece(self):
        """Piece on cooldown should have COOLDOWN status."""
        state = _make_game()
        state.cooldowns.append(Cooldown(piece_id="P:1:6:4", start_tick=0, duration=300))

        ai_state = StateExtractor.extract(state, ai_player=1)
        pawn = next(p for p in ai_state.pieces if p.piece.id == "P:1:6:4")
        assert pawn.status == PieceStatus.COOLDOWN
        assert pawn.cooldown_remaining == 300

    def test_enemy_king(self):
        """Should find enemy king."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)
        enemy_king = ai_state.get_enemy_king()
        assert enemy_king is not None
        assert enemy_king.piece.type == PieceType.KING
        assert enemy_king.piece.player == 2

    def test_own_king(self):
        """Should find own king."""
        state = _make_game()
        ai_state = StateExtractor.extract(state, ai_player=1)
        own_king = ai_state.get_own_king()
        assert own_king is not None
        assert own_king.piece.type == PieceType.KING
        assert own_king.piece.player == 1

    def test_traveling_enemy_knight_exposes_destination(self):
        """Enemy traveling knight should expose destination (L-shaped path)."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KNIGHT, 2, 0, 1))
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "p1", 2: "p2"},
            board=board,
        )
        state.status = GameStatus.PLAYING

        move = GameEngine.validate_move(state, 2, "N:2:0:1", 2, 2)
        assert move is not None
        GameEngine.apply_move(state, move)

        ai_state = StateExtractor.extract(state, ai_player=1)
        knight = next(p for p in ai_state.pieces if p.piece.id == "N:2:0:1")
        assert knight.status == PieceStatus.TRAVELING
        assert knight.destination == (2, 2)
        assert knight.travel_remaining_ticks > 0

    def test_cooldown_buffer_keeps_piece_non_idle(self):
        """Piece that just came off cooldown should stay COOLDOWN with buffer."""
        state = _make_game()
        state.current_tick = 100

        # Simulate a piece that had its cooldown expire at tick 98
        pawn = state.board.get_piece_by_id("P:1:6:4")
        assert pawn is not None
        pawn.cooldown_end_tick = 98

        buffer_ticks = int(0.1 * TICK_RATE_HZ)  # 3 ticks

        # At tick 100, only 2 ticks since expiry — within buffer
        ai_state = StateExtractor.extract(
            state, ai_player=1, cooldown_buffer_ticks=buffer_ticks,
        )
        piece = next(p for p in ai_state.pieces if p.piece.id == "P:1:6:4")
        assert piece.status == PieceStatus.COOLDOWN
        assert piece not in ai_state.get_movable_pieces()

    def test_cooldown_buffer_expires(self):
        """Piece should become IDLE once buffer window passes."""
        state = _make_game()
        state.current_tick = 105

        pawn = state.board.get_piece_by_id("P:1:6:4")
        assert pawn is not None
        pawn.cooldown_end_tick = 98

        buffer_ticks = int(0.1 * TICK_RATE_HZ)  # 3 ticks

        # At tick 105, 7 ticks since expiry — well past buffer
        ai_state = StateExtractor.extract(
            state, ai_player=1, cooldown_buffer_ticks=buffer_ticks,
        )
        piece = next(p for p in ai_state.pieces if p.piece.id == "P:1:6:4")
        assert piece.status == PieceStatus.IDLE

    def test_cooldown_buffer_only_affects_ai_pieces(self):
        """Buffer should not affect enemy pieces."""
        state = _make_game()
        state.current_tick = 100

        enemy_pawn = state.board.get_piece_by_id("P:2:1:4")
        assert enemy_pawn is not None
        enemy_pawn.cooldown_end_tick = 99  # 1 tick ago, within buffer

        buffer_ticks = int(0.1 * TICK_RATE_HZ)

        ai_state = StateExtractor.extract(
            state, ai_player=1, cooldown_buffer_ticks=buffer_ticks,
        )
        piece = next(p for p in ai_state.pieces if p.piece.id == "P:2:1:4")
        assert piece.status == PieceStatus.IDLE  # Enemy, buffer doesn't apply

    def test_eliminated_player_pieces_excluded_from_enemies(self):
        """Pieces from eliminated players (king captured) should not be in enemy_pieces."""
        board = Board(pieces=[], board_type=BoardType.FOUR_PLAYER, width=12, height=12)
        # Player 1 (AI) king
        board.pieces.append(Piece.create(PieceType.KING, 1, 9, 11))
        # Player 2 king — alive
        board.pieces.append(Piece.create(PieceType.KING, 2, 11, 6))
        # Player 2 rook — should be enemy
        p2_rook = Piece.create(PieceType.ROOK, 2, 11, 0)
        board.pieces.append(p2_rook)
        # Player 3 king — captured (eliminated)
        p3_king = Piece.create(PieceType.KING, 3, 6, 0)
        p3_king.captured = True
        board.pieces.append(p3_king)
        # Player 3 rook — should NOT be enemy (eliminated player)
        p3_rook = Piece.create(PieceType.ROOK, 3, 4, 0)
        board.pieces.append(p3_rook)
        # Player 4 king — alive
        board.pieces.append(Piece.create(PieceType.KING, 4, 0, 6))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "human", 2: "bot:ai", 3: "bot:ai", 4: "bot:ai"},
            board=board,
        )
        state.status = GameStatus.PLAYING

        ai_state = StateExtractor.extract(state, ai_player=1)
        enemy_ids = {ep.piece.id for ep in ai_state.get_enemy_pieces()}

        # Player 2's rook should be an enemy
        assert p2_rook.id in enemy_ids, "Living player's pieces should be enemies"
        # Player 3's rook should NOT be an enemy (eliminated)
        assert p3_rook.id not in enemy_ids, "Eliminated player's pieces should not be enemies"
        # Player 3's rook should still be in the pieces list (for occupancy)
        all_ids = {p.piece.id for p in ai_state.pieces}
        assert p3_rook.id in all_ids, "Eliminated player's pieces should still exist for blocking"

    def test_no_buffer_without_parameter(self):
        """Without cooldown_buffer_ticks, recently expired cooldown is IDLE."""
        state = _make_game()
        state.current_tick = 100

        pawn = state.board.get_piece_by_id("P:1:6:4")
        assert pawn is not None
        pawn.cooldown_end_tick = 99  # 1 tick ago

        ai_state = StateExtractor.extract(state, ai_player=1)
        piece = next(p for p in ai_state.pieces if p.piece.id == "P:1:6:4")
        assert piece.status == PieceStatus.IDLE  # No buffer, so idle

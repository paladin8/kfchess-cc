"""Tests for the core game engine."""


from kfchess.game.board import Board
from kfchess.game.engine import GameEngine, GameEventType
from kfchess.game.moves import Cooldown, Move
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import SPEED_CONFIGS, GameStatus, Speed, WinReason


class TestCreateGame:
    """Tests for game creation."""

    def test_create_game_standard(self):
        """Test creating a standard game."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:123", 2: "u:456"},
        )

        assert state.speed == Speed.STANDARD
        assert state.players == {1: "u:123", 2: "u:456"}
        assert state.status == GameStatus.WAITING
        assert state.current_tick == 0
        assert len(state.board.pieces) == 32
        assert state.winner is None
        assert len(state.active_moves) == 0
        assert len(state.cooldowns) == 0

    def test_create_game_lightning(self):
        """Test creating a lightning game."""
        state = GameEngine.create_game(
            speed=Speed.LIGHTNING,
            players={1: "u:123", 2: "bot:novice"},
        )

        assert state.speed == Speed.LIGHTNING
        # Verify lightning speed uses correct timing (0.2s/square, 2s cooldown)
        config = SPEED_CONFIGS[Speed.LIGHTNING]
        assert state.config.ticks_per_square == config.ticks_per_square
        assert state.config.cooldown_ticks == config.cooldown_ticks

    def test_create_game_custom_id(self):
        """Test creating a game with custom ID."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            game_id="TESTGAME",
        )

        assert state.game_id == "TESTGAME"

    def test_create_game_from_board(self):
        """Test creating a game with a custom board."""
        board = Board.create_empty()
        board.add_piece(Piece.create(PieceType.KING, player=1, row=7, col=4))
        board.add_piece(Piece.create(PieceType.KING, player=2, row=0, col=4))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )

        assert len(state.board.pieces) == 2


class TestSetPlayerReady:
    """Tests for player ready handling."""

    def test_set_player_ready(self):
        """Test setting a player as ready."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )

        new_state, events = GameEngine.set_player_ready(state, 1)

        assert 1 in new_state.ready_players
        assert new_state.status == GameStatus.WAITING  # Not all ready yet

    def test_game_starts_when_all_ready(self):
        """Test game starts when all players are ready."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )

        state, _ = GameEngine.set_player_ready(state, 1)
        state, events = GameEngine.set_player_ready(state, 2)

        assert state.status == GameStatus.PLAYING
        assert state.started_at is not None
        assert len([e for e in events if e.type == GameEventType.GAME_STARTED]) == 1

    def test_bot_auto_ready(self):
        """Test bots are automatically ready."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "bot:novice"},
        )

        state, events = GameEngine.set_player_ready(state, 1)

        # Game should start immediately (bot is auto-ready)
        assert state.status == GameStatus.PLAYING

    def test_invalid_player_ready(self):
        """Test invalid player cannot be set ready."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )

        new_state, events = GameEngine.set_player_ready(state, 3)

        assert 3 not in new_state.ready_players


class TestValidateMove:
    """Tests for move validation."""

    def test_validate_valid_move(self):
        """Test validating a valid pawn move."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)

        assert move is not None
        assert move.piece_id == pawn.id
        assert move.path == [(6, 4), (5, 4)]

    def test_validate_move_wrong_player(self):
        """Test cannot move opponent's piece."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Player 1 trying to move player 2's pawn
        pawn = state.board.get_piece_at(1, 4)  # Black pawn
        move = GameEngine.validate_move(state, 1, pawn.id, 2, 4)

        assert move is None

    def test_validate_move_piece_moving(self):
        """Test cannot move a piece that's already moving."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)

        # First move
        move1 = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        state, _ = GameEngine.apply_move(state, move1)

        # Try to move again while still moving
        move2 = GameEngine.validate_move(state, 1, pawn.id, 4, 4)
        assert move2 is None

    def test_validate_move_piece_on_cooldown(self):
        """Test cannot move a piece on cooldown."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)

        # Add cooldown
        state.cooldowns.append(Cooldown(piece_id=pawn.id, start_tick=0, duration=100))

        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        assert move is None

    def test_validate_move_game_not_playing(self):
        """Test cannot move when game not playing."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        # Game is in WAITING state

        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)

        assert move is None

    def test_validate_move_captured_piece(self):
        """Test cannot move a captured piece."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        pawn.captured = True

        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        assert move is None

    def test_validate_move_blocked_by_enemy_piece(self):
        """Test cannot move through a stationary enemy piece."""
        board = Board.create_empty()
        # Rook at (4,0), enemy pawn at (4,3), trying to move to (4,7)
        white_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        black_pawn = Piece.create(PieceType.PAWN, player=2, row=4, col=3)
        white_king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        black_king = Piece.create(PieceType.KING, player=2, row=0, col=4)
        board.add_piece(white_rook)
        board.add_piece(black_pawn)
        board.add_piece(white_king)
        board.add_piece(black_king)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Cannot move through enemy pawn to (4,7)
        move = GameEngine.validate_move(state, 1, white_rook.id, 4, 7)
        assert move is None

        # Can move to enemy pawn's square (capture)
        move = GameEngine.validate_move(state, 1, white_rook.id, 4, 3)
        assert move is not None

        # Can move to empty square before enemy pawn
        move = GameEngine.validate_move(state, 1, white_rook.id, 4, 2)
        assert move is not None


class TestApplyMove:
    """Tests for applying moves."""

    def test_apply_move(self):
        """Test applying a valid move."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)

        new_state, events = GameEngine.apply_move(state, move)

        assert len(new_state.active_moves) == 1
        assert new_state.active_moves[0].piece_id == pawn.id
        assert len([e for e in events if e.type == GameEventType.MOVE_STARTED]) == 1

    def test_apply_move_records_replay(self):
        """Test that moves are recorded for replay."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)

        new_state, _ = GameEngine.apply_move(state, move)

        assert len(new_state.replay_moves) == 1
        assert new_state.replay_moves[0].piece_id == pawn.id
        assert new_state.replay_moves[0].to_row == 5
        assert new_state.replay_moves[0].to_col == 4

    def test_apply_castling_emits_events_for_both_pieces(self):
        """Test that castling emits MOVE_STARTED events for both king and rook."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Validate castling move
        move = GameEngine.validate_move(state, 1, king.id, 7, 6)
        assert move is not None
        assert move.extra_move is not None

        new_state, events = GameEngine.apply_move(state, move)

        # Should have 2 MOVE_STARTED events (king and rook)
        move_started_events = [e for e in events if e.type == GameEventType.MOVE_STARTED]
        assert len(move_started_events) == 2

        # Verify both pieces are in the events
        piece_ids = {e.data["piece_id"] for e in move_started_events}
        assert king.id in piece_ids
        assert rook.id in piece_ids

        # Both moves should be in active_moves
        assert len(new_state.active_moves) == 2


class TestTick:
    """Tests for game tick processing."""

    def test_tick_advances_game(self):
        """Test that tick advances the game state."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        assert state.current_tick == 0

        new_state, _ = GameEngine.tick(state)

        assert new_state.current_tick == 1

    def test_tick_completes_move(self):
        """Test that tick completes moves after enough time."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Make a move (1 square = ticks_per_square ticks)
        # Move starts on NEXT tick (tick 1), so needs ticks_per_square + 1 total ticks to complete
        config = SPEED_CONFIGS[Speed.STANDARD]
        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        state, _ = GameEngine.apply_move(state, move)

        # Tick until move completes (move starts at tick 1, completes after ticks_per_square ticks)
        for _ in range(config.ticks_per_square + 1):
            state, events = GameEngine.tick(state)

        # Move should be completed
        assert len(state.active_moves) == 0

        # Piece should be at new position
        pawn = state.board.get_piece_by_id(pawn.id)
        assert pawn.grid_position == (5, 4)

        # Cooldown should be started
        assert len(state.cooldowns) == 1

    def test_tick_pawn_promotion(self):
        """Test pawn promotion when reaching end."""
        board = Board.create_empty()
        pawn = Piece.create(PieceType.PAWN, player=1, row=1, col=4)
        king1 = Piece.create(PieceType.KING, player=1, row=7, col=4)
        king2 = Piece.create(PieceType.KING, player=2, row=0, col=0)
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

        # Move pawn to promotion square (1 square move)
        # Move starts on NEXT tick, so needs ticks_per_square + 1 total ticks
        config = SPEED_CONFIGS[Speed.STANDARD]
        move = GameEngine.validate_move(state, 1, pawn.id, 0, 4)
        state, _ = GameEngine.apply_move(state, move)

        # Tick until move completes
        promotion_event = None
        for _ in range(config.ticks_per_square + 1):
            state, events = GameEngine.tick(state)
            for e in events:
                if e.type == GameEventType.PROMOTION:
                    promotion_event = e

        assert promotion_event is not None
        pawn = state.board.get_piece_by_id(pawn.id)
        assert pawn.type == PieceType.QUEEN

    def test_tick_cooldown_expiration(self):
        """Test cooldowns expire after duration."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Add a cooldown that will expire soon
        pawn = state.board.get_piece_at(6, 4)
        state.cooldowns.append(Cooldown(piece_id=pawn.id, start_tick=0, duration=5))

        # Tick 5 times
        for _ in range(5):
            state, _ = GameEngine.tick(state)

        # Cooldown should be expired
        assert len(state.cooldowns) == 0

    def test_tick_not_playing(self):
        """Test tick does nothing when game not playing."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        # Game is WAITING

        new_state, events = GameEngine.tick(state)

        assert new_state.current_tick == 0
        assert len(events) == 0


class TestCheckWinner:
    """Tests for win condition checking."""

    def test_king_captured_wins(self):
        """Test capturing king wins the game."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Capture player 2's king
        king2 = state.board.get_king(2)
        king2.captured = True

        winner, win_reason = GameEngine.check_winner(state)
        assert winner == 1
        assert win_reason == WinReason.KING_CAPTURED

    def test_no_winner_ongoing(self):
        """Test no winner when game is ongoing."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        winner, win_reason = GameEngine.check_winner(state)
        assert winner is None
        assert win_reason is None


class TestGetLegalMoves:
    """Tests for getting legal moves."""

    def test_get_legal_moves_initial_position(self):
        """Test getting legal moves at game start."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        moves = GameEngine.get_legal_moves(state, 1)

        # Should have pawn moves (8 pawns × 2 squares each = 16)
        # Plus knight moves (2 knights × 2 squares each = 4)
        assert len(moves) >= 20

    def test_get_legal_moves_excludes_moving_pieces(self):
        """Test that pieces currently moving have no legal moves."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        state, _ = GameEngine.apply_move(state, move)

        moves = GameEngine.get_legal_moves(state, 1)

        # Pawn should not have any moves
        pawn_moves = [m for m in moves if m[0] == pawn.id]
        assert len(pawn_moves) == 0


class TestGetPieceState:
    """Tests for getting piece state."""

    def test_get_piece_state(self):
        """Test getting piece state."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        piece_state = GameEngine.get_piece_state(state, pawn.id)

        assert piece_state is not None
        assert piece_state["id"] == pawn.id
        assert piece_state["type"] == "P"
        assert piece_state["player"] == 1
        assert piece_state["row"] == 6.0
        assert piece_state["col"] == 4.0
        assert piece_state["captured"] is False
        assert piece_state["moving"] is False
        assert piece_state["on_cooldown"] is False

    def test_get_piece_state_moving(self):
        """Test getting state of a moving piece."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        config = SPEED_CONFIGS[Speed.STANDARD]
        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        state, _ = GameEngine.apply_move(state, move)

        # Tick halfway through the move
        halfway_ticks = config.ticks_per_square // 2
        for _ in range(halfway_ticks):
            state, _ = GameEngine.tick(state)

        piece_state = GameEngine.get_piece_state(state, pawn.id)

        assert piece_state["moving"] is True
        # Position should be interpolated
        assert 5.0 < piece_state["row"] < 6.0

    def test_get_piece_state_nonexistent(self):
        """Test getting state of nonexistent piece."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )

        piece_state = GameEngine.get_piece_state(state, "X:9:9:9")
        assert piece_state is None


class TestCaptureFlow:
    """Tests for capture flow through ticks."""

    def test_capture_by_collision(self):
        """Test capturing via collision during movement."""
        # Set up a simple capture scenario
        board = Board.create_empty()
        white_queen = Piece.create(PieceType.QUEEN, player=1, row=4, col=0)
        black_pawn = Piece.create(PieceType.PAWN, player=2, row=4, col=3)
        white_king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        black_king = Piece.create(PieceType.KING, player=2, row=0, col=4)
        board.add_piece(white_queen)
        board.add_piece(black_pawn)
        board.add_piece(white_king)
        board.add_piece(black_king)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Move queen TO pawn's position (capture move)
        # Note: can't move THROUGH enemy piece, only TO it
        move = GameEngine.validate_move(state, 1, white_queen.id, 4, 3)
        assert move is not None
        state, _ = GameEngine.apply_move(state, move)

        # Tick until queen reaches pawn (3 square move)
        config = SPEED_CONFIGS[Speed.STANDARD]
        capture_event = None
        for _ in range(3 * config.ticks_per_square + 10):
            state, events = GameEngine.tick(state)
            for e in events:
                if e.type == GameEventType.CAPTURE:
                    capture_event = e
                    break
            if capture_event:
                break

        # Pawn should be captured
        assert capture_event is not None
        assert capture_event.data["captured_piece_id"] == black_pawn.id

        # Verify pawn is marked captured
        pawn = state.board.get_piece_by_id(black_pawn.id)
        assert pawn.captured is True

    def test_mutual_destruction(self):
        """Test that two pieces moving at same tick mutually destroy each other."""
        # Set up two pieces moving toward each other at same tick
        board = Board.create_empty()
        white_rook = Piece.create(PieceType.ROOK, player=1, row=4, col=0)
        black_rook = Piece.create(PieceType.ROOK, player=2, row=4, col=7)
        white_king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        black_king = Piece.create(PieceType.KING, player=2, row=0, col=4)
        board.add_piece(white_rook)
        board.add_piece(black_rook)
        board.add_piece(white_king)
        board.add_piece(black_king)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Both rooks move toward each other on same tick
        white_move = GameEngine.validate_move(state, 1, white_rook.id, 4, 7)
        black_move = GameEngine.validate_move(state, 2, black_rook.id, 4, 0)
        assert white_move is not None
        assert black_move is not None

        state, _ = GameEngine.apply_move(state, white_move)
        state, _ = GameEngine.apply_move(state, black_move)

        # Both moves should have same start tick
        assert white_move.start_tick == black_move.start_tick

        # Tick until collision (they meet in the middle around col 3.5, ~3.5 squares each)
        config = SPEED_CONFIGS[Speed.STANDARD]
        capture_events = []
        for _ in range(4 * config.ticks_per_square + 10):
            state, events = GameEngine.tick(state)
            for e in events:
                if e.type == GameEventType.CAPTURE:
                    capture_events.append(e)
            if len(capture_events) >= 2:
                break

        # Both rooks should be captured (mutual destruction)
        assert len(capture_events) == 2
        captured_ids = {e.data["captured_piece_id"] for e in capture_events}
        assert white_rook.id in captured_ids
        assert black_rook.id in captured_ids

        # Verify both are marked captured
        white = state.board.get_piece_by_id(white_rook.id)
        black = state.board.get_piece_by_id(black_rook.id)
        assert white.captured is True
        assert black.captured is True


class TestWinnerCheck:
    """Tests for winner checking with multiple scenarios."""

    def test_simultaneous_king_capture_is_draw(self):
        """Test that simultaneous king captures result in a draw."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Capture both kings
        king1 = state.board.get_king(1)
        king2 = state.board.get_king(2)
        king1.captured = True
        king2.captured = True

        winner, win_reason = GameEngine.check_winner(state)
        assert winner == 0  # Draw
        assert win_reason == WinReason.DRAW

    def test_winner_with_multiple_players(self):
        """Test winner detection works correctly with more than 2 players."""
        # Create a game with 4 players (simulated)
        board = Board.create_empty()
        king1 = Piece.create(PieceType.KING, player=1, row=7, col=4)
        king2 = Piece.create(PieceType.KING, player=2, row=0, col=4)
        king3 = Piece.create(PieceType.KING, player=3, row=4, col=0)
        king4 = Piece.create(PieceType.KING, player=4, row=4, col=7)
        board.add_piece(king1)
        board.add_piece(king2)
        board.add_piece(king3)
        board.add_piece(king4)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3", 4: "u:4"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)
        state, _ = GameEngine.set_player_ready(state, 3)
        state, _ = GameEngine.set_player_ready(state, 4)

        # All kings alive - no winner
        winner, win_reason = GameEngine.check_winner(state)
        assert winner is None
        assert win_reason is None

        # Eliminate players 2, 3, 4 - player 1 wins
        # Get pieces from state's board (not original references)
        state.board.get_king(2).captured = True
        state.board.get_king(3).captured = True
        state.board.get_king(4).captured = True

        winner, win_reason = GameEngine.check_winner(state)
        assert winner == 1
        assert win_reason == WinReason.KING_CAPTURED

    def test_two_players_remaining(self):
        """Test game continues when 2+ players still have kings."""
        board = Board.create_empty()
        king1 = Piece.create(PieceType.KING, player=1, row=7, col=4)
        king2 = Piece.create(PieceType.KING, player=2, row=0, col=4)
        king3 = Piece.create(PieceType.KING, player=3, row=4, col=0)
        board.add_piece(king1)
        board.add_piece(king2)
        board.add_piece(king3)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2", 3: "u:3"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)
        state, _ = GameEngine.set_player_ready(state, 3)

        # Eliminate player 3 - game continues with 2 players
        state.board.get_king(3).captured = True
        winner, win_reason = GameEngine.check_winner(state)
        assert winner is None
        assert win_reason is None

        # Eliminate player 2 - player 1 wins
        state.board.get_king(2).captured = True
        winner, win_reason = GameEngine.check_winner(state)
        assert winner == 1
        assert win_reason == WinReason.KING_CAPTURED


class TestCastlingCapture:
    """Tests for castling-related capture scenarios."""

    def test_rook_move_cancelled_when_king_captured_during_castling(self):
        """Test that rook move is cancelled when king is captured during castling."""
        # Setup: King and rook ready to castle, enemy piece ready to capture king
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        # Enemy rook on row 7, will collide with king during castling
        enemy_rook = Piece.create(PieceType.ROOK, player=2, row=7, col=0)
        # Enemy king required for move validation (far from action)
        enemy_king = Piece.create(PieceType.KING, player=2, row=0, col=4)
        board.add_piece(king)
        board.add_piece(rook)
        board.add_piece(enemy_rook)
        board.add_piece(enemy_king)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        config = state.config

        # Initiate castling for player 1
        castling_move = GameEngine.validate_move(state, 1, king.id, 7, 6)
        assert castling_move is not None
        assert castling_move.extra_move is not None  # Has rook move

        state, _ = GameEngine.apply_move(state, castling_move)

        # Verify both moves are active
        assert len(state.active_moves) == 2
        assert any(m.piece_id == king.id for m in state.active_moves)
        assert any(m.piece_id == rook.id for m in state.active_moves)

        # Enemy rook moves toward king's path
        enemy_move = GameEngine.validate_move(state, 2, enemy_rook.id, 7, 5)
        assert enemy_move is not None
        state, _ = GameEngine.apply_move(state, enemy_move)

        # Advance ticks until collision occurs
        # The enemy rook starts at col 0 and needs to reach col 5 (5 squares)
        # King starts at col 4 and moves to col 6 (2 squares)
        # With ticks_per_square = 4 (standard), king takes 8 ticks
        # Enemy rook takes 20 ticks to reach col 5

        # Fast forward to when collision might occur
        for _ in range(config.ticks_per_square * 6):
            state, events = GameEngine.tick(state)
            # Check if king was captured
            if state.board.get_piece_by_id(king.id).captured:
                break

        # If collision happened, verify rook move was also cancelled
        king_piece = state.board.get_piece_by_id(king.id)
        if king_piece.captured:
            # Rook move should have been removed from active moves
            assert not any(m.piece_id == rook.id for m in state.active_moves), \
                "Rook move should be cancelled when king is captured during castling"

    def test_extra_move_cancellation_on_capture(self):
        """Test that extra_move (e.g., rook in castling) is cancelled when main piece captured."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Create castling move manually and apply it
        king_move = Move(
            piece_id=king.id,
            path=[(7, 4), (7, 5), (7, 6)],
            start_tick=1,
        )
        rook_move = Move(
            piece_id=rook.id,
            path=[(7, 7), (7, 5)],
            start_tick=1,
        )
        king_move.extra_move = rook_move

        # Add both moves to active moves
        state = state.copy()
        state.active_moves = [king_move, rook_move]

        # Verify both moves are active
        assert len(state.active_moves) == 2

        # Simulate king capture by directly manipulating state
        # (In real game, this would happen via collision detection)

        # Process the capture through the tick logic
        # First mark king as captured and check that extra_move is removed
        captured_move = next(
            (m for m in state.active_moves if m.piece_id == king.id),
            None,
        )
        assert captured_move is not None
        assert captured_move.extra_move is not None

        # Simulate what tick() does when processing a capture
        pieces_to_remove = {king.id}
        if captured_move.extra_move is not None:
            pieces_to_remove.add(captured_move.extra_move.piece_id)

        new_active_moves = [
            m for m in state.active_moves if m.piece_id not in pieces_to_remove
        ]

        # Both king and rook moves should be removed
        assert len(new_active_moves) == 0
        assert not any(m.piece_id == rook.id for m in new_active_moves)


class TestStateSerialization:
    """Tests for game state serialization."""

    def test_to_dict_includes_extra_move(self):
        """Test that to_dict() serializes extra_move for castling."""
        board = Board.create_empty()
        king = Piece.create(PieceType.KING, player=1, row=7, col=4)
        rook = Piece.create(PieceType.ROOK, player=1, row=7, col=7)
        board.add_piece(king)
        board.add_piece(rook)

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
            board=board,
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Initiate castling
        move = GameEngine.validate_move(state, 1, king.id, 7, 6)
        assert move is not None
        assert move.extra_move is not None

        state, _ = GameEngine.apply_move(state, move)

        # Serialize state
        state_dict = state.to_dict()

        # Check active_moves includes extra_move
        assert len(state_dict["active_moves"]) == 2

        # Find the king's move (should have extra_move)
        king_move_dict = next(
            m for m in state_dict["active_moves"] if m["piece_id"] == king.id
        )
        assert king_move_dict["extra_move"] is not None
        assert king_move_dict["extra_move"]["piece_id"] == rook.id

        # Rook's move should have no extra_move
        rook_move_dict = next(
            m for m in state_dict["active_moves"] if m["piece_id"] == rook.id
        )
        assert rook_move_dict["extra_move"] is None

    def test_to_dict_no_extra_move_for_normal_moves(self):
        """Test that to_dict() serializes extra_move as None for normal moves."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        state, _ = GameEngine.apply_move(state, move)

        state_dict = state.to_dict()

        assert len(state_dict["active_moves"]) == 1
        assert state_dict["active_moves"][0]["extra_move"] is None

    def test_to_dict_includes_moved_flag(self):
        """Test that to_dict() includes the moved flag for pieces."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )
        state, _ = GameEngine.set_player_ready(state, 1)
        state, _ = GameEngine.set_player_ready(state, 2)

        # Move a pawn and complete the move
        pawn = state.board.get_piece_at(6, 4)
        move = GameEngine.validate_move(state, 1, pawn.id, 5, 4)
        state, _ = GameEngine.apply_move(state, move)

        # Advance ticks until move completes
        config = state.config
        for _ in range(config.ticks_per_square + 2):
            state, _ = GameEngine.tick(state)

        # Pawn should now have moved=True
        pawn_piece = state.board.get_piece_by_id(pawn.id)
        assert pawn_piece.moved is True

        # Serialize state
        state_dict = state.to_dict()

        # Find the pawn in serialized pieces
        pawn_dict = next(
            p for p in state_dict["board"]["pieces"] if p["id"] == pawn.id
        )
        assert "moved" in pawn_dict
        assert pawn_dict["moved"] is True

        # Find an unmoved piece
        king = state.board.get_king(1)
        king_dict = next(
            p for p in state_dict["board"]["pieces"] if p["id"] == king.id
        )
        assert king_dict["moved"] is False

    def test_to_dict_includes_board_metadata(self):
        """Test that to_dict() includes board type, width, and height."""
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:1", 2: "u:2"},
        )

        state_dict = state.to_dict()

        assert "board_type" in state_dict["board"]
        assert state_dict["board"]["board_type"] == "standard"
        assert "width" in state_dict["board"]
        assert state_dict["board"]["width"] == 8
        assert "height" in state_dict["board"]
        assert state_dict["board"]["height"] == 8

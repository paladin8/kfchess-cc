"""Tests for the game service."""


from kfchess.ai.dummy import DummyAI
from kfchess.game.board import BoardType
from kfchess.game.state import SPEED_CONFIGS, GameStatus, Speed, WinReason
from kfchess.services.game_service import GameService


class TestGameService:
    """Tests for GameService."""

    def test_create_game_standard(self) -> None:
        """Test creating a standard 2-player game."""
        service = GameService()
        game_id, player_key, player_num = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        assert game_id is not None
        assert len(game_id) == 8
        assert player_key.startswith("p1_")
        assert player_num == 1

        # Verify game was stored
        state = service.get_game(game_id)
        assert state is not None
        assert state.game_id == game_id
        assert state.board.board_type == BoardType.STANDARD
        assert state.speed == Speed.STANDARD
        assert state.status == GameStatus.WAITING
        assert len(state.players) == 2

    def test_create_game_4player(self) -> None:
        """Test creating a 4-player game."""
        service = GameService()
        game_id, player_key, player_num = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.FOUR_PLAYER,
            opponent="bot:dummy",
        )

        state = service.get_game(game_id)
        assert state is not None
        assert state.board.board_type == BoardType.FOUR_PLAYER
        assert len(state.players) == 4

        # Check that 3 AI players were created
        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert len(managed.ai_players) == 3
        assert 2 in managed.ai_players
        assert 3 in managed.ai_players
        assert 4 in managed.ai_players

    def test_create_game_unique_ids(self) -> None:
        """Test that game IDs are unique."""
        service = GameService()
        ids = set()
        for _ in range(10):
            game_id, _, _ = service.create_game(
                speed=Speed.STANDARD,
                board_type=BoardType.STANDARD,
                opponent="bot:dummy",
            )
            ids.add(game_id)
        assert len(ids) == 10

    def test_validate_player_key(self) -> None:
        """Test player key validation."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Valid key
        player = service.validate_player_key(game_id, player_key)
        assert player == 1

        # Invalid key
        player = service.validate_player_key(game_id, "invalid_key")
        assert player is None

        # Invalid game
        player = service.validate_player_key("invalid_game", player_key)
        assert player is None

    def test_mark_ready_starts_game(self) -> None:
        """Test marking player ready starts the game."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Mark player 1 ready (bots are auto-ready)
        success, game_started = service.mark_ready(game_id, player_key)
        assert success is True
        assert game_started is True

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.PLAYING

    def test_make_move_invalid_key(self) -> None:
        """Test making a move with invalid key."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Try move with invalid key
        result = service.make_move(
            game_id=game_id,
            player_key="invalid_key",
            piece_id="P:1:6:0",
            to_row=5,
            to_col=0,
        )
        assert result.success is False
        assert result.error == "invalid_key"

    def test_make_move_game_not_started(self) -> None:
        """Test making a move before game starts."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Try move without starting
        result = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=5,
            to_col=0,
        )
        assert result.success is False
        assert result.error == "game_not_started"

    def test_make_valid_move(self) -> None:
        """Test making a valid move."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Make a valid pawn move
        result = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=5,
            to_col=0,
        )
        assert result.success is True
        assert result.move_data is not None
        assert result.move_data["piece_id"] == "P:1:6:0"

    def test_make_move_wrong_piece(self) -> None:
        """Test making a move with opponent's piece."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Try to move opponent's piece
        result = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:2:1:0",  # Opponent's pawn
            to_row=2,
            to_col=0,
        )
        assert result.success is False
        assert result.error == "not_your_piece"

    def test_make_invalid_move(self) -> None:
        """Test making an invalid move."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Try invalid move (pawn can't move diagonally without capture)
        result = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=5,
            to_col=1,
        )
        assert result.success is False
        assert result.error == "invalid_move"

    def test_get_legal_moves(self) -> None:
        """Test getting legal moves."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Get legal moves
        moves = service.get_legal_moves(game_id, player_key)
        assert moves is not None
        assert len(moves) > 0

        # Check structure
        for move in moves:
            assert "piece_id" in move
            assert "targets" in move
            assert len(move["targets"]) > 0

    def test_get_legal_moves_invalid_key(self) -> None:
        """Test getting legal moves with invalid key."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Get legal moves with invalid key
        moves = service.get_legal_moves(game_id, "invalid_key")
        assert moves is None

    def test_tick_advances_game(self) -> None:
        """Test that tick advances the game."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        state = service.get_game(game_id)
        assert state is not None
        initial_tick = state.current_tick

        # Tick
        updated_state, events, game_finished, _, _ = service.tick(game_id)
        assert updated_state is not None
        assert updated_state.current_tick == initial_tick + 1
        assert not game_finished

    def test_tick_nonexistent_game(self) -> None:
        """Test ticking a nonexistent game."""
        service = GameService()
        state, events, game_finished, _, _ = service.tick("nonexistent")
        assert state is None
        assert events == []
        assert not game_finished

    def test_cleanup_stale_games(self) -> None:
        """Test cleaning up stale games."""
        service = GameService()

        # Create a game
        game_id, _, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Should not be cleaned up (too recent)
        cleaned = service.cleanup_stale_games(max_age_seconds=3600)
        assert cleaned == 0
        assert game_id in service.games

        # Force cleanup with 0 max age
        cleaned = service.cleanup_stale_games(max_age_seconds=0)
        assert cleaned == 1
        assert game_id not in service.games


    def test_make_move_piece_already_moving(self) -> None:
        """Test making a move while piece is already moving."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Make first move
        result1 = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=4,
            to_col=0,
        )
        assert result1.success is True

        # Try to move same piece again while still moving
        result2 = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=3,
            to_col=0,
        )
        assert result2.success is False
        assert result2.error == "invalid_move"

    def test_make_move_piece_on_cooldown(self) -> None:
        """Test making a move while piece is on cooldown."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Start game
        service.mark_ready(game_id, player_key)

        # Make a move
        result = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=5,
            to_col=0,
        )
        assert result.success is True

        # Advance ticks until move completes
        config = SPEED_CONFIGS[Speed.STANDARD]
        for _ in range(config.ticks_per_square + 2):
            service.tick(game_id)

        # Piece should now be on cooldown
        state = service.get_game(game_id)
        assert state is not None
        assert len(state.cooldowns) > 0

        # Try to move piece on cooldown
        result2 = service.make_move(
            game_id=game_id,
            player_key=player_key,
            piece_id="P:1:6:0",
            to_row=4,
            to_col=0,
        )
        assert result2.success is False
        assert result2.error == "invalid_move"

    def test_player_id_format(self) -> None:
        """Test that player IDs are formatted correctly."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        state = service.get_game(game_id)
        assert state is not None

        # Player 1 should be user
        assert state.players[1].startswith("u:")

        # Player 2 should be bot:dummy (not bot:bot:dummy)
        assert state.players[2] == "bot:dummy"

    def test_player_id_format_with_prefixed_opponent(self) -> None:
        """Test that opponent with bot: prefix is handled correctly."""
        service = GameService()
        game_id, _, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",  # Already has bot: prefix
        )

        state = service.get_game(game_id)
        assert state is not None
        # Should NOT be "bot:bot:dummy"
        assert state.players[2] == "bot:dummy"

    def test_player_id_format_without_prefix(self) -> None:
        """Test that opponent without bot: prefix is handled correctly."""
        service = GameService()
        game_id, _, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="dummy",  # No bot: prefix
        )

        state = service.get_game(game_id)
        assert state is not None
        # Should add bot: prefix
        assert state.players[2] == "bot:dummy"


class TestDummyAI:
    """Tests for DummyAI."""

    def test_dummy_ai_probabilistic_move(self) -> None:
        """Test that dummy AI makes moves probabilistically."""
        import random

        from kfchess.game.engine import GameEngine
        from kfchess.game.state import GameStatus

        # Set seed for deterministic testing
        random.seed(42)

        ai = DummyAI()
        state = GameEngine.create_game(
            speed=Speed.STANDARD,
            players={1: "u:test", 2: "bot:dummy"},
            board_type=BoardType.STANDARD,
        )
        # Set status to PLAYING so moves can be validated
        state.status = GameStatus.PLAYING

        # With standard speed, probability is 1/40 = 2.5% per tick
        # Over many ticks, we should see some True and some False
        results = [ai.should_move(state, 2, tick) for tick in range(200)]
        assert any(results), "AI should decide to move at least once in 200 ticks"
        assert not all(results), "AI should not move every single tick"

        # Reset seed and test get_move returns valid moves
        random.seed(42)
        move = ai.get_move(state, 2)
        assert move is not None, "AI should return a valid move"
        piece_id, to_row, to_col = move
        assert isinstance(piece_id, str)
        assert isinstance(to_row, int)
        assert isinstance(to_col, int)


class TestResign:
    """Tests for GameService.resign()."""

    def _create_playing_game(
        self,
        board_type: BoardType = BoardType.STANDARD,
    ) -> tuple[GameService, str, str]:
        """Helper: create a game and start it. Returns (service, game_id, player_key)."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=board_type,
            opponent="bot:dummy",
        )
        service.mark_ready(game_id, player_key)
        return service, game_id, player_key

    def test_resign_ends_2player_game(self) -> None:
        """Resigning in a 2-player game should end the game."""
        service, game_id, _ = self._create_playing_game()

        result = service.resign(game_id, 1)
        assert result is True

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.FINISHED
        assert state.win_reason == WinReason.RESIGNATION
        # Player 2 should win when player 1 resigns
        assert state.winner == 2

    def test_resign_captures_king(self) -> None:
        """Resignation should mark the player's king as captured."""
        service, game_id, _ = self._create_playing_game()

        state = service.get_game(game_id)
        assert state is not None
        king = state.board.get_king(1)
        assert king is not None
        assert king.captured is False

        service.resign(game_id, 1)

        king = state.board.get_king(1)
        assert king is None  # get_king only returns uncaptured kings

    def test_resign_invalid_game(self) -> None:
        """Resigning from a nonexistent game should fail."""
        service = GameService()
        result = service.resign("nonexistent", 1)
        assert result is False

    def test_resign_game_not_playing(self) -> None:
        """Resigning from a game that hasn't started should fail."""
        service = GameService()
        game_id, _, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        result = service.resign(game_id, 1)
        assert result is False

    def test_resign_already_finished(self) -> None:
        """Resigning from an already-finished game should fail."""
        service, game_id, _ = self._create_playing_game()

        # First resignation ends the game
        service.resign(game_id, 1)
        # Second resignation should fail
        result = service.resign(game_id, 2)
        assert result is False

    def _create_4player_multi_human(self) -> tuple[GameService, str]:
        """Helper: create a 4P lobby game with 2 humans + 2 bots."""
        service = GameService()
        player_keys = {1: "key1", 2: "key2"}
        game_id = service.create_lobby_game(
            speed=Speed.STANDARD,
            board_type=BoardType.FOUR_PLAYER,
            player_keys=player_keys,
            ai_players_config={3: "dummy", 4: "dummy"},
        )
        return service, game_id

    def test_resign_4player_continues_game(self) -> None:
        """Resigning in 4-player should eliminate player but continue the game."""
        service, game_id = self._create_4player_multi_human()

        result = service.resign(game_id, 1)
        assert result is True

        state = service.get_game(game_id)
        assert state is not None
        # Game should still be playing (human player 2 still alive)
        assert state.status == GameStatus.PLAYING
        assert state.winner is None

        # The resigned player's king should be captured
        king = state.board.get_king(1)
        assert king is None

    def test_resign_4player_sets_force_broadcast(self) -> None:
        """4-player resignation should set force_broadcast flag."""
        service, game_id = self._create_4player_multi_human()

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert managed.force_broadcast is False

        service.resign(game_id, 1)
        assert managed.force_broadcast is True

    def test_resign_4player_last_human_ends_game(self) -> None:
        """When the last human resigns in 4-player, game should end."""
        service, game_id = self._create_4player_multi_human()

        # Resign both humans — only bots remain, game ends
        service.resign(game_id, 1)
        service.resign(game_id, 2)

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.FINISHED
        assert state.winner in (3, 4)  # Random bot wins
        assert state.win_reason == WinReason.RESIGNATION

    def test_resign_4player_all_humans_gone_ends_game(self) -> None:
        """When all humans resign in 4-player, game should end with a bot winner."""
        service, game_id = self._create_4player_multi_human()

        # Resign both human players
        service.resign(game_id, 1)
        service.resign(game_id, 2)

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.FINISHED
        assert state.winner in (3, 4)  # Random bot wins
        assert state.win_reason == WinReason.RESIGNATION

    def test_resign_4player_sole_human_ends_game(self) -> None:
        """When the only human resigns in 1H+3B 4-player, game ends immediately."""
        service, game_id, _ = self._create_playing_game(BoardType.FOUR_PLAYER)

        service.resign(game_id, 1)

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.FINISHED
        assert state.winner in (2, 3, 4)  # Random bot wins
        assert state.win_reason == WinReason.RESIGNATION


class TestOfferDraw:
    """Tests for GameService.offer_draw()."""

    def _create_playing_game_with_bot(
        self,
    ) -> tuple[GameService, str, str]:
        """Helper: create a 2P game (human vs bot) and start it."""
        service = GameService()
        game_id, player_key, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )
        service.mark_ready(game_id, player_key)
        return service, game_id, player_key

    def _create_lobby_game_2_humans(
        self,
    ) -> tuple[GameService, str]:
        """Helper: create a 2P lobby game with 2 human players."""
        service = GameService()
        player_keys = {1: "key1", 2: "key2"}
        game_id = service.create_lobby_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            player_keys=player_keys,
        )
        return service, game_id

    def test_offer_draw_succeeds(self) -> None:
        """Basic draw offer should succeed."""
        service, game_id = self._create_lobby_game_2_humans()
        success, error = service.offer_draw(game_id, 1)
        assert success is True
        assert error is None

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert 1 in managed.draw_offers

    def test_offer_draw_all_humans_accept_ends_game(self) -> None:
        """When all human players offer draw, game ends as draw."""
        service, game_id = self._create_lobby_game_2_humans()

        service.offer_draw(game_id, 1)
        service.offer_draw(game_id, 2)

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.FINISHED
        assert state.winner == 0
        assert state.win_reason == WinReason.DRAW

    def test_offer_draw_rejected_when_only_human(self) -> None:
        """Draw offer should be rejected when there are no other human players."""
        service, game_id, _ = self._create_playing_game_with_bot()
        success, error = service.offer_draw(game_id, 1)
        assert success is False
        assert error == "No other human players to agree"

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.PLAYING

    def test_offer_draw_invalid_game(self) -> None:
        """Draw offer for nonexistent game should fail."""
        service = GameService()
        success, error = service.offer_draw("nonexistent", 1)
        assert success is False
        assert error == "Game not found"

    def test_offer_draw_game_not_playing(self) -> None:
        """Draw offer before game starts should fail."""
        service = GameService()
        game_id, _, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )
        success, error = service.offer_draw(game_id, 1)
        assert success is False
        assert error == "Game is not in progress"

    def test_offer_draw_already_offered(self) -> None:
        """Offering draw twice should fail."""
        service, game_id = self._create_lobby_game_2_humans()
        service.offer_draw(game_id, 1)

        success, error = service.offer_draw(game_id, 1)
        assert success is False
        assert error == "Already offered draw"

    def test_offer_draw_ai_cannot_offer(self) -> None:
        """AI players should not be able to offer draw."""
        service, game_id, _ = self._create_playing_game_with_bot()
        success, error = service.offer_draw(game_id, 2)
        assert success is False
        assert error == "AI players cannot offer draw"

    def test_offer_draw_eliminated_player(self) -> None:
        """Eliminated player should not be able to offer draw."""
        service = GameService()
        player_keys = {1: "key1", 2: "key2", 3: "key3", 4: "key4"}
        game_id = service.create_lobby_game(
            speed=Speed.STANDARD,
            board_type=BoardType.FOUR_PLAYER,
            player_keys=player_keys,
        )

        # Eliminate player 1 via resignation
        service.resign(game_id, 1)

        success, error = service.offer_draw(game_id, 1)
        assert success is False
        assert error == "Eliminated players cannot offer draw"

    def test_offer_draw_4player_mixed_humans_and_bots(self) -> None:
        """In 4-player with 2 humans + 2 bots, both humans must offer."""
        service = GameService()
        player_keys = {1: "key1", 2: "key2"}
        game_id = service.create_lobby_game(
            speed=Speed.STANDARD,
            board_type=BoardType.FOUR_PLAYER,
            player_keys=player_keys,
            ai_players_config={3: "dummy", 4: "dummy"},
        )

        # One human offers — game should continue
        success, _ = service.offer_draw(game_id, 1)
        assert success is True

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.PLAYING

        # Second human offers — game should end as draw
        success, _ = service.offer_draw(game_id, 2)
        assert success is True

        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.FINISHED
        assert state.winner == 0
        assert state.win_reason == WinReason.DRAW

    def test_offer_draw_4player_human_eliminated_then_remaining_draw(self) -> None:
        """In 4-player with 3 humans, if one is eliminated the other 2 can draw."""
        service = GameService()
        player_keys = {1: "key1", 2: "key2", 3: "key3"}
        game_id = service.create_lobby_game(
            speed=Speed.STANDARD,
            board_type=BoardType.FOUR_PLAYER,
            player_keys=player_keys,
            ai_players_config={4: "dummy"},
        )

        # Eliminate player 3
        service.resign(game_id, 3)
        state = service.get_game(game_id)
        assert state is not None
        assert state.status == GameStatus.PLAYING

        # Remaining humans draw
        service.offer_draw(game_id, 1)
        assert state.status == GameStatus.PLAYING

        service.offer_draw(game_id, 2)
        assert state.status == GameStatus.FINISHED
        assert state.winner == 0
        assert state.win_reason == WinReason.DRAW

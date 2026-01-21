"""Game service for managing active games.

This service handles game creation, state management, and move processing.
For MVP, games are stored in-memory only.
"""

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kfchess.ai.base import AIPlayer
from kfchess.ai.dummy import DummyAI
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine, GameEvent
from kfchess.game.state import GameState, GameStatus, Speed


@dataclass
class MoveResult:
    """Result of attempting to make a move."""

    success: bool
    error: str | None = None
    message: str | None = None
    move_data: dict | None = None


@dataclass
class ManagedGame:
    """A game being managed by the service.

    Attributes:
        state: The game state
        player_keys: Map of player number to secret key
        ai_players: Map of player number to AI instance
        loop_task: The async task running the game loop
        created_at: When the game was created
        last_activity: When the game was last accessed
    """

    state: GameState
    player_keys: dict[int, str] = field(default_factory=dict)
    ai_players: dict[int, AIPlayer] = field(default_factory=dict)
    loop_task: asyncio.Task[Any] | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


def _generate_player_key(player: int) -> str:
    """Generate a secret player key."""
    return f"p{player}_{secrets.token_urlsafe(16)}"


def _generate_game_id() -> str:
    """Generate a unique game ID."""
    return secrets.token_urlsafe(6).upper()[:8]


class GameService:
    """Manages active games and their state.

    This service is responsible for:
    - Creating new games
    - Validating player keys
    - Processing moves
    - Managing game lifecycle
    """

    def __init__(self) -> None:
        """Initialize the game service."""
        self.games: dict[str, ManagedGame] = {}

    def create_game(
        self,
        speed: Speed,
        board_type: BoardType,
        opponent: str,
    ) -> tuple[str, str, int]:
        """Create a new game.

        Args:
            speed: Game speed setting
            board_type: Type of board (standard or four_player)
            opponent: Opponent type (e.g., "bot:dummy")

        Returns:
            Tuple of (game_id, player_key, player_number)
        """
        game_id = _generate_game_id()

        # Ensure unique game ID
        while game_id in self.games:
            game_id = _generate_game_id()

        # Human player is always player 1
        human_player = 1
        player_key = _generate_player_key(human_player)

        # Normalize opponent name (strip "bot:" prefix if present)
        bot_name = opponent.removeprefix("bot:")

        # Set up players based on board type
        if board_type == BoardType.STANDARD:
            players = {1: f"u:{player_key}", 2: f"bot:{bot_name}"}
            bot_players = [2]
        else:
            # 4-player mode: human is player 1, rest are bots
            players = {
                1: f"u:{player_key}",
                2: f"bot:{bot_name}",
                3: f"bot:{bot_name}",
                4: f"bot:{bot_name}",
            }
            bot_players = [2, 3, 4]

        # Create the game state
        state = GameEngine.create_game(
            speed=speed,
            players=players,
            board_type=board_type,
            game_id=game_id,
        )

        # Set up AI instances
        ai_players: dict[int, AIPlayer] = {}
        for bot_player in bot_players:
            ai_players[bot_player] = self._create_ai(bot_name)

        # Create managed game
        managed_game = ManagedGame(
            state=state,
            player_keys={human_player: player_key},
            ai_players=ai_players,
        )

        self.games[game_id] = managed_game

        return game_id, player_key, human_player

    def _create_ai(self, bot_name: str) -> AIPlayer:
        """Create an AI instance based on bot name.

        Args:
            bot_name: Name of the bot (e.g., "dummy", "random")

        Returns:
            AI player instance
        """
        if bot_name == "dummy":
            return DummyAI()
        # Default to dummy for MVP
        return DummyAI()

    def get_game(self, game_id: str) -> GameState | None:
        """Get the current game state.

        Args:
            game_id: The game ID

        Returns:
            GameState or None if not found
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return None

        managed_game.last_activity = datetime.now()
        return managed_game.state

    def get_managed_game(self, game_id: str) -> ManagedGame | None:
        """Get the managed game object.

        Args:
            game_id: The game ID

        Returns:
            ManagedGame or None if not found
        """
        managed_game = self.games.get(game_id)
        if managed_game is not None:
            managed_game.last_activity = datetime.now()
        return managed_game

    def validate_player_key(self, game_id: str, player_key: str) -> int | None:
        """Validate a player key and return the player number.

        Args:
            game_id: The game ID
            player_key: The player's secret key

        Returns:
            Player number if valid, None if invalid
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return None

        for player_num, key in managed_game.player_keys.items():
            if key == player_key:
                return player_num

        return None

    def make_move(
        self,
        game_id: str,
        player_key: str,
        piece_id: str,
        to_row: int,
        to_col: int,
    ) -> MoveResult:
        """Attempt to make a move.

        Args:
            game_id: The game ID
            player_key: The player's secret key
            piece_id: ID of the piece to move
            to_row: Destination row
            to_col: Destination column

        Returns:
            MoveResult indicating success or failure
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return MoveResult(
                success=False,
                error="game_not_found",
                message="Game not found",
            )

        # Validate player key
        player = self.validate_player_key(game_id, player_key)
        if player is None:
            return MoveResult(
                success=False,
                error="invalid_key",
                message="Invalid player key",
            )

        state = managed_game.state
        managed_game.last_activity = datetime.now()

        # Check game status
        if state.status == GameStatus.FINISHED:
            return MoveResult(
                success=False,
                error="game_over",
                message="Game is already over",
            )

        if state.status == GameStatus.WAITING:
            return MoveResult(
                success=False,
                error="game_not_started",
                message="Game has not started yet",
            )

        # Validate the move
        move = GameEngine.validate_move(state, player, piece_id, to_row, to_col)
        if move is None:
            # Determine specific error
            piece = state.board.get_piece_by_id(piece_id)
            if piece is None:
                return MoveResult(
                    success=False,
                    error="piece_not_found",
                    message="Piece not found",
                )
            if piece.player != player:
                return MoveResult(
                    success=False,
                    error="not_your_piece",
                    message="This piece belongs to another player",
                )
            if piece.captured:
                return MoveResult(
                    success=False,
                    error="piece_captured",
                    message="This piece has been captured",
                )

            return MoveResult(
                success=False,
                error="invalid_move",
                message="Invalid move",
            )

        # Apply the move
        GameEngine.apply_move(state, move)

        return MoveResult(
            success=True,
            move_data={
                "piece_id": move.piece_id,
                "path": move.path,
                "start_tick": move.start_tick,
            },
        )

    def mark_ready(self, game_id: str, player_key: str) -> tuple[bool, bool]:
        """Mark a player as ready.

        Args:
            game_id: The game ID
            player_key: The player's secret key

        Returns:
            Tuple of (success, game_started)
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return False, False

        # Validate player key
        player = self.validate_player_key(game_id, player_key)
        if player is None:
            return False, False

        state = managed_game.state
        managed_game.last_activity = datetime.now()

        if state.status != GameStatus.WAITING:
            return False, False

        _, events = GameEngine.set_player_ready(state, player)

        game_started = any(e.type.value == "game_started" for e in events)

        return True, game_started

    def tick(self, game_id: str) -> tuple[GameState | None, list[GameEvent]]:
        """Advance the game by one tick.

        Args:
            game_id: The game ID

        Returns:
            Tuple of (updated state, events) or (None, []) if game not found
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return None, []

        state = managed_game.state

        if state.status != GameStatus.PLAYING:
            return state, []

        # Process AI moves
        for player_num, ai in managed_game.ai_players.items():
            if ai.should_move(state, player_num, state.current_tick):
                move_data = ai.get_move(state, player_num)
                if move_data is not None:
                    piece_id, to_row, to_col = move_data
                    move = GameEngine.validate_move(state, player_num, piece_id, to_row, to_col)
                    if move is not None:
                        GameEngine.apply_move(state, move)

        # Advance game state
        _, events = GameEngine.tick(state)

        return state, events

    def get_legal_moves(self, game_id: str, player_key: str) -> list[dict] | None:
        """Get all legal moves for a player.

        Args:
            game_id: The game ID
            player_key: The player's secret key

        Returns:
            List of legal moves grouped by piece, or None if invalid
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return None

        player = self.validate_player_key(game_id, player_key)
        if player is None:
            return None

        state = managed_game.state

        if state.status != GameStatus.PLAYING:
            return []

        legal_moves = GameEngine.get_legal_moves(state, player)

        # Group by piece
        moves_by_piece: dict[str, list[list[int]]] = {}
        for piece_id, to_row, to_col in legal_moves:
            if piece_id not in moves_by_piece:
                moves_by_piece[piece_id] = []
            moves_by_piece[piece_id].append([to_row, to_col])

        return [
            {"piece_id": piece_id, "targets": targets}
            for piece_id, targets in moves_by_piece.items()
        ]

    def cleanup_stale_games(self, max_age_seconds: int = 3600) -> int:
        """Remove games that haven't been accessed recently.

        Args:
            max_age_seconds: Maximum age in seconds before cleanup

        Returns:
            Number of games cleaned up
        """
        now = datetime.now()
        stale_games = []

        for game_id, game in self.games.items():
            age = (now - game.last_activity).total_seconds()
            if age > max_age_seconds:
                stale_games.append(game_id)

        for game_id in stale_games:
            del self.games[game_id]

        return len(stale_games)


# Global singleton instance
_game_service: GameService | None = None


def get_game_service() -> GameService:
    """Get the global game service instance."""
    global _game_service
    if _game_service is None:
        _game_service = GameService()
    return _game_service

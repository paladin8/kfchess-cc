"""Game service for managing active games.

This service handles game creation, state management, and move processing.
Games are stored in-memory during play, and replays are saved to the database
when games finish.
"""

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kfchess.game.snapshot import GameSnapshot

from kfchess.ai.base import AIPlayer
from kfchess.ai.dummy import DummyAI
from kfchess.ai.kungfu_ai import KungFuAI
from kfchess.campaign.board_parser import parse_board_string
from kfchess.campaign.models import CampaignLevel
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine, GameEvent, GameEventType
from kfchess.game.replay import Replay
from kfchess.game.state import GameState, GameStatus, Speed, WinReason

logger = logging.getLogger(__name__)


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
        campaign_level_id: Campaign level ID if this is a campaign game
        campaign_user_id: User ID who started the campaign game
    """

    state: GameState
    player_keys: dict[int, str] = field(default_factory=dict)
    ai_players: dict[int, AIPlayer] = field(default_factory=dict)
    ai_config: dict[int, str] = field(default_factory=dict)
    loop_task: asyncio.Task[Any] | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    force_broadcast: bool = False
    resigned_piece_ids: list[str] = field(default_factory=list)
    draw_offers: set[int] = field(default_factory=set)
    campaign_level_id: int | None = None
    campaign_user_id: int | None = None
    initial_board_str: str | None = None  # Initial board string for campaign games


def _generate_player_key(player: int) -> str:
    """Generate a secret player key."""
    return f"p{player}_{secrets.token_urlsafe(16)}"


_GAME_ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_GAME_ID_LENGTH = 8


def _generate_game_id() -> str:
    """Generate a unique game ID."""
    return "".join(random.choices(_GAME_ID_ALPHABET, k=_GAME_ID_LENGTH))


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
            opponent: Opponent type (e.g., "bot:novice")

        Returns:
            Tuple of (game_id, player_key, player_number)
        """
        logger.debug(f"GameService.create_game: speed={speed}, board_type={board_type}, opponent={opponent}")

        game_id = _generate_game_id()

        # Ensure unique game ID
        while game_id in self.games:
            game_id = _generate_game_id()

        # Human player is always player 1
        human_player = 1
        player_key = _generate_player_key(human_player)

        # Normalize opponent name (strip "bot:" prefix if present)
        bot_name = opponent.removeprefix("bot:")
        logger.debug(f"Bot name: {bot_name}")

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

        logger.debug(f"Creating game state with players: {players}")

        # Create the game state
        state = GameEngine.create_game(
            speed=speed,
            players=players,
            board_type=board_type,
            game_id=game_id,
        )
        logger.debug(f"Game state created: {state.game_id}")

        # Set up AI instances
        ai_players: dict[int, AIPlayer] = {}
        ai_config: dict[int, str] = {}
        for bot_player in bot_players:
            ai_players[bot_player] = self._create_ai(bot_name, speed)
            ai_config[bot_player] = bot_name
        logger.debug(f"AI players created: {list(ai_players.keys())}")

        # Create managed game
        managed_game = ManagedGame(
            state=state,
            player_keys={human_player: player_key},
            ai_players=ai_players,
            ai_config=ai_config,
        )

        self.games[game_id] = managed_game
        logger.info(f"Game {game_id} created successfully")

        return game_id, player_key, human_player

    def create_lobby_game(
        self,
        speed: Speed,
        board_type: BoardType,
        player_keys: dict[int, str],
        player_ids: dict[int, str] | None = None,
        ai_players_config: dict[int, str] | None = None,
        game_id: str | None = None,
    ) -> str:
        """Create a game from a lobby with multiple human players.

        Args:
            speed: Game speed setting
            board_type: Type of board (standard or four_player)
            player_keys: Map of player number to pre-generated player key
            player_ids: Map of player number to player ID (e.g., "u:123", "guest:xxx")
                        Used for replay storage. If not provided, falls back to key-based IDs.
            ai_players_config: Map of player number to AI type (e.g., {2: "dummy"})
            game_id: Optional pre-generated game ID (e.g., from Redis lobby manager)

        Returns:
            The game_id
        """
        if game_id is None:
            game_id = _generate_game_id()

        # Ensure unique game ID
        while game_id in self.games:
            game_id = _generate_game_id()

        # Build players dict using proper player IDs for replay storage
        player_ids = player_ids or {}
        players: dict[int, str] = {}
        for player_num in player_keys.keys():
            # Use provided player_id if available, otherwise fall back to key-based ID
            if player_num in player_ids:
                players[player_num] = player_ids[player_num]
            else:
                # Fallback for backwards compatibility
                players[player_num] = f"u:{player_keys[player_num]}"

        ai_players_config = ai_players_config or {}
        ai_instances: dict[int, AIPlayer] = {}
        for player_num, ai_type in ai_players_config.items():
            players[player_num] = f"bot:{ai_type}"
            ai_instances[player_num] = self._create_ai(ai_type, speed)

        logger.debug(f"Creating lobby game with players: {players}")

        # Create the game state
        state = GameEngine.create_game(
            speed=speed,
            players=players,
            board_type=board_type,
            game_id=game_id,
        )

        # Auto-start the game for lobby games since players already marked ready in lobby
        # Mark all players as ready and transition to PLAYING
        for player_num in players.keys():
            GameEngine.set_player_ready(state, player_num)

        logger.debug(
            f"Lobby game {game_id} auto-started: status={state.status.value}, "
            f"ready_players={state.ready_players}"
        )

        # Create managed game with all player keys
        managed_game = ManagedGame(
            state=state,
            player_keys=dict(player_keys),  # Copy all human player keys
            ai_players=ai_instances,
            ai_config=dict(ai_players_config),
        )

        self.games[game_id] = managed_game
        logger.info(f"Lobby game {game_id} created with {len(player_keys)} human players")

        return game_id

    def create_campaign_game(
        self,
        level: CampaignLevel,
        user_id: int,
    ) -> tuple[str, str, int]:
        """Create a campaign game with a custom board.

        Args:
            level: The campaign level definition
            user_id: The user ID (for progress tracking)

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

        # Parse the board string to create custom board
        board = parse_board_string(level.board_str, level.board_type)

        # Map level speed to Speed enum
        speed = Speed(level.speed)

        # Build players dict - human player + AI opponents
        players: dict[int, str] = {1: f"u:{user_id}"}
        ai_instances: dict[int, AIPlayer] = {}
        ai_config: dict[int, str] = {}

        for p in range(2, level.player_count + 1):
            players[p] = "bot:campaign"
            ai_instances[p] = self._create_ai("campaign", speed)
            ai_config[p] = "campaign"

        # Create game with custom board
        state = GameEngine.create_game_from_board(
            speed=speed,
            players=players,
            board=board,
            game_id=game_id,
        )
        state.is_campaign = True

        # Auto-start the game (mark all players ready)
        for player_num in players.keys():
            GameEngine.set_player_ready(state, player_num)

        logger.debug(
            f"Campaign game {game_id} auto-started: status={state.status.value}, "
            f"ready_players={state.ready_players}"
        )

        # Create managed game with campaign tracking
        managed_game = ManagedGame(
            state=state,
            player_keys={human_player: player_key},
            ai_players=ai_instances,
            ai_config=ai_config,
            campaign_level_id=level.level_id,
            campaign_user_id=user_id,
            initial_board_str=level.board_str,
        )

        self.games[game_id] = managed_game
        logger.info(
            f"Campaign game {game_id} created for level {level.level_id} "
            f"by user {user_id}"
        )

        return game_id, player_key, human_player

    def restore_game(self, snapshot: "GameSnapshot") -> bool:
        """Restore a game from a Redis snapshot.

        Reconstructs a ManagedGame from snapshot data including AI instances.
        The game loop is NOT started here — it starts when a player reconnects
        via start_game_loop_if_needed().

        Args:
            snapshot: The game snapshot to restore from

        Returns:
            True if the game was restored successfully
        """
        game_id = snapshot.game_id

        if game_id in self.games:
            logger.warning(f"Game {game_id} already exists, skipping restore")
            return False

        try:
            state = GameState.from_snapshot_dict(snapshot.state)
        except Exception:
            logger.exception(f"Failed to deserialize game state for {game_id}")
            return False

        # Skip finished games (stale snapshot that wasn't cleaned up)
        if state.is_finished:
            logger.info(f"Skipping restore of finished game {game_id}")
            return False

        # Rebuild AI instances from ai_config
        ai_instances: dict[int, AIPlayer] = {}
        for player_num, ai_type in snapshot.ai_config.items():
            try:
                ai_instances[player_num] = self._create_ai(ai_type, state.speed)
            except Exception:
                logger.exception(
                    f"Failed to create AI '{ai_type}' for player {player_num} "
                    f"in game {game_id}"
                )
                return False

        managed_game = ManagedGame(
            state=state,
            player_keys=dict(snapshot.player_keys),
            ai_players=ai_instances,
            ai_config=dict(snapshot.ai_config),
            campaign_level_id=snapshot.campaign_level_id,
            campaign_user_id=snapshot.campaign_user_id,
            initial_board_str=snapshot.initial_board_str,
            resigned_piece_ids=list(snapshot.resigned_piece_ids),
            draw_offers=set(snapshot.draw_offers),
            force_broadcast=snapshot.force_broadcast,
        )

        self.games[game_id] = managed_game
        logger.info(
            f"Restored game {game_id} from snapshot "
            f"(tick={snapshot.snapshot_tick}, players={len(state.players)})"
        )
        return True

    # Difficulty names → KungFuAI levels
    _DIFFICULTY_MAP: dict[str, int] = {
        "novice": 1,
        "intermediate": 2,
        "advanced": 3,
        "campaign": 3,
    }

    def _create_ai(self, bot_name: str, speed: Speed = Speed.STANDARD) -> AIPlayer:
        """Create an AI instance based on bot name.

        Supports difficulty names (novice, intermediate, advanced, campaign)
        and the legacy "dummy" identifier.

        Args:
            bot_name: Name of the bot (e.g., "novice", "intermediate", "advanced")
            speed: Game speed, passed to AI for move timing

        Returns:
            AI player instance
        """
        if bot_name in self._DIFFICULTY_MAP:
            level = self._DIFFICULTY_MAP[bot_name]
            noise = bot_name != "campaign"
            return KungFuAI(level=level, speed=speed, noise=noise)
        if bot_name == "dummy":
            return DummyAI(speed=speed)
        # Default to novice
        return KungFuAI(level=1, speed=speed)

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

        # Apply the move (human moves reset the no-move draw timer)
        GameEngine.apply_move(state, move)
        state.last_move_tick = state.current_tick

        return MoveResult(
            success=True,
            move_data={
                "piece_id": move.piece_id,
                "path": move.path,
                "start_tick": move.start_tick,
            },
        )

    def resign(self, game_id: str, player: int) -> bool:
        """Process a player resignation.

        Marks the player's king as captured and ends the game.

        Args:
            game_id: The game ID
            player: The player number

        Returns:
            True if resignation was processed successfully
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return False

        state = managed_game.state
        if state.status != GameStatus.PLAYING:
            return False

        # Find and capture the player's king
        king = state.board.get_king(player)
        if king is None:
            return False

        king.captured = True
        state.board.invalidate_position_map()

        # Check winner (handles 2P and 4P correctly)
        winner, _ = GameEngine.check_winner(state)
        if winner is not None:
            state.winner = winner
            state.status = GameStatus.FINISHED
            state.win_reason = WinReason.RESIGNATION
        else:
            # 4-player: game continues, just this player is eliminated
            # Force broadcast so other players see the king captured immediately
            managed_game.force_broadcast = True
            managed_game.resigned_piece_ids.append(king.id)

        return True

    def offer_draw(self, game_id: str, player: int) -> tuple[bool, str | None]:
        """Process a draw offer from a player.

        Args:
            game_id: The game ID
            player: The player number

        Returns:
            Tuple of (success, error_message)
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return False, "Game not found"

        state = managed_game.state
        if state.status != GameStatus.PLAYING:
            return False, "Game is not in progress"

        # Can't offer draw if you're an AI player
        if player in managed_game.ai_players:
            return False, "AI players cannot offer draw"

        # Can't offer draw if eliminated (king captured)
        king = state.board.get_king(player)
        if king is None or king.captured:
            return False, "Eliminated players cannot offer draw"

        # Already offered
        if player in managed_game.draw_offers:
            return False, "Already offered draw"

        # Check active human players
        human_players = set(state.players.keys()) - set(managed_game.ai_players.keys())
        active_humans = set()
        for p in human_players:
            p_king = state.board.get_king(p)
            if p_king is not None and not p_king.captured:
                active_humans.add(p)

        # Need at least 2 active humans for a draw agreement
        if len(active_humans) < 2:
            return False, "No other human players to agree"

        managed_game.draw_offers.add(player)

        if managed_game.draw_offers >= active_humans:
            state.winner = 0
            state.status = GameStatus.FINISHED
            state.win_reason = WinReason.DRAW

        return True, None

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

    def tick(
        self, game_id: str
    ) -> tuple[GameState | None, list[GameEvent], bool, int, int]:
        """Advance the game by one tick.

        Args:
            game_id: The game ID

        Returns:
            Tuple of (updated state, events, game_finished, ai_ns, engine_ns).
            ai_ns and engine_ns are wall-clock nanoseconds spent in AI and
            engine processing respectively.
            Returns (None, [], False, 0, 0) if game not found.
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return None, [], False, 0, 0

        state = managed_game.state

        if state.status != GameStatus.PLAYING:
            return state, [], False, 0, 0

        # Process AI moves (shuffled to avoid move-order bias).
        # AI moves intentionally don't update last_move_tick — that
        # timer only tracks human activity for AFK draw detection.
        ai_start = time.monotonic_ns()
        ai_items = list(managed_game.ai_players.items())
        random.shuffle(ai_items)
        for player_num, ai in ai_items:
            if ai.should_move(state, player_num, state.current_tick):
                move_data = ai.get_move(state, player_num)
                if move_data is not None:
                    piece_id, to_row, to_col = move_data
                    move = GameEngine.validate_move(state, player_num, piece_id, to_row, to_col)
                    if move is not None:
                        GameEngine.apply_move(state, move)
        ai_ns = time.monotonic_ns() - ai_start

        # Advance game state
        engine_start = time.monotonic_ns()
        _, events = GameEngine.tick(state)
        engine_ns = time.monotonic_ns() - engine_start

        # Check if game just finished
        game_finished = any(
            e.type in (GameEventType.GAME_OVER, GameEventType.DRAW) for e in events
        )

        return state, events, game_finished, ai_ns, engine_ns

    def get_replay(self, game_id: str) -> Replay | None:
        """Get the replay data for a finished game.

        Args:
            game_id: The game ID

        Returns:
            Replay data or None if game not found or not finished
        """
        managed_game = self.games.get(game_id)
        if managed_game is None:
            return None

        state = managed_game.state

        if state.status != GameStatus.FINISHED:
            return None

        replay = Replay.from_game_state(state)
        # Add campaign data if this was a campaign game
        replay.campaign_level_id = managed_game.campaign_level_id
        replay.initial_board_str = managed_game.initial_board_str
        return replay

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
            # Deregister from active games DB registry (requires running event loop)
            try:
                import asyncio
                asyncio.get_running_loop()
                from kfchess.services.game_registry import deregister_game_fire_and_forget
                deregister_game_fire_and_forget(game_id)
            except RuntimeError:
                pass  # No event loop; startup/shutdown cleanup will catch it
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

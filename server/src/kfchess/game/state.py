"""Game state management for Kung Fu Chess."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from kfchess.game.board import Board
from kfchess.game.moves import Cooldown, Move


class Speed(Enum):
    """Game speed settings."""

    STANDARD = "standard"
    LIGHTNING = "lightning"


class GameStatus(Enum):
    """Game lifecycle status."""

    WAITING = "waiting"  # Waiting for players to ready up
    PLAYING = "playing"  # Game in progress
    FINISHED = "finished"  # Game has ended


@dataclass
class SpeedConfig:
    """Configuration for a game speed.

    Attributes:
        tick_period_ms: Milliseconds per tick (typically 100ms = 10 ticks/sec)
        ticks_per_square: Ticks to move one square
        cooldown_ticks: Cooldown duration after completing a move
        draw_no_move_ticks: Draw if no moves for this many ticks
        draw_no_capture_ticks: Draw if no captures for this many ticks
        min_draw_ticks: Minimum game length before draw conditions are checked
    """

    tick_period_ms: int
    ticks_per_square: int
    cooldown_ticks: int
    draw_no_move_ticks: int
    draw_no_capture_ticks: int
    min_draw_ticks: int


# Speed configurations
SPEED_CONFIGS: dict[Speed, SpeedConfig] = {
    Speed.STANDARD: SpeedConfig(
        tick_period_ms=100,  # 10 ticks per second
        ticks_per_square=10,  # 1 second per square
        cooldown_ticks=100,  # 10 second cooldown
        draw_no_move_ticks=1200,  # 2 minutes
        draw_no_capture_ticks=1800,  # 3 minutes
        min_draw_ticks=3600,  # 6 minutes minimum before draw
    ),
    Speed.LIGHTNING: SpeedConfig(
        tick_period_ms=100,  # 10 ticks per second
        ticks_per_square=2,  # 0.2 seconds per square
        cooldown_ticks=20,  # 2 second cooldown
        draw_no_move_ticks=300,  # 30 seconds
        draw_no_capture_ticks=450,  # 45 seconds
        min_draw_ticks=900,  # 90 seconds minimum before draw
    ),
}


@dataclass
class ReplayMove:
    """A move recorded for replay playback.

    Attributes:
        tick: The tick when the move was initiated
        piece_id: ID of the piece that moved
        to_row: Destination row
        to_col: Destination column
        player: Player who made the move
    """

    tick: int
    piece_id: str
    to_row: int
    to_col: int
    player: int


@dataclass
class GameState:
    """Complete state of a Kung Fu Chess game.

    Attributes:
        game_id: Unique identifier for the game
        board: Current board state
        speed: Game speed setting
        players: Map of player number to player ID (e.g., "u:123" or "bot:novice")
        active_moves: Currently active piece movements
        cooldowns: Pieces currently on cooldown
        current_tick: Current game tick count
        status: Game lifecycle status
        started_at: When the game started
        finished_at: When the game finished
        winner: Winner (0=draw, 1-4=player number, None=ongoing)
        last_move_tick: Tick of the last move made
        last_capture_tick: Tick of the last capture
        replay_moves: Recorded moves for replay
        ready_players: Set of player numbers who are ready
    """

    game_id: str
    board: Board
    speed: Speed
    players: dict[int, str]
    active_moves: list[Move] = field(default_factory=list)
    cooldowns: list[Cooldown] = field(default_factory=list)
    current_tick: int = 0
    status: GameStatus = GameStatus.WAITING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    winner: int | None = None
    last_move_tick: int = 0
    last_capture_tick: int = 0
    replay_moves: list[ReplayMove] = field(default_factory=list)
    ready_players: set[int] = field(default_factory=set)

    @property
    def config(self) -> SpeedConfig:
        """Get the speed configuration for this game."""
        return SPEED_CONFIGS[self.speed]

    @property
    def is_finished(self) -> bool:
        """Check if the game has finished."""
        return self.status == GameStatus.FINISHED

    @property
    def is_playing(self) -> bool:
        """Check if the game is in progress."""
        return self.status == GameStatus.PLAYING

    def get_player_number(self, player_id: str) -> int | None:
        """Get the player number for a player ID."""
        for num, pid in self.players.items():
            if pid == player_id:
                return num
        return None

    def copy(self) -> "GameState":
        """Create a deep copy of the game state."""
        return GameState(
            game_id=self.game_id,
            board=self.board.copy(),
            speed=self.speed,
            players=dict(self.players),
            active_moves=[
                Move(
                    piece_id=m.piece_id,
                    path=list(m.path),
                    start_tick=m.start_tick,
                    extra_move=(
                        Move(
                            piece_id=m.extra_move.piece_id,
                            path=list(m.extra_move.path),
                            start_tick=m.extra_move.start_tick,
                        )
                        if m.extra_move
                        else None
                    ),
                )
                for m in self.active_moves
            ],
            cooldowns=[
                Cooldown(piece_id=c.piece_id, start_tick=c.start_tick, duration=c.duration)
                for c in self.cooldowns
            ],
            current_tick=self.current_tick,
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            winner=self.winner,
            last_move_tick=self.last_move_tick,
            last_capture_tick=self.last_capture_tick,
            replay_moves=[
                ReplayMove(
                    tick=rm.tick,
                    piece_id=rm.piece_id,
                    to_row=rm.to_row,
                    to_col=rm.to_col,
                    player=rm.player,
                )
                for rm in self.replay_moves
            ],
            ready_players=set(self.ready_players),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize game state to a dictionary."""
        return {
            "game_id": self.game_id,
            "speed": self.speed.value,
            "players": self.players,
            "current_tick": self.current_tick,
            "status": self.status.value,
            "winner": self.winner,
            "board": {
                "board_type": self.board.board_type.value,
                "width": self.board.width,
                "height": self.board.height,
                "pieces": [
                    {
                        "id": p.id,
                        "type": p.type.value,
                        "player": p.player,
                        "row": p.row,
                        "col": p.col,
                        "captured": p.captured,
                        "moved": p.moved,
                    }
                    for p in self.board.pieces
                ],
            },
            "active_moves": [
                {
                    "piece_id": m.piece_id,
                    "path": m.path,
                    "start_tick": m.start_tick,
                    "extra_move": (
                        {
                            "piece_id": m.extra_move.piece_id,
                            "path": m.extra_move.path,
                            "start_tick": m.extra_move.start_tick,
                        }
                        if m.extra_move is not None
                        else None
                    ),
                }
                for m in self.active_moves
            ],
            "cooldowns": [
                {
                    "piece_id": c.piece_id,
                    "start_tick": c.start_tick,
                    "duration": c.duration,
                }
                for c in self.cooldowns
            ],
        }

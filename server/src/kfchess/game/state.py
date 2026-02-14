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


class WinReason(Enum):
    """Reason for game ending.

    Used to determine if a game should affect ratings.
    - KING_CAPTURED and DRAW are rated (normal game endings)
    - RESIGNATION is rated (player chose to forfeit)
    - INVALID is not rated (abandoned, cancelled, error, etc.)
    """

    KING_CAPTURED = "king_captured"  # A king was captured
    DRAW = "draw"  # Game ended in a draw (stalemate, simultaneous capture, etc.)
    RESIGNATION = "resignation"  # A player resigned
    INVALID = "invalid"  # Game ended abnormally (abandoned, cancelled, error)

    def is_rated(self) -> bool:
        """Return True if this win reason should affect ratings."""
        return self in (WinReason.KING_CAPTURED, WinReason.DRAW, WinReason.RESIGNATION)


# Global tick rate - single source of truth
# Changing this value automatically adjusts all tick-based timing
TICK_RATE_HZ: int = 30


@dataclass
class SpeedConfig:
    """Configuration for a game speed.

    Timing is defined in real-world units (seconds). Tick counts are derived
    from these values using the global TICK_RATE_HZ, making it easy to change
    the tick rate without updating individual timing values.

    Attributes:
        seconds_per_square: Time to move one square
        cooldown_seconds: Cooldown duration after completing a move
        draw_no_move_seconds: Draw if no moves for this many seconds
        draw_no_capture_seconds: Draw if no captures for this many seconds
        min_draw_seconds: Minimum game length before draw conditions are checked
    """

    seconds_per_square: float
    cooldown_seconds: float
    draw_no_move_seconds: float
    draw_no_capture_seconds: float
    min_draw_seconds: float

    @property
    def tick_rate_hz(self) -> int:
        """Get the tick rate in Hz."""
        return TICK_RATE_HZ

    @property
    def tick_period_ms(self) -> float:
        """Get milliseconds per tick."""
        return 1000.0 / TICK_RATE_HZ

    @property
    def ticks_per_square(self) -> int:
        """Get ticks to move one square."""
        return int(self.seconds_per_square * TICK_RATE_HZ)

    @property
    def cooldown_ticks(self) -> int:
        """Get cooldown duration in ticks."""
        return int(self.cooldown_seconds * TICK_RATE_HZ)

    @property
    def draw_no_move_ticks(self) -> int:
        """Get ticks before draw if no moves."""
        return int(self.draw_no_move_seconds * TICK_RATE_HZ)

    @property
    def draw_no_capture_ticks(self) -> int:
        """Get ticks before draw if no captures."""
        return int(self.draw_no_capture_seconds * TICK_RATE_HZ)

    @property
    def min_draw_ticks(self) -> int:
        """Get minimum ticks before draw conditions are checked."""
        return int(self.min_draw_seconds * TICK_RATE_HZ)


# Speed configurations - defined in real-world time units
SPEED_CONFIGS: dict[Speed, SpeedConfig] = {
    Speed.STANDARD: SpeedConfig(
        seconds_per_square=1.0,  # 1 second per square
        cooldown_seconds=10.0,  # 10 second cooldown
        draw_no_move_seconds=120.0,  # 2 minutes
        draw_no_capture_seconds=180.0,  # 3 minutes
        min_draw_seconds=360.0,  # 6 minutes minimum before draw
    ),
    Speed.LIGHTNING: SpeedConfig(
        seconds_per_square=0.2,  # 0.2 seconds per square
        cooldown_seconds=2.0,  # 2 second cooldown
        draw_no_move_seconds=30.0,  # 30 seconds
        draw_no_capture_seconds=45.0,  # 45 seconds
        min_draw_seconds=90.0,  # 90 seconds minimum before draw
    ),
}

# Campaign-specific draw timing
CAMPAIGN_DRAW_NO_MOVE_SECONDS: float = 120.0  # 2 minutes
CAMPAIGN_DRAW_NO_MOVE_TICKS: int = int(CAMPAIGN_DRAW_NO_MOVE_SECONDS * TICK_RATE_HZ)


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

    def to_dict(self) -> dict:
        """Serialize replay move to a dictionary for snapshot persistence."""
        return {
            "tick": self.tick,
            "piece_id": self.piece_id,
            "to_row": self.to_row,
            "to_col": self.to_col,
            "player": self.player,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReplayMove":
        """Deserialize replay move from a dictionary."""
        return cls(
            tick=data["tick"],
            piece_id=data["piece_id"],
            to_row=data["to_row"],
            to_col=data["to_col"],
            player=data["player"],
        )


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
        win_reason: Reason for game end (WinReason enum)
        last_move_tick: Tick of the last human move (AI moves don't reset this)
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
    win_reason: WinReason | None = None
    last_move_tick: int = 0
    last_capture_tick: int = 0
    replay_moves: list[ReplayMove] = field(default_factory=list)
    ready_players: set[int] = field(default_factory=set)
    is_campaign: bool = False

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
            win_reason=self.win_reason,
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
            is_campaign=self.is_campaign,
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
            "win_reason": self.win_reason.value if self.win_reason else None,
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

    def to_snapshot_dict(self) -> dict[str, Any]:
        """Serialize full game state for snapshot persistence.

        Unlike to_dict() (used for WebSocket protocol), this includes all fields
        needed to fully reconstruct the game state: replay_moves, ready_players,
        timestamps, etc.
        """
        return {
            "game_id": self.game_id,
            "speed": self.speed.value,
            "board_type": self.board.board_type.value,
            "board_width": self.board.width,
            "board_height": self.board.height,
            "players": {str(k): v for k, v in self.players.items()},
            "current_tick": self.current_tick,
            "status": self.status.value,
            "winner": self.winner,
            "win_reason": self.win_reason.value if self.win_reason else None,
            "ready_players": list(self.ready_players),
            "pieces": [p.to_dict() for p in self.board.pieces],
            "active_moves": [m.to_dict() for m in self.active_moves],
            "cooldowns": [c.to_dict() for c in self.cooldowns],
            "replay_moves": [rm.to_dict() for rm in self.replay_moves],
            "last_move_tick": self.last_move_tick,
            "last_capture_tick": self.last_capture_tick,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "is_campaign": self.is_campaign,
        }

    @classmethod
    def from_snapshot_dict(cls, data: dict[str, Any]) -> "GameState":
        """Deserialize full game state from a snapshot dictionary.

        Reconstructs a complete GameState from the output of to_snapshot_dict().
        """
        from kfchess.game.board import Board, BoardType
        from kfchess.game.pieces import Piece

        board_type = BoardType(data["board_type"])
        pieces = [Piece.from_dict(p) for p in data["pieces"]]
        board = Board(
            pieces=pieces,
            board_type=board_type,
            width=data.get("board_width", 8 if board_type == BoardType.STANDARD else 12),
            height=data.get("board_height", 8 if board_type == BoardType.STANDARD else 12),
        )

        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])

        finished_at = None
        if data.get("finished_at"):
            finished_at = datetime.fromisoformat(data["finished_at"])

        return cls(
            game_id=data["game_id"],
            board=board,
            speed=Speed(data["speed"]),
            players={int(k): v for k, v in data["players"].items()},
            active_moves=[Move.from_dict(m) for m in data.get("active_moves", [])],
            cooldowns=[Cooldown.from_dict(c) for c in data.get("cooldowns", [])],
            current_tick=data.get("current_tick", 0),
            status=GameStatus(data["status"]),
            started_at=started_at,
            finished_at=finished_at,
            winner=data.get("winner"),
            win_reason=WinReason(data["win_reason"]) if data.get("win_reason") else None,
            last_move_tick=data.get("last_move_tick", 0),
            last_capture_tick=data.get("last_capture_tick", 0),
            replay_moves=[ReplayMove.from_dict(rm) for rm in data.get("replay_moves", [])],
            ready_players=set(data.get("ready_players", [])),
            is_campaign=data.get("is_campaign", False),
        )

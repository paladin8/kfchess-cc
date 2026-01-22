"""Replay recording and playback for Kung Fu Chess.

This module provides:
- Replay dataclass for storing complete game replays
- Format conversion between v1 (original) and v2 (new) replay formats
- ReplayEngine for computing game state at any tick
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from kfchess.game.board import BoardType
from kfchess.game.state import GameStatus, ReplayMove, Speed

if TYPE_CHECKING:
    from kfchess.game.state import GameState

logger = logging.getLogger(__name__)


@dataclass
class Replay:
    """Complete replay data for a game.

    Attributes:
        version: Replay format version (2 for new format)
        speed: Game speed setting
        board_type: Type of board
        players: Map of player number to player ID
        moves: List of all moves in the game
        total_ticks: Total game duration in ticks
        winner: Winner (0=draw, 1-4=player number, None=unknown)
        win_reason: Reason for game end
        created_at: When the game was completed
    """

    version: int
    speed: Speed
    board_type: BoardType
    players: dict[int, str]
    moves: list[ReplayMove]
    total_ticks: int
    winner: int | None
    win_reason: str | None
    created_at: datetime | None

    @staticmethod
    def from_game_state(state: "GameState") -> "Replay":
        """Create a replay from a completed game state."""
        # Determine win reason based on game state
        win_reason = None
        if state.winner is not None:
            if state.winner == 0:
                win_reason = "draw"
            else:
                win_reason = "king_captured"

        return Replay(
            version=2,
            speed=state.speed,
            board_type=state.board.board_type,
            players=dict(state.players),
            moves=list(state.replay_moves),
            total_ticks=state.current_tick,
            winner=state.winner,
            win_reason=win_reason,
            created_at=state.finished_at,
        )

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Replay":
        """Load replay from dictionary.

        Handles both v1 (original) and v2 (new) replay formats.
        """
        version = data.get("version", 1)

        if version == 1:
            return _convert_v1_to_v2(data)
        return _parse_v2(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize replay to dictionary."""
        return {
            "version": self.version,
            "speed": self.speed.value,
            "board_type": self.board_type.value,
            "players": {str(k): v for k, v in self.players.items()},
            "moves": [
                {
                    "tick": m.tick,
                    "piece_id": m.piece_id,
                    "to_row": m.to_row,
                    "to_col": m.to_col,
                    "player": m.player,
                }
                for m in self.moves
            ],
            "total_ticks": self.total_ticks,
            "winner": self.winner,
            "win_reason": self.win_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def get_moves_at_tick(self, tick: int) -> list[ReplayMove]:
        """Get all moves that started at a specific tick."""
        return [m for m in self.moves if m.tick == tick]

    def get_moves_in_range(self, start_tick: int, end_tick: int) -> list[ReplayMove]:
        """Get all moves in a tick range (inclusive)."""
        return [m for m in self.moves if start_tick <= m.tick <= end_tick]


def _convert_v1_to_v2(data: dict[str, Any]) -> Replay:
    """Convert original replay format (v1) to new format (v2).

    V1 format (from ../kfchess/lib/replay.py):
    {
        "speed": "standard",
        "players": {"1": "player1", "2": "player2"},
        "moves": [
            {"pieceId": "P:1:6:4", "player": 1, "row": 4, "col": 4, "tick": 5},
            ...
        ],
        "ticks": 1500
    }
    """
    moves = []
    for m in data.get("moves", []):
        moves.append(
            ReplayMove(
                tick=m["tick"],
                piece_id=m["pieceId"],
                to_row=m["row"],
                to_col=m["col"],
                player=m["player"],
            )
        )

    # Parse players dict (keys may be strings in JSON)
    players_raw = data.get("players", {})
    players = {int(k): v for k, v in players_raw.items()}

    return Replay(
        version=2,
        speed=Speed(data.get("speed", "standard")),
        board_type=BoardType.STANDARD,  # Original only supported standard
        players=players,
        moves=moves,
        total_ticks=data.get("ticks", 0),
        winner=None,  # Original format didn't store winner
        win_reason=None,
        created_at=None,
    )


def _parse_v2(data: dict[str, Any]) -> Replay:
    """Parse v2 replay format."""
    moves = []
    for m in data.get("moves", []):
        moves.append(
            ReplayMove(
                tick=m["tick"],
                piece_id=m["piece_id"],
                to_row=m["to_row"],
                to_col=m["to_col"],
                player=m["player"],
            )
        )

    # Parse players dict (keys may be strings in JSON)
    players_raw = data.get("players", {})
    players = {int(k): v for k, v in players_raw.items()}

    # Parse created_at
    created_at_str = data.get("created_at")
    created_at = None
    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str)

    return Replay(
        version=2,
        speed=Speed(data.get("speed", "standard")),
        board_type=BoardType(data.get("board_type", "standard")),
        players=players,
        moves=moves,
        total_ticks=data.get("total_ticks", 0),
        winner=data.get("winner"),
        win_reason=data.get("win_reason"),
        created_at=created_at,
    )


class ReplayEngine:
    """Engine for replaying games tick-by-tick.

    This class simulates game state at any given tick by replaying moves
    from the start. It's used for server-side replay state computation.
    """

    def __init__(self, replay: Replay) -> None:
        """Initialize the replay engine.

        Args:
            replay: The replay to process
        """
        self.replay = replay

        # Pre-index moves by tick for fast lookup
        self._moves_by_tick: dict[int, list[ReplayMove]] = defaultdict(list)
        for move in replay.moves:
            self._moves_by_tick[move.tick].append(move)

    def get_state_at_tick(self, target_tick: int) -> "GameState":
        """Compute the game state at a specific tick.

        This creates a fresh game and simulates all moves up to target_tick.

        Args:
            target_tick: The tick to compute state for

        Returns:
            GameState at the specified tick
        """
        # Import here to avoid circular imports
        from kfchess.game.engine import GameEngine

        # Create initial game state
        state = GameEngine.create_game(
            speed=self.replay.speed,
            players=self.replay.players,
            board_type=self.replay.board_type,
        )
        state.status = GameStatus.PLAYING

        # Simulate all ticks up to target
        while state.current_tick < target_tick:
            # Apply any moves at this tick
            for replay_move in self._moves_by_tick.get(state.current_tick, []):
                move = GameEngine.validate_move(
                    state,
                    replay_move.player,
                    replay_move.piece_id,
                    replay_move.to_row,
                    replay_move.to_col,
                )
                if move:
                    GameEngine.apply_move(state, move)
                else:
                    # Log skipped moves - could indicate data corruption or version mismatch
                    logger.warning(
                        f"Replay move skipped at tick {state.current_tick}: "
                        f"player={replay_move.player}, piece={replay_move.piece_id}, "
                        f"to=({replay_move.to_row}, {replay_move.to_col}) - move validation failed"
                    )

            # Advance tick
            GameEngine.tick(state)

        return state

    def get_initial_state(self) -> "GameState":
        """Get the state at tick 0."""
        return self.get_state_at_tick(0)

"""WebSocket protocol message types."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ServerMessageType(Enum):
    """Types of messages sent from server to client."""

    JOINED = "joined"
    STATE = "state"
    COUNTDOWN = "countdown"
    GAME_STARTED = "game_started"
    GAME_OVER = "game_over"
    RATING_UPDATE = "rating_update"
    MOVE_REJECTED = "move_rejected"
    PONG = "pong"
    ERROR = "error"


class ClientMessageType(Enum):
    """Types of messages sent from client to server."""

    MOVE = "move"
    READY = "ready"
    PING = "ping"


# Server -> Client Messages


class JoinedMessage(BaseModel):
    """Sent when client successfully joins a game via WebSocket."""

    type: str = "joined"
    player_number: int  # 0 = spectator, 1-4 = player
    tick_rate_hz: int  # Server tick rate for client synchronization


class StateUpdateMessage(BaseModel):
    """Game state update sent when state changes.

    Note: With the state optimization, updates are only sent when the game state
    meaningfully changes (events, active moves, or cooldowns change). Clients
    should use time_since_tick for smooth interpolation between updates.
    """

    type: str = "state"
    tick: int
    pieces: list[dict[str, Any]]
    active_moves: list[dict[str, Any]]
    cooldowns: list[dict[str, Any]]
    events: list[dict[str, Any]]
    time_since_tick: float = 0.0  # Milliseconds since tick started (0 to tick_period_ms)


class CountdownMessage(BaseModel):
    """Sent during pre-game countdown (first 3 seconds)."""

    type: str = "countdown"
    seconds: int  # Seconds remaining (3, 2, 1)


class GameStartedMessage(BaseModel):
    """Sent when game starts (after countdown completes)."""

    type: str = "game_started"
    tick: int = 0


class GameOverMessage(BaseModel):
    """Sent when game ends."""

    type: str = "game_over"
    winner: int  # 0 for draw, 1-4 for player number
    reason: str  # "king_captured" | "draw_timeout" | "resignation"


class RatingChangeData(BaseModel):
    """Rating change data for a single player."""

    old_rating: int
    new_rating: int
    old_belt: str
    new_belt: str
    belt_changed: bool = False


class RatingUpdateMessage(BaseModel):
    """Sent after a ranked game to report rating changes."""

    type: str = "rating_update"
    ratings: dict[str, RatingChangeData]  # player_num (as string) -> rating change


class MoveRejectedMessage(BaseModel):
    """Sent when a move is rejected."""

    type: str = "move_rejected"
    piece_id: str
    reason: str


class PongMessage(BaseModel):
    """Response to ping."""

    type: str = "pong"


class ErrorMessage(BaseModel):
    """Error message."""

    type: str = "error"
    message: str


# Client -> Server Messages


class MoveMessage(BaseModel):
    """Request to make a move."""

    type: str = "move"
    piece_id: str
    to_row: int
    to_col: int


class ReadyMessage(BaseModel):
    """Request to mark player ready."""

    type: str = "ready"


class PingMessage(BaseModel):
    """Keepalive ping."""

    type: str = "ping"


def parse_client_message(data: dict[str, Any]) -> MoveMessage | ReadyMessage | PingMessage | None:
    """Parse a client message from JSON data.

    Args:
        data: Parsed JSON data

    Returns:
        Parsed message or None if invalid
    """
    msg_type = data.get("type")

    if msg_type == "move":
        try:
            return MoveMessage(
                piece_id=data["piece_id"],
                to_row=data["to_row"],
                to_col=data["to_col"],
            )
        except (KeyError, TypeError):
            return None

    elif msg_type == "ready":
        return ReadyMessage()

    elif msg_type == "ping":
        return PingMessage()

    return None

"""WebSocket protocol message types."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ServerMessageType(Enum):
    """Types of messages sent from server to client."""

    STATE = "state"
    GAME_STARTED = "game_started"
    GAME_OVER = "game_over"
    MOVE_REJECTED = "move_rejected"
    PONG = "pong"
    ERROR = "error"


class ClientMessageType(Enum):
    """Types of messages sent from client to server."""

    MOVE = "move"
    READY = "ready"
    PING = "ping"


# Server -> Client Messages


class StateUpdateMessage(BaseModel):
    """Game state update sent every tick."""

    type: str = "state"
    tick: int
    pieces: list[dict[str, Any]]
    active_moves: list[dict[str, Any]]
    cooldowns: list[dict[str, Any]]
    events: list[dict[str, Any]]


class GameStartedMessage(BaseModel):
    """Sent when game starts."""

    type: str = "game_started"
    tick: int = 0


class GameOverMessage(BaseModel):
    """Sent when game ends."""

    type: str = "game_over"
    winner: int  # 0 for draw, 1-4 for player number
    reason: str  # "king_captured" | "draw_timeout" | "resignation"


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

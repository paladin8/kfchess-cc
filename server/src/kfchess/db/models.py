"""Database models for Kung Fu Chess."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class GameReplay(Base):
    """Stored replay for a completed game.

    Attributes:
        id: Unique identifier (same as game_id)
        speed: Game speed setting ("standard" or "lightning")
        board_type: Type of board ("standard" or "four_player")
        players: Map of player number to player ID
        moves: List of replay moves
        total_ticks: Total game duration in ticks
        winner: Winner (0=draw, 1-4=player number, None=unknown)
        win_reason: Reason for game end (e.g., "king_captured", "draw_no_moves")
        created_at: When the game was completed
        is_public: Whether the replay is publicly viewable
    """

    __tablename__ = "game_replays"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    speed: Mapped[str] = mapped_column(String, nullable=False)
    board_type: Mapped[str] = mapped_column(String, nullable=False)
    players: Mapped[dict] = mapped_column(JSON, nullable=False)
    moves: Mapped[list] = mapped_column(JSON, nullable=False)
    total_ticks: Mapped[int] = mapped_column(Integer, nullable=False)
    winner: Mapped[int | None] = mapped_column(Integer, nullable=True)
    win_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

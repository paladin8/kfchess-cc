"""Database models for Kung Fu Chess."""

from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseOAuthAccountTable, SQLAlchemyBaseUserTable
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class OAuthAccount(SQLAlchemyBaseOAuthAccountTable[int], Base):
    """OAuth account linked to a user."""

    __tablename__ = "oauth_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class User(SQLAlchemyBaseUserTable[int], Base):
    """User model supporting both email/password and Google OAuth.

    Attributes:
        id: Unique identifier (BIGINT for legacy compatibility)
        email: User email (optional for potential future username-only accounts)
        hashed_password: Password hash (NULL for Google-only users)
        is_active: Whether the user can login
        is_verified: Whether the email has been verified
        is_superuser: Admin privileges
        username: Display name (auto-generated if not provided)
        picture_url: Profile picture URL (from Google or uploaded)
        google_id: Google OAuth identifier for legacy user lookup
        ratings: Game ratings by mode (e.g. {"standard": 1200})
        created_at: Account creation timestamp
        last_online: Last activity timestamp
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # FastAPI-Users required fields
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Application-specific fields
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    picture_url: Mapped[str | None] = mapped_column(String, nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    ratings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    last_online: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Relationship to OAuth accounts
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship("OAuthAccount", lazy="joined")


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

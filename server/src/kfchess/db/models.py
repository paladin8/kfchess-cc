"""Database models for Kung Fu Chess."""

from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseOAuthAccountTable, SQLAlchemyBaseUserTable
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
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


class Lobby(Base):
    """Database model for game lobbies.

    Attributes:
        id: Unique identifier
        code: Short join code (e.g., "ABC123")
        host_id: User ID of the lobby host (NULL for anonymous hosts)
        speed: Game speed ("standard" or "lightning")
        player_count: Number of players (2 or 4)
        is_public: Whether the lobby appears in public listings
        is_ranked: Whether the game affects ELO ratings
        status: Lobby lifecycle status ("waiting", "in_game", "finished")
        game_id: ID of current/last game
        created_at: When the lobby was created
        started_at: When the game started
        finished_at: When the game finished
    """

    __tablename__ = "lobbies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    host_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    speed: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    player_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_ranked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="waiting", index=True
    )
    game_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    host: Mapped["User | None"] = relationship("User", foreign_keys=[host_id])
    players: Mapped[list["LobbyPlayer"]] = relationship(
        "LobbyPlayer", back_populates="lobby", cascade="all, delete-orphan"
    )

    # Composite index for list_public_waiting() queries
    __table_args__ = (
        Index("ix_lobbies_public_waiting", "is_public", "status", "created_at"),
    )


class LobbyPlayer(Base):
    """Database model for players in a lobby.

    Attributes:
        id: Unique identifier
        lobby_id: Foreign key to the lobby
        user_id: User ID (NULL for anonymous players)
        guest_id: Guest identifier for anonymous players
        player_slot: Slot number (1-4)
        username: Display name
        is_ready: Whether the player is ready
        is_ai: Whether this is an AI player
        ai_type: AI type identifier (e.g., "bot:dummy")
        joined_at: When the player joined
    """

    __tablename__ = "lobby_players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lobby_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lobbies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    guest_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    player_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Relationships
    lobby: Mapped["Lobby"] = relationship("Lobby", back_populates="players")
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])

    # Constraints
    __table_args__ = (
        UniqueConstraint("lobby_id", "player_slot", name="uq_lobby_players_lobby_slot"),
    )


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
    tick_rate_hz: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

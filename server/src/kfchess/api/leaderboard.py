"""Leaderboard API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.auth.dependencies import get_required_user_with_dev_bypass
from kfchess.db.models import User
from kfchess.db.session import get_db_session
from kfchess.game.elo import get_belt
from kfchess.services.rating_service import get_user_rating_stats

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

VALID_MODES = {"2p_standard", "2p_lightning", "4p_standard", "4p_lightning"}


class LeaderboardEntry(BaseModel):
    """Single entry in the leaderboard."""

    rank: int
    user_id: int
    username: str
    rating: int
    belt: str
    games_played: int
    wins: int


class LeaderboardResponse(BaseModel):
    """Response for leaderboard queries."""

    mode: str
    entries: list[LeaderboardEntry]
    total_count: int


class MyRankResponse(BaseModel):
    """Response for user's own rank."""

    mode: str
    rank: int | None
    rating: int
    belt: str
    games_played: int
    wins: int
    percentile: float | None


@router.get("", response_model=LeaderboardResponse)
async def get_leaderboard(
    mode: str = Query(..., pattern="^(2p|4p)_(standard|lightning)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Annotated[AsyncSession, Depends(get_db_session)] = ...,
) -> JSONResponse:
    """Get leaderboard for a specific rating mode.

    Results are cached for 60 seconds to reduce database load.

    Args:
        mode: Rating pool (2p_standard, 2p_lightning, 4p_standard, 4p_lightning)
        limit: Max results (default: 50, max: 100)
        offset: Pagination offset
        db: Database session

    Returns:
        LeaderboardResponse with ranked entries
    """
    # Query users with ratings for this mode, ordered by rating
    # Only include users who have played at least 1 game
    query = text("""
        SELECT
            id,
            username,
            (ratings->:mode->>'rating')::int as rating,
            (ratings->:mode->>'games')::int as games_played,
            (ratings->:mode->>'wins')::int as wins
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
        ORDER BY (ratings->:mode->>'rating')::int DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query, {"mode": mode, "limit": limit, "offset": offset})
    rows = result.fetchall()

    # Get total count for pagination
    count_query = text("""
        SELECT COUNT(*)
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
    """)
    total = (await db.execute(count_query, {"mode": mode})).scalar()

    entries = [
        LeaderboardEntry(
            rank=offset + i + 1,
            user_id=row.id,
            username=row.username,
            rating=row.rating,
            belt=get_belt(row.rating),
            games_played=row.games_played,
            wins=row.wins,
        )
        for i, row in enumerate(rows)
    ]

    response = JSONResponse(
        content=LeaderboardResponse(
            mode=mode,
            entries=entries,
            total_count=total or 0,
        ).model_dump()
    )
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@router.get("/me", response_model=MyRankResponse)
async def get_my_rank(
    mode: str = Query(..., pattern="^(2p|4p)_(standard|lightning)$"),
    db: Annotated[AsyncSession, Depends(get_db_session)] = ...,
    user: Annotated[User, Depends(get_required_user_with_dev_bypass)] = ...,
) -> MyRankResponse:
    """Get the current user's rank in a specific leaderboard.

    Args:
        mode: Rating pool (required)
        db: Database session
        user: Current authenticated user

    Returns:
        MyRankResponse with user's rank and stats
    """
    # Parse mode to get player_count and speed
    prefix, speed = mode.split("_", 1)
    player_count = 2 if prefix == "2p" else 4

    stats = get_user_rating_stats(user, player_count, speed)

    if stats.games == 0:
        return MyRankResponse(
            mode=mode,
            rank=None,
            rating=stats.rating,
            belt=get_belt(stats.rating),
            games_played=0,
            wins=0,
            percentile=None,
        )

    # Count users with higher rating
    rank_query = text("""
        SELECT COUNT(*) + 1
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
          AND (ratings->:mode->>'rating')::int > :rating
    """)
    rank = (await db.execute(rank_query, {"mode": mode, "rating": stats.rating})).scalar()

    # Get total for percentile
    total_query = text("""
        SELECT COUNT(*)
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
    """)
    total = (await db.execute(total_query, {"mode": mode})).scalar()

    percentile = round((1 - (rank - 1) / total) * 100, 1) if total > 0 else None

    return MyRankResponse(
        mode=mode,
        rank=rank,
        rating=stats.rating,
        belt=get_belt(stats.rating),
        games_played=stats.games,
        wins=stats.wins,
        percentile=percentile,
    )

"""Replays API endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from kfchess.auth.dependencies import (
    get_current_user_with_dev_bypass,
    get_required_user_with_dev_bypass,
)
from kfchess.db.models import User
from kfchess.db.repositories.replay_likes import ReplayLikesRepository
from kfchess.db.repositories.replays import ReplayRepository
from kfchess.db.session import async_session_factory
from kfchess.utils.display_name import PlayerDisplay, resolve_player_info_batch

router = APIRouter(prefix="/replays", tags=["replays"])


class ReplaySummary(BaseModel):
    """Summary of a replay for listing."""

    game_id: str
    speed: str
    board_type: str
    players: dict[str, PlayerDisplay]
    total_ticks: int
    winner: int | None
    win_reason: str | None
    created_at: datetime | None
    likes: int
    user_has_liked: bool | None
    is_ranked: bool
    campaign_level_id: int | None = None


class ReplayListResponse(BaseModel):
    """Response for listing replays."""

    replays: list[ReplaySummary]
    total: int


class LikeResponse(BaseModel):
    """Response for like/unlike operations."""

    likes: int
    user_has_liked: bool


@router.get("", response_model=ReplayListResponse)
async def list_replays(
    user: Annotated[User | None, Depends(get_current_user_with_dev_bypass)],
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: Literal["recent", "top"] = Query(default="recent"),
) -> ReplayListResponse:
    """List replays with optional sorting.

    Args:
        limit: Maximum number of replays to return (1-100)
        offset: Number of replays to skip
        sort: Sort order - "recent" (default) or "top" (by likes)

    Returns:
        List of replay summaries with like counts and user's like status
    """
    async with async_session_factory() as session:
        repository = ReplayRepository(session)
        likes_repo = ReplayLikesRepository(session)

        if sort == "top":
            replays_data, total = await repository.list_top(limit=limit, offset=offset)
            replays_with_ids = [(gid, replay) for gid, replay, _ in replays_data]
            like_counts = {gid: count for gid, _, count in replays_data}
        else:
            replays_with_ids, total = await repository.list_recent(limit=limit, offset=offset)
            # Get like counts for recent replays in a single batch query
            game_ids = [gid for gid, _ in replays_with_ids]
            like_counts = await repository.get_like_counts_batch(game_ids)

        # Get user's liked status for all replays
        replay_ids = [gid for gid, _ in replays_with_ids]
        user_id = user.id if user else None
        user_likes = await likes_repo.get_likes_for_replays(replay_ids, user_id)

        # Convert all player dicts to int keys for batch resolution
        players_list = [
            {int(k): v for k, v in replay.players.items()}
            for _, replay in replays_with_ids
        ]

        # Single DB query for all replays
        resolved_list = await resolve_player_info_batch(session, players_list)

        summaries = [
            ReplaySummary(
                game_id=game_id,
                speed=replay.speed.value,
                board_type=replay.board_type.value,
                players={str(k): v for k, v in resolved.items()},
                total_ticks=replay.total_ticks,
                winner=replay.winner,
                win_reason=replay.win_reason,
                created_at=replay.created_at,
                likes=like_counts.get(game_id, 0),
                user_has_liked=user_likes.get(game_id) if user else None,
                is_ranked=replay.is_ranked,
                campaign_level_id=replay.campaign_level_id,
            )
            for (game_id, replay), resolved in zip(
                replays_with_ids, resolved_list, strict=True
            )
        ]

    return ReplayListResponse(replays=summaries, total=total)


@router.post("/{game_id}/like", response_model=LikeResponse)
async def like_replay(
    game_id: str,
    user: Annotated[User, Depends(get_required_user_with_dev_bypass)],
) -> LikeResponse:
    """Like a replay.

    Requires authentication. Idempotent - liking twice has no effect.

    Args:
        game_id: The replay ID to like

    Returns:
        Updated like count and user's like status
    """
    async with async_session_factory() as session:
        replay_repo = ReplayRepository(session)
        likes_repo = ReplayLikesRepository(session)

        # Verify replay exists
        if not await replay_repo.exists(game_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Replay not found",
            )

        await likes_repo.like(game_id, user.id)
        await session.commit()

        like_count = await replay_repo.get_like_count(game_id)

        return LikeResponse(likes=like_count, user_has_liked=True)


@router.delete("/{game_id}/like", response_model=LikeResponse)
async def unlike_replay(
    game_id: str,
    user: Annotated[User, Depends(get_required_user_with_dev_bypass)],
) -> LikeResponse:
    """Unlike a replay.

    Requires authentication. Idempotent - unliking twice has no effect.

    Args:
        game_id: The replay ID to unlike

    Returns:
        Updated like count and user's like status
    """
    async with async_session_factory() as session:
        replay_repo = ReplayRepository(session)
        likes_repo = ReplayLikesRepository(session)

        # Verify replay exists
        if not await replay_repo.exists(game_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Replay not found",
            )

        await likes_repo.unlike(game_id, user.id)
        await session.commit()

        like_count = await replay_repo.get_like_count(game_id)

        return LikeResponse(likes=like_count, user_has_liked=False)


@router.get("/{game_id}/like", response_model=LikeResponse)
async def get_like_status(
    game_id: str,
    user: Annotated[User | None, Depends(get_current_user_with_dev_bypass)],
) -> LikeResponse:
    """Get like count and user's like status for a replay.

    Args:
        game_id: The replay ID

    Returns:
        Like count and whether the current user has liked it
    """
    async with async_session_factory() as session:
        replay_repo = ReplayRepository(session)
        likes_repo = ReplayLikesRepository(session)

        if not await replay_repo.exists(game_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Replay not found",
            )

        like_count = await replay_repo.get_like_count(game_id)
        user_has_liked = False
        if user:
            user_has_liked = await likes_repo.has_liked(game_id, user.id)

        return LikeResponse(likes=like_count, user_has_liked=user_has_liked)

"""Campaign API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kfchess.auth import current_active_user, optional_current_user
from kfchess.campaign.levels import BELT_NAMES, LEVELS, MAX_BELT, get_level
from kfchess.campaign.service import CampaignService
from kfchess.db.models import User
from kfchess.db.repositories.campaign import CampaignProgressRepository
from kfchess.db.session import async_session_factory
from kfchess.drain import is_draining
from kfchess.redis.routing import register_routing
from kfchess.services.game_registry import register_game_fire_and_forget
from kfchess.services.game_service import get_game_service
from kfchess.ws.game_loop import start_game_loop_if_needed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaign", tags=["campaign"])


# Response models


class CampaignProgressResponse(BaseModel):
    """Campaign progress response."""

    levels_completed: dict[str, bool] = Field(alias="levelsCompleted")
    belts_completed: dict[str, bool] = Field(alias="beltsCompleted")
    current_belt: int = Field(alias="currentBelt")
    max_belt: int = Field(alias="maxBelt")

    model_config = {"populate_by_name": True}


class LevelResponse(BaseModel):
    """Campaign level metadata."""

    level_id: int = Field(alias="levelId")
    belt: int
    belt_name: str = Field(alias="beltName")
    title: str
    description: str
    speed: str
    player_count: int = Field(alias="playerCount")
    is_unlocked: bool = Field(alias="isUnlocked")
    is_completed: bool = Field(alias="isCompleted")

    model_config = {"populate_by_name": True}


class LevelsListResponse(BaseModel):
    """List of campaign levels."""

    levels: list[LevelResponse]


class StartGameResponse(BaseModel):
    """Response for starting a campaign game."""

    game_id: str = Field(alias="gameId")
    player_key: str = Field(alias="playerKey")
    player_number: int = Field(alias="playerNumber")

    model_config = {"populate_by_name": True}


# Helper functions


async def _get_campaign_service() -> CampaignService:
    """Create a campaign service with database session."""
    async with async_session_factory() as session:
        repo = CampaignProgressRepository(session)
        return CampaignService(repo)


# Endpoints


@router.get("/progress", response_model=CampaignProgressResponse)
async def get_progress(
    user: Annotated[User, Depends(current_active_user)],
) -> CampaignProgressResponse:
    """Get the user's campaign progress.

    Requires authentication.
    """
    async with async_session_factory() as session:
        repo = CampaignProgressRepository(session)
        service = CampaignService(repo)
        progress = await service.get_progress(user.id)

        return CampaignProgressResponse(
            levels_completed=progress.levels_completed,
            belts_completed=progress.belts_completed,
            current_belt=progress.current_belt,
            max_belt=MAX_BELT,
        )


@router.get("/progress/{user_id}", response_model=CampaignProgressResponse)
async def get_user_progress(
    user_id: int,
) -> CampaignProgressResponse:
    """Get any user's campaign progress by user ID.

    Public endpoint for viewing other users' progress.
    """
    async with async_session_factory() as session:
        repo = CampaignProgressRepository(session)
        service = CampaignService(repo)
        progress = await service.get_progress(user_id)

        return CampaignProgressResponse(
            levels_completed=progress.levels_completed,
            belts_completed=progress.belts_completed,
            current_belt=progress.current_belt,
            max_belt=MAX_BELT,
        )


@router.get("/levels", response_model=LevelsListResponse)
async def list_levels(
    user: Annotated[User | None, Depends(optional_current_user)],
) -> LevelsListResponse:
    """Get all campaign levels.

    If authenticated, includes unlock/completion status for the user.
    """
    # Get progress if user is authenticated
    progress = None
    if user:
        async with async_session_factory() as session:
            repo = CampaignProgressRepository(session)
            service = CampaignService(repo)
            progress = await service.get_progress(user.id)

    levels = []
    for level in LEVELS:
        is_unlocked = progress.is_level_unlocked(level.level_id) if progress else False
        is_completed = progress.is_level_completed(level.level_id) if progress else False

        levels.append(
            LevelResponse(
                level_id=level.level_id,
                belt=level.belt,
                belt_name=BELT_NAMES[level.belt] or "",
                title=level.title,
                description=level.description,
                speed=level.speed,
                player_count=level.player_count,
                is_unlocked=is_unlocked,
                is_completed=is_completed,
            )
        )

    return LevelsListResponse(levels=levels)


@router.get("/levels/{level_id}", response_model=LevelResponse)
async def get_level_info(
    level_id: int,
    user: Annotated[User | None, Depends(optional_current_user)],
) -> LevelResponse:
    """Get a single campaign level.

    If authenticated, includes unlock/completion status for the user.
    """
    level = get_level(level_id)
    if level is None:
        raise HTTPException(status_code=404, detail="Level not found")

    # Get progress if user is authenticated
    is_unlocked = False
    is_completed = False
    if user:
        async with async_session_factory() as session:
            repo = CampaignProgressRepository(session)
            service = CampaignService(repo)
            progress = await service.get_progress(user.id)
            is_unlocked = progress.is_level_unlocked(level_id)
            is_completed = progress.is_level_completed(level_id)

    return LevelResponse(
        level_id=level.level_id,
        belt=level.belt,
        belt_name=BELT_NAMES[level.belt] or "",
        title=level.title,
        description=level.description,
        speed=level.speed,
        player_count=level.player_count,
        is_unlocked=is_unlocked,
        is_completed=is_completed,
    )


@router.post("/levels/{level_id}/start", response_model=StartGameResponse)
async def start_level(
    level_id: int,
    user: Annotated[User, Depends(current_active_user)],
) -> StartGameResponse:
    """Start a campaign level.

    Creates a new game with the campaign board and AI opponent(s).
    Requires authentication and the level must be unlocked.
    """
    if is_draining():
        raise HTTPException(status_code=503, detail="Server is shutting down")

    # Check level exists
    level = get_level(level_id)
    if level is None:
        raise HTTPException(status_code=404, detail="Level not found")

    # Check level is unlocked
    async with async_session_factory() as session:
        repo = CampaignProgressRepository(session)
        service = CampaignService(repo)
        progress = await service.get_progress(user.id)

        if not progress.is_level_unlocked(level_id):
            logger.warning(
                f"User {user.id} attempted to start locked level {level_id}"
            )
            raise HTTPException(status_code=403, detail="Level is locked")

    # Create campaign game
    game_service = get_game_service()
    game_id, player_key, player_number = game_service.create_campaign_game(
        level=level,
        user_id=user.id,
    )

    logger.info(f"User {user.id} started campaign level {level_id}, game {game_id}")

    # Register in active games and routing registries
    players_info = [
        {"slot": 1, "player_id": f"u:{user.id}", "is_ai": False},
    ]
    for p in range(2, level.player_count + 1):
        players_info.append({"slot": p, "player_id": "bot:campaign", "is_ai": True})
    register_game_fire_and_forget(
        game_id=game_id,
        game_type="campaign",
        speed=level.speed,
        player_count=level.player_count,
        board_type=level.board_type.value,
        players=players_info,
        campaign_level_id=level.level_id,
    )
    await register_routing(game_id)

    # Start game loop immediately so draw timers run even if no WS connects
    await start_game_loop_if_needed(game_id)

    return StartGameResponse(
        game_id=game_id,
        player_key=player_key,
        player_number=player_number,
    )

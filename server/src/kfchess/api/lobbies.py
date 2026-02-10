"""Lobby API endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from kfchess.auth import optional_current_user
from kfchess.db.models import User
from kfchess.lobby.manager import LobbyError, get_lobby_manager
from kfchess.lobby.models import LobbySettings, LobbyStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


class CreateLobbySettingsRequest(BaseModel):
    """Settings for creating a lobby."""

    is_public: bool = Field(default=True, alias="isPublic")
    speed: str = "standard"
    player_count: int = Field(default=2, alias="playerCount")
    is_ranked: bool = Field(default=False, alias="isRanked")

    model_config = {"populate_by_name": True}


class CreateLobbyRequest(BaseModel):
    """Request body for creating a lobby."""

    settings: CreateLobbySettingsRequest | None = None
    add_ai: bool = Field(default=False, alias="addAi")
    ai_type: str = Field(default="bot:novice", alias="aiType")
    guest_id: str | None = Field(default=None, alias="guestId")

    model_config = {"populate_by_name": True}


class CreateLobbyResponse(BaseModel):
    """Response for creating a lobby."""

    id: int
    code: str
    player_key: str = Field(alias="playerKey")
    slot: int
    lobby: dict[str, Any]

    model_config = {"populate_by_name": True}


class JoinLobbyRequest(BaseModel):
    """Request body for joining a lobby."""

    preferred_slot: int | None = Field(default=None, alias="preferredSlot")
    guest_id: str | None = Field(default=None, alias="guestId")

    model_config = {"populate_by_name": True}


class JoinLobbyResponse(BaseModel):
    """Response for joining a lobby."""

    player_key: str = Field(alias="playerKey")
    slot: int
    lobby: dict[str, Any]

    model_config = {"populate_by_name": True}


class LobbyListItem(BaseModel):
    """A lobby item in the list response."""

    id: int
    code: str
    host_username: str = Field(alias="hostUsername")
    host_picture_url: str | None = Field(default=None, alias="hostPictureUrl")
    settings: dict[str, Any]
    player_count: int = Field(alias="playerCount")
    current_players: int = Field(alias="currentPlayers")
    status: str

    model_config = {"populate_by_name": True}


class LobbyListResponse(BaseModel):
    """Response for listing lobbies."""

    lobbies: list[LobbyListItem]


@router.post("", response_model=CreateLobbyResponse)
async def create_lobby(
    request: CreateLobbyRequest,
    user: Annotated[User | None, Depends(optional_current_user)],
) -> CreateLobbyResponse:
    """Create a new lobby.

    If authenticated, the user becomes the host. If not authenticated,
    a guest lobby is created.
    """
    manager = get_lobby_manager()

    # Build settings
    if request.settings:
        try:
            settings = LobbySettings(
                is_public=request.settings.is_public,
                speed=request.settings.speed,
                player_count=request.settings.player_count,
                is_ranked=request.settings.is_ranked,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        settings = LobbySettings()

    # Determine player identity from auth
    if user:
        user_id = user.id
        username = user.username
        player_id = f"u:{user.id}"
    else:
        user_id = None
        username = "Guest"
        player_id = f"guest:{request.guest_id}" if request.guest_id else None

    result = await manager.create_lobby(
        host_user_id=user_id,
        host_username=username,
        settings=settings,
        add_ai=request.add_ai,
        ai_type=request.ai_type,
        player_id=player_id,
        picture_url=user.picture_url if user else None,
    )

    if isinstance(result, LobbyError):
        raise HTTPException(status_code=400, detail=result.message)

    lobby, player_key = result

    logger.info(f"Lobby {lobby.code} created via API")

    return CreateLobbyResponse(
        id=lobby.id,
        code=lobby.code,
        player_key=player_key,
        slot=1,  # Host is always slot 1
        lobby=lobby.to_dict(),
    )


@router.get("", response_model=LobbyListResponse)
async def list_lobbies(
    speed: str | None = None,
    player_count: int | None = Query(default=None, alias="playerCount"),
    is_ranked: bool | None = Query(default=None, alias="isRanked"),
) -> LobbyListResponse:
    """List public lobbies that are waiting for players.

    Only lobbies with status WAITING are returned. Lobbies with games
    in progress can be viewed via the live games endpoint.
    """
    manager = get_lobby_manager()

    lobbies = await manager.get_public_lobbies(
        speed=speed,
        player_count=player_count,
        is_ranked=is_ranked,
    )

    items = []
    for lobby in lobbies:
        host = lobby.host
        items.append(
            LobbyListItem(
                id=lobby.id,
                code=lobby.code,
                host_username=host.username if host else "Unknown",
                host_picture_url=host.picture_url if host else None,
                settings={
                    "isPublic": lobby.settings.is_public,
                    "speed": lobby.settings.speed,
                    "playerCount": lobby.settings.player_count,
                    "isRanked": lobby.settings.is_ranked,
                },
                player_count=lobby.settings.player_count,
                current_players=len(lobby.players),
                status=lobby.status.value,
            )
        )

    return LobbyListResponse(lobbies=items)


@router.get("/{code}")
async def get_lobby(code: str) -> dict[str, Any]:
    """Get lobby details by code."""
    manager = get_lobby_manager()

    lobby = await manager.get_lobby(code)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")

    return {"lobby": lobby.to_dict()}


@router.post("/{code}/join", response_model=JoinLobbyResponse)
async def join_lobby(
    code: str,
    request: JoinLobbyRequest,
    user: Annotated[User | None, Depends(optional_current_user)],
) -> JoinLobbyResponse:
    """Join an existing lobby.

    Returns the player key needed for WebSocket authentication.
    Both public and private lobbies can be joined if the user knows the code
    (e.g., via invite link).
    """
    manager = get_lobby_manager()

    # Check if lobby exists
    lobby = await manager.get_lobby(code)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")

    # Determine player identity from auth
    if user:
        user_id = user.id
        username = user.username
        player_id = f"u:{user.id}"
    else:
        user_id = None
        username = "Guest"
        player_id = f"guest:{request.guest_id}" if request.guest_id else None

    result = await manager.join_lobby(
        code=code,
        user_id=user_id,
        username=username,
        player_id=player_id,
        preferred_slot=request.preferred_slot,
        picture_url=user.picture_url if user else None,
    )

    if isinstance(result, LobbyError):
        if result.code == "not_found":
            raise HTTPException(status_code=404, detail=result.message)
        elif result.code == "lobby_full":
            raise HTTPException(status_code=409, detail=result.message)
        elif result.code == "game_in_progress":
            raise HTTPException(status_code=409, detail=result.message)
        else:
            raise HTTPException(status_code=400, detail=result.message)

    lobby, player_key, slot = result

    logger.info(f"Player {username} joined lobby {code} via API")

    return JoinLobbyResponse(
        player_key=player_key,
        slot=slot,
        lobby=lobby.to_dict(),
    )


@router.delete("/{code}")
async def delete_lobby(
    code: str,
    player_key: str = Query(..., description="Host's player key"),
) -> dict[str, Any]:
    """Delete a lobby (host only).

    The player_key query parameter is used to verify the requester is the host.
    """
    manager = get_lobby_manager()

    # Validate player key and check if host
    slot = await manager.validate_player_key(code, player_key)
    if slot is None:
        raise HTTPException(status_code=403, detail="Invalid player key")

    lobby = await manager.get_lobby(code)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")

    if lobby.host_slot != slot:
        raise HTTPException(status_code=403, detail="Only the host can delete the lobby")

    if lobby.status != LobbyStatus.WAITING:
        raise HTTPException(status_code=409, detail="Cannot delete lobby while game is in progress")

    success = await manager.delete_lobby(code)
    if not success:
        raise HTTPException(status_code=404, detail="Lobby not found")

    logger.info(f"Lobby {code} deleted via API")

    return {"success": True}

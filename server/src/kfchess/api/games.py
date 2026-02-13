"""Game API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from kfchess.db.repositories.active_games import ActiveGameRepository
from kfchess.db.repositories.replays import ReplayRepository
from kfchess.db.session import async_session_factory
from kfchess.drain import is_draining
from kfchess.game.board import BoardType
from kfchess.game.collision import (
    get_interpolated_position,
    is_piece_moving,
    is_piece_on_cooldown,
)
from kfchess.game.state import Speed
from kfchess.redis.client import get_redis
from kfchess.redis.heartbeat import is_server_alive
from kfchess.redis.routing import get_game_server, register_routing
from kfchess.services.game_registry import deregister_game_fire_and_forget
from kfchess.services.game_service import get_game_service
from kfchess.settings import get_settings
from kfchess.utils.display_name import resolve_player_info, resolve_player_info_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


class CreateGameRequest(BaseModel):
    """Request body for creating a game."""

    speed: str = "standard"
    board_type: str = "standard"
    opponent: str = "bot:novice"


class CreateGameResponse(BaseModel):
    """Response for creating a game."""

    game_id: str
    player_key: str
    player_number: int
    board_type: str
    status: str


class MoveRequest(BaseModel):
    """Request body for making a move."""

    player_key: str
    piece_id: str
    to_row: int
    to_col: int


class MoveResponse(BaseModel):
    """Response for making a move."""

    success: bool
    error: str | None = None
    message: str | None = None
    move: dict | None = None


class ReadyRequest(BaseModel):
    """Request body for marking player ready."""

    player_key: str


class ReadyResponse(BaseModel):
    """Response for marking player ready."""

    success: bool
    game_started: bool
    status: str


class LiveGamePlayer(BaseModel):
    """Player info in a live game."""

    slot: int
    username: str
    is_ai: bool = False
    user_id: int | None = None
    picture_url: str | None = None


class LiveGameItem(BaseModel):
    """A live game in the list response."""

    game_id: str
    game_type: str
    lobby_code: str | None = None
    campaign_level_id: int | None = None
    players: list[LiveGamePlayer]
    settings: dict
    current_tick: int
    started_at: str | None = None


class LiveGamesResponse(BaseModel):
    """Response for listing live games."""

    games: list[LiveGameItem]


@router.post("", response_model=CreateGameResponse)
async def create_game(request: CreateGameRequest) -> CreateGameResponse:
    """Create a new game against AI."""
    if is_draining():
        raise HTTPException(status_code=503, detail="Server is shutting down")

    logger.info(f"Creating game: speed={request.speed}, board_type={request.board_type}, opponent={request.opponent}")

    # Validate speed
    try:
        speed = Speed(request.speed)
    except ValueError as err:
        logger.warning(f"Invalid speed: {request.speed}")
        raise HTTPException(status_code=400, detail=f"Invalid speed: {request.speed}") from err

    # Validate board type
    try:
        board_type = BoardType(request.board_type)
    except ValueError as err:
        logger.warning(f"Invalid board_type: {request.board_type}")
        raise HTTPException(
            status_code=400, detail=f"Invalid board type: {request.board_type}"
        ) from err

    # Create the game
    try:
        service = get_game_service()
        game_id, player_key, player_number = service.create_game(
            speed=speed,
            board_type=board_type,
            opponent=request.opponent,
        )
        logger.info(f"Game created: game_id={game_id}, player_number={player_number}")

        # Register routing key only (active_games deferred until game starts)
        await register_routing(game_id)
    except Exception as err:
        logger.exception(f"Failed to create game: {err}")
        raise HTTPException(status_code=500, detail=f"Failed to create game: {err}") from err

    return CreateGameResponse(
        game_id=game_id,
        player_key=player_key,
        player_number=player_number,
        board_type=request.board_type,
        status="waiting",
    )


# IMPORTANT: /live endpoint must be defined BEFORE /{game_id} to avoid being
# caught by the parameterized route
@router.get("/live", response_model=LiveGamesResponse)
async def list_live_games(
    speed: str | None = None,
    player_count: int | None = None,
    game_type: str | None = None,
) -> LiveGamesResponse:
    """List games currently in progress.

    Queries the active_games database registry, then validates each entry
    against in-memory state and Redis routing/heartbeat to filter out stale
    games. Definitely-dead games (ours but not in memory, or no routing key)
    are deregistered on the spot.
    """
    service = get_game_service()
    my_server_id = get_settings().effective_server_id

    async with async_session_factory() as session:
        repo = ActiveGameRepository(session)
        active_records = await repo.list_active(
            speed=speed,
            player_count=player_count,
            game_type=game_type,
        )

    # Validate each record against live state
    r = await get_redis()
    stale_game_ids: list[str] = []
    valid_records: list[tuple] = []  # (record, current_tick)
    for record in active_records:
        state = service.get_game(record.game_id)

        if state is not None:
            # Game is in memory on this server — definitely live
            pass
        elif record.server_id == my_server_id:
            # Owned by us but not in memory — definitely dead
            stale_game_ids.append(record.game_id)
            continue
        else:
            # On a remote server — check routing + heartbeat
            routing_owner = await get_game_server(r, record.game_id)
            if routing_owner is None:
                # No routing key — game is gone
                stale_game_ids.append(record.game_id)
                continue
            if not await is_server_alive(r, routing_owner):
                # Owner server is dead — omit but don't deregister
                # (might be recoverable via crash recovery)
                continue

        valid_records.append((record, state.current_tick if state else 0))

    # Batch-resolve player display names from player_ids
    players_dicts: list[dict[int, str]] = []
    for record, _ in valid_records:
        pid_map: dict[int, str] = {}
        for p in record.players:
            player_id = p.get("player_id")
            if player_id:
                pid_map[p["slot"]] = player_id
        players_dicts.append(pid_map)

    async with async_session_factory() as session:
        resolved_list = await resolve_player_info_batch(session, players_dicts)

    # Build response
    games = []
    for (record, current_tick), resolved in zip(valid_records, resolved_list, strict=True):
        players = []
        for p in record.players:
            slot = p["slot"]
            display = resolved.get(slot)
            if display:
                players.append(LiveGamePlayer(
                    slot=slot,
                    username=display.name,
                    is_ai=p.get("is_ai", False),
                    user_id=display.user_id,
                    picture_url=display.picture_url,
                ))
            else:
                # Fallback for legacy rows without player_id
                players.append(LiveGamePlayer(
                    slot=slot,
                    username=p.get("username", f"Player {slot}"),
                    is_ai=p.get("is_ai", False),
                    user_id=p.get("user_id"),
                    picture_url=p.get("picture_url"),
                ))

        games.append(
            LiveGameItem(
                game_id=record.game_id,
                game_type=record.game_type,
                lobby_code=record.lobby_code,
                campaign_level_id=record.campaign_level_id,
                players=players,
                settings={
                    "speed": record.speed,
                    "playerCount": record.player_count,
                    "boardType": record.board_type,
                },
                current_tick=current_tick,
                started_at=record.started_at.isoformat() if record.started_at else None,
            )
        )

    # Deregister definitely-dead games in background
    for game_id in stale_game_ids:
        deregister_game_fire_and_forget(game_id)

    return LiveGamesResponse(games=games)


@router.get("/{game_id}")
async def get_game(game_id: str, server: str | None = None) -> dict[str, Any]:
    """Get the current game state."""
    service = get_game_service()
    state = service.get_game(game_id)

    if state is None:
        # Not on this server — check Redis routing for cross-server redirect
        try:
            r = await get_redis()
            owner = await get_game_server(r, game_id)
            my_server_id = get_settings().effective_server_id

            if owner is not None and owner != my_server_id:
                if await is_server_alive(r, owner):
                    logger.info(
                        f"REST redirect: game {game_id} is on {owner}, "
                        f"sending 307"
                    )
                    return RedirectResponse(
                        url=f"/api/games/{game_id}?server={owner}",
                        status_code=307,
                    )
        except Exception:
            logger.exception(f"Failed to check routing for game {game_id}")

        raise HTTPException(status_code=404, detail="Game not found")

    config = state.config

    # Build piece data with interpolated positions
    pieces = []
    for piece in state.board.pieces:
        # Get interpolated position if moving
        pos = get_interpolated_position(
            piece, state.active_moves, state.current_tick, config.ticks_per_square
        )

        pieces.append(
            {
                "id": piece.id,
                "type": piece.type.value,
                "player": piece.player,
                "row": pos[0],
                "col": pos[1],
                "captured": piece.captured,
                "moving": is_piece_moving(piece.id, state.active_moves),
                "on_cooldown": is_piece_on_cooldown(piece.id, state.cooldowns, state.current_tick),
                "moved": piece.moved,
            }
        )

    # Build active moves data
    active_moves = []
    for move in state.active_moves:
        total_ticks = (len(move.path) - 1) * config.ticks_per_square
        elapsed = max(0, state.current_tick - move.start_tick)
        progress = min(1.0, elapsed / total_ticks) if total_ticks > 0 else 1.0

        active_moves.append(
            {
                "piece_id": move.piece_id,
                "path": move.path,
                "start_tick": move.start_tick,
                "progress": progress,
            }
        )

    # Build cooldown data
    cooldowns = []
    for cd in state.cooldowns:
        remaining = max(0, (cd.start_tick + cd.duration) - state.current_tick)
        cooldowns.append(
            {
                "piece_id": cd.piece_id,
                "remaining_ticks": remaining,
            }
        )

    # Resolve player display names
    async with async_session_factory() as session:
        resolved_players = await resolve_player_info(session, state.players)

    players_serialized = {
        str(k): v.model_dump() for k, v in resolved_players.items()
    }

    return {
        "game_id": state.game_id,
        "status": state.status.value,
        "speed": state.speed.value,
        "current_tick": state.current_tick,
        "winner": state.winner,
        "players": players_serialized,
        "board": {
            "board_type": state.board.board_type.value,
            "width": state.board.width,
            "height": state.board.height,
            "pieces": pieces,
        },
        "active_moves": active_moves,
        "cooldowns": cooldowns,
    }


@router.post("/{game_id}/move", response_model=MoveResponse)
async def make_move(game_id: str, request: MoveRequest) -> MoveResponse:
    """Make a move in the game."""
    service = get_game_service()

    result = service.make_move(
        game_id=game_id,
        player_key=request.player_key,
        piece_id=request.piece_id,
        to_row=request.to_row,
        to_col=request.to_col,
    )

    if result.error == "game_not_found":
        raise HTTPException(status_code=404, detail="Game not found")

    return MoveResponse(
        success=result.success,
        error=result.error,
        message=result.message,
        move=result.move_data,
    )


@router.post("/{game_id}/ready", response_model=ReadyResponse)
async def mark_ready(game_id: str, request: ReadyRequest) -> ReadyResponse:
    """Mark player as ready to start the game."""
    service = get_game_service()

    state = service.get_game(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    success, game_started = service.mark_ready(game_id, request.player_key)

    # Refresh state after marking ready
    state = service.get_game(game_id)
    status = state.status.value if state else "unknown"

    return ReadyResponse(
        success=success,
        game_started=game_started,
        status=status,
    )


@router.get("/{game_id}/legal-moves")
async def get_legal_moves(game_id: str, player_key: str) -> dict[str, Any]:
    """Get all legal moves for the player."""
    service = get_game_service()

    state = service.get_game(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    moves = service.get_legal_moves(game_id, player_key)
    if moves is None:
        raise HTTPException(status_code=403, detail="Invalid player key")

    return {"moves": moves}


@router.get("/{game_id}/replay")
async def get_replay(game_id: str) -> dict[str, Any]:
    """Get the replay data for a completed game.

    First tries to get the replay from the database. If not found,
    checks if the game is still in memory and finished.

    Returns:
        Replay data including moves, players, and game outcome
    """
    # First, try to get from database
    async with async_session_factory() as session:
        repository = ReplayRepository(session)
        replay = await repository.get_by_id(game_id)
        if replay is not None:
            return replay.to_dict()

    # Fall back to in-memory game state
    service = get_game_service()
    replay = service.get_replay(game_id)

    if replay is None:
        # Check if game exists but isn't finished
        state = service.get_game(game_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Game not found")
        if not state.is_finished:
            raise HTTPException(status_code=400, detail="Game is not finished yet")
        raise HTTPException(status_code=404, detail="Replay not found")

    return replay.to_dict()

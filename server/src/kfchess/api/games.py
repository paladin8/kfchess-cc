"""Game API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kfchess.game.board import BoardType
from kfchess.game.collision import (
    get_interpolated_position,
    is_piece_moving,
    is_piece_on_cooldown,
)
from kfchess.game.state import Speed
from kfchess.services.game_service import get_game_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


class CreateGameRequest(BaseModel):
    """Request body for creating a game."""

    speed: str = "standard"
    board_type: str = "standard"
    opponent: str = "bot:dummy"


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


class LiveGameItem(BaseModel):
    """A live game in the list response."""

    game_id: str
    lobby_code: str | None = None
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
) -> LiveGamesResponse:
    """List games currently in progress for spectating.

    This endpoint returns all public games that are currently being played.
    Users can spectate any game by connecting to its WebSocket without a player key.
    """
    from kfchess.lobby.manager import get_lobby_manager
    from kfchess.lobby.models import LobbyStatus

    lobby_manager = get_lobby_manager()
    service = get_game_service()

    games = []

    # Get games from IN_GAME lobbies (these have player info)
    for code, lobby in list(lobby_manager._lobbies.items()):
        if lobby.status != LobbyStatus.IN_GAME:
            continue
        if not lobby.settings.is_public:
            continue
        if speed and lobby.settings.speed != speed:
            continue
        if player_count and lobby.settings.player_count != player_count:
            continue

        game_id = lobby.current_game_id
        if not game_id:
            continue

        # Get current game state
        state = service.get_game(game_id)
        if state is None:
            continue

        # Build player list
        players = [
            LiveGamePlayer(
                slot=slot,
                username=p.username,
                is_ai=p.is_ai,
            )
            for slot, p in sorted(lobby.players.items())
        ]

        managed_game = service.get_managed_game(game_id)
        started_at = managed_game.created_at.isoformat() if managed_game else None

        games.append(
            LiveGameItem(
                game_id=game_id,
                lobby_code=code,
                players=players,
                settings={
                    "speed": lobby.settings.speed,
                    "playerCount": lobby.settings.player_count,
                    "isRanked": lobby.settings.is_ranked,
                },
                current_tick=state.current_tick,
                started_at=started_at,
            )
        )

    return LiveGamesResponse(games=games)


@router.get("/{game_id}")
async def get_game(game_id: str) -> dict[str, Any]:
    """Get the current game state."""
    service = get_game_service()
    state = service.get_game(game_id)

    if state is None:
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

    return {
        "game_id": state.game_id,
        "status": state.status.value,
        "current_tick": state.current_tick,
        "winner": state.winner,
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
    from kfchess.db.repositories.replays import ReplayRepository
    from kfchess.db.session import async_session_factory

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

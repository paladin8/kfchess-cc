"""Game API endpoints."""

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


@router.post("", response_model=CreateGameResponse)
async def create_game(request: CreateGameRequest) -> CreateGameResponse:
    """Create a new game against AI."""
    # Validate speed
    try:
        speed = Speed(request.speed)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid speed: {request.speed}") from err

    # Validate board type
    try:
        board_type = BoardType(request.board_type)
    except ValueError as err:
        raise HTTPException(
            status_code=400, detail=f"Invalid board type: {request.board_type}"
        ) from err

    # Create the game
    service = get_game_service()
    game_id, player_key, player_number = service.create_game(
        speed=speed,
        board_type=board_type,
        opponent=request.opponent,
    )

    return CreateGameResponse(
        game_id=game_id,
        player_key=player_key,
        player_number=player_number,
        board_type=request.board_type,
        status="waiting",
    )


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

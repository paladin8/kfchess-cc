"""Fire-and-forget helpers for active game registration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kfchess.game.state import GameState

from kfchess.db.repositories.active_games import ActiveGameRepository
from kfchess.db.session import async_session_factory
from kfchess.settings import get_settings

logger = logging.getLogger(__name__)

# Store references to background tasks to prevent garbage collection.
# See: https://docs.python.org/3/library/asyncio-task.html#creating-tasks
_background_tasks: set[asyncio.Task] = set()

# Periodic cleanup task
_cleanup_task: asyncio.Task | None = None
CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
CLEANUP_MAX_AGE_HOURS = 2


async def _register_game(
    game_id: str,
    game_type: str,
    speed: str,
    player_count: int,
    board_type: str,
    players: list[dict],
    lobby_code: str | None = None,
    campaign_level_id: int | None = None,
    started_at: datetime | None = None,
) -> None:
    """Register a game in the database (runs in background)."""
    try:
        server_id = get_settings().effective_server_id
        async with async_session_factory() as session:
            repo = ActiveGameRepository(session)
            await repo.register(
                game_id=game_id,
                game_type=game_type,
                speed=speed,
                player_count=player_count,
                board_type=board_type,
                players=players,
                server_id=server_id,
                lobby_code=lobby_code,
                campaign_level_id=campaign_level_id,
                started_at=started_at,
            )
            await session.commit()
    except Exception:
        logger.exception(f"Failed to register active game {game_id}")


async def _deregister_game(game_id: str) -> None:
    """Deregister a game from the database (runs in background)."""
    try:
        async with async_session_factory() as session:
            repo = ActiveGameRepository(session)
            await repo.deregister(game_id)
            await session.commit()
    except Exception:
        logger.exception(f"Failed to deregister active game {game_id}")


def register_game_fire_and_forget(
    game_id: str,
    game_type: str,
    speed: str,
    player_count: int,
    board_type: str,
    players: list[dict],
    lobby_code: str | None = None,
    campaign_level_id: int | None = None,
    started_at: datetime | None = None,
) -> None:
    """Schedule game registration as a fire-and-forget task."""
    task = asyncio.create_task(
        _register_game(
            game_id=game_id,
            game_type=game_type,
            speed=speed,
            player_count=player_count,
            board_type=board_type,
            players=players,
            lobby_code=lobby_code,
            campaign_level_id=campaign_level_id,
            started_at=started_at,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def deregister_game_fire_and_forget(game_id: str) -> None:
    """Schedule game deregistration as a fire-and-forget task."""
    task = asyncio.create_task(_deregister_game(game_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def register_restored_game(
    game_id: str,
    state: GameState,
    ai_player_nums: set[int],
    campaign_level_id: int | None,
) -> None:
    """Register a restored game in the active_games DB table.

    Shared by startup restore (main.py) and on-demand crash recovery
    (ws/handler.py). Uses fire-and-forget registration.

    Args:
        game_id: The game ID
        state: The restored GameState
        ai_player_nums: Set of player numbers that are AI
        campaign_level_id: Campaign level ID or None
    """
    players_info = []
    for pnum, pid in state.players.items():
        is_ai = pnum in ai_player_nums
        players_info.append({"slot": pnum, "player_id": pid, "is_ai": is_ai})

    game_type = "campaign" if campaign_level_id else "restored"
    register_game_fire_and_forget(
        game_id=game_id,
        game_type=game_type,
        speed=state.speed.value,
        player_count=len(state.players),
        board_type=state.board.board_type.value,
        players=players_info,
        campaign_level_id=campaign_level_id,
        started_at=state.started_at,
    )


async def deregister_game(game_id: str) -> None:
    """Deregister a game from the active_games table (awaitable).

    Use this instead of the fire-and-forget variant when you can afford
    to wait, e.g. at the end of a game loop where reliability matters.
    """
    try:
        async with async_session_factory() as session:
            repo = ActiveGameRepository(session)
            await repo.deregister(game_id)
            await session.commit()
    except Exception:
        logger.exception(f"Failed to deregister active game {game_id}")


async def _cleanup_loop() -> None:
    """Background loop that periodically removes stale active_games entries."""
    try:
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            try:
                async with async_session_factory() as session:
                    repo = ActiveGameRepository(session)
                    removed = await repo.cleanup_stale(
                        max_age_hours=CLEANUP_MAX_AGE_HOURS,
                    )
                    if removed:
                        await session.commit()
                        logger.info(
                            f"Periodic cleanup: removed {removed} stale "
                            f"active game entries"
                        )
            except Exception:
                logger.exception("Error in periodic active-game cleanup")
    except asyncio.CancelledError:
        raise


async def start_cleanup_loop() -> None:
    """Start the periodic stale-game cleanup task."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        return
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info(
        f"Active-game cleanup loop started "
        f"(interval={CLEANUP_INTERVAL_SECONDS}s, "
        f"max_age={CLEANUP_MAX_AGE_HOURS}h)"
    )


async def stop_cleanup_loop() -> None:
    """Stop the periodic stale-game cleanup task."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    _cleanup_task = None
    logger.info("Active-game cleanup loop stopped")

"""Game loop lifecycle helpers.

Shared module that handler.py, lobby_handler.py, and campaign.py can all
import without circular-dependency issues.  The actual game-loop coroutine
(_run_game_loop) lives in handler.py and is registered here at import time
via ``register_game_loop_factory()``.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from kfchess.services.game_service import get_game_service

logger = logging.getLogger(__name__)

# ── Lock management ──────────────────────────────────────────────

_game_loop_locks: dict[str, asyncio.Lock] = {}


def _get_game_loop_lock(game_id: str) -> asyncio.Lock:
    """Get or create a lock for game loop startup."""
    if game_id not in _game_loop_locks:
        _game_loop_locks[game_id] = asyncio.Lock()
    return _game_loop_locks[game_id]


def cleanup_game_loop_lock(game_id: str) -> None:
    """Remove the lock for a finished game."""
    _game_loop_locks.pop(game_id, None)


# ── Game loop factory registration ───────────────────────────────

_game_loop_factory: Callable[[str], Coroutine[Any, Any, None]] | None = None


def register_game_loop_factory(
    factory: Callable[[str], Coroutine[Any, Any, None]],
) -> None:
    """Register the game loop coroutine factory.

    Called once by handler.py at import time to provide _run_game_loop.
    """
    global _game_loop_factory  # noqa: PLW0603
    _game_loop_factory = factory


# ── Public API ───────────────────────────────────────────────────


async def start_game_loop_if_needed(game_id: str) -> None:
    """Start the game loop if not already running.

    Uses a lock to prevent race conditions when multiple connections
    try to start the loop simultaneously.
    """
    if _game_loop_factory is None:
        logger.error("Game loop factory not registered — cannot start loop")
        return

    service = get_game_service()
    lock = _get_game_loop_lock(game_id)

    async with lock:
        managed_game = service.get_managed_game(game_id)
        if managed_game is None:
            return

        if not managed_game.state.is_playing:
            return

        if managed_game.loop_task is None or managed_game.loop_task.done():
            managed_game.loop_task = asyncio.create_task(_game_loop_factory(game_id))

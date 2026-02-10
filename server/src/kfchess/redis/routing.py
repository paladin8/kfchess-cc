"""Redis storage for game-to-server routing keys."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from kfchess.redis.client import get_redis
from kfchess.settings import get_settings

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Background tasks for fire-and-forget routing operations
_routing_tasks: set[asyncio.Task] = set()

ROUTING_TTL_SECONDS = 7200  # 2 hours (same as snapshot)


def _routing_key(game_id: str) -> str:
    """Build the Redis key for game routing."""
    return f"game:{game_id}:server"


async def register_game_routing(
    r: aioredis.Redis, game_id: str, server_id: str
) -> None:
    """Register which server owns a game.

    Sets game:{game_id}:server to the server_id with a TTL.
    Called on game creation and refreshed periodically by the game loop.
    """
    key = _routing_key(game_id)
    await r.set(key, server_id, ex=ROUTING_TTL_SECONDS)


async def get_game_server(r: aioredis.Redis, game_id: str) -> str | None:
    """Look up which server owns a game.

    Returns the server_id or None if no routing entry exists.
    """
    key = _routing_key(game_id)
    return await r.get(key)


async def delete_game_routing(r: aioredis.Redis, game_id: str) -> None:
    """Remove the routing entry for a game.

    Called when a game finishes.
    """
    key = _routing_key(game_id)
    await r.delete(key)


def register_routing_fire_and_forget(game_id: str) -> None:
    """Schedule routing registration as a fire-and-forget task.

    Uses the current server's effective_server_id.
    """
    async def _register() -> None:
        try:
            r = await get_redis()
            server_id = get_settings().effective_server_id
            await register_game_routing(r, game_id, server_id)
        except Exception:
            logger.exception(f"Failed to register routing for game {game_id}")

    task = asyncio.create_task(_register())
    _routing_tasks.add(task)
    task.add_done_callback(_routing_tasks.discard)

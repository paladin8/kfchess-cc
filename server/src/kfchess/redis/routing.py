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


# Lua CAS script: atomically claim a routing key from a dead server.
# If the current value matches the expected (dead) server, sets to the new owner
# with TTL. Returns 1 on success, 0 if the value didn't match.
_CLAIM_LUA_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
    return 1
else
    return 0
end
"""


async def claim_game_routing(
    r: aioredis.Redis,
    game_id: str,
    expected_server_id: str,
    new_server_id: str,
) -> bool:
    """Atomically claim a game's routing key from an expected (dead) server.

    Uses a Lua compare-and-swap: if the current value matches
    expected_server_id, sets it to new_server_id with TTL.
    Returns True if the claim succeeded, False if another server already
    claimed it or the key doesn't exist / has a different value.
    """
    key = _routing_key(game_id)
    result = await r.eval(
        _CLAIM_LUA_SCRIPT,
        1,
        key,
        expected_server_id,
        new_server_id,
        str(ROUTING_TTL_SECONDS),
    )
    if result == 1:
        logger.info(
            f"Claimed game {game_id} routing: {expected_server_id} -> {new_server_id}"
        )
        return True
    logger.info(
        f"Failed to claim game {game_id} routing from {expected_server_id} "
        f"(current owner differs)"
    )
    return False


async def register_routing(game_id: str) -> None:
    """Register routing for a game synchronously (awaited).

    This must be awaited before returning a game_id to the client so
    the routing key exists when the client's WebSocket connection arrives
    (which may land on a different server in multi-process/multi-server).
    """
    try:
        r = await get_redis()
        server_id = get_settings().effective_server_id
        await register_game_routing(r, game_id, server_id)
    except Exception:
        logger.exception(f"Failed to register routing for game {game_id}")


def register_routing_fire_and_forget(game_id: str) -> None:
    """Schedule routing registration as a fire-and-forget task.

    Uses the current server's effective_server_id.

    WARNING: Only use this when the caller does not need to guarantee the
    key exists before returning to the client. For game creation endpoints,
    use register_routing() instead.
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

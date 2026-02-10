"""Server heartbeat for liveness detection."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

HEARTBEAT_TTL_SECONDS = 5
HEARTBEAT_INTERVAL_SECONDS = 1

_heartbeat_task: asyncio.Task | None = None


def _heartbeat_key(server_id: str) -> str:
    """Build the Redis key for a server heartbeat."""
    return f"server:{server_id}:heartbeat"


async def _heartbeat_loop(r: aioredis.Redis, server_id: str) -> None:
    """Background loop that refreshes the heartbeat key."""
    key = _heartbeat_key(server_id)
    try:
        while True:
            await r.set(key, str(time.time()), ex=HEARTBEAT_TTL_SECONDS)
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        # Clean up: delete heartbeat key on graceful shutdown
        try:
            await r.delete(key)
        except Exception:
            pass
        raise


async def is_server_alive(r: aioredis.Redis, server_id: str) -> bool:
    """Check if a server has a live heartbeat."""
    key = _heartbeat_key(server_id)
    return await r.exists(key) == 1


async def start_heartbeat(r: aioredis.Redis, server_id: str) -> None:
    """Start the heartbeat background task."""
    global _heartbeat_task
    if _heartbeat_task is not None and not _heartbeat_task.done():
        return
    _heartbeat_task = asyncio.create_task(_heartbeat_loop(r, server_id))
    logger.info(f"Heartbeat started for server {server_id}")


async def stop_heartbeat() -> None:
    """Stop the heartbeat background task."""
    global _heartbeat_task
    if _heartbeat_task is not None and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    _heartbeat_task = None
    logger.info("Heartbeat stopped")

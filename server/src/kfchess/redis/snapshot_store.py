"""Redis storage for game snapshots."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from kfchess.game.snapshot import GameSnapshot

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

SNAPSHOT_TTL_SECONDS = 7200  # 2 hours


def _snapshot_key(game_id: str) -> str:
    """Build the Redis key for a game snapshot."""
    return f"game:{game_id}:snapshot"


async def save_snapshot(r: aioredis.Redis, snapshot: GameSnapshot) -> None:
    """Save a game snapshot to Redis.

    Overwrites any existing snapshot for the same game_id.
    TTL is refreshed on each save.
    """
    key = _snapshot_key(snapshot.game_id)
    data = json.dumps(snapshot.to_dict())
    await r.set(key, data, ex=SNAPSHOT_TTL_SECONDS)


async def load_snapshot(r: aioredis.Redis, game_id: str) -> GameSnapshot | None:
    """Load a game snapshot from Redis.

    Returns None if the snapshot doesn't exist, has expired, or is corrupted.
    """
    key = _snapshot_key(game_id)
    data = await r.get(key)
    if data is None:
        return None
    try:
        return GameSnapshot.from_dict(json.loads(data))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning(f"Corrupted snapshot for game {game_id}, ignoring")
        return None


async def delete_snapshot(r: aioredis.Redis, game_id: str) -> None:
    """Delete a game snapshot from Redis."""
    key = _snapshot_key(game_id)
    await r.delete(key)


async def list_snapshot_game_ids(r: aioredis.Redis) -> list[str]:
    """List all game IDs that have snapshots in Redis.

    Uses SCAN to avoid blocking on large key spaces.
    """
    game_ids: list[str] = []
    prefix = "game:"
    suffix = ":snapshot"
    async for key in r.scan_iter(match="game:*:snapshot", count=100):
        # key is already a str because decode_responses=True
        game_id = key[len(prefix) : -len(suffix)]
        game_ids.append(game_id)
    return game_ids

"""Async Redis client for game state persistence."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from kfchess.settings import get_settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get the shared async Redis client, creating it if needed."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        logger.info(f"Redis client connected to {settings.redis_url}")
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis client closed")

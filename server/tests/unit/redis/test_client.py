"""Tests for Redis client module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kfchess.redis import client as redis_client


class TestRedisClient:
    """Tests for the Redis client singleton."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        """Reset the global client between tests."""
        redis_client._redis_client = None
        yield
        redis_client._redis_client = None

    @pytest.mark.asyncio
    async def test_get_redis_creates_client(self) -> None:
        """get_redis creates a client on first call."""
        with patch("kfchess.redis.client.aioredis") as mock_aioredis:
            mock_client = AsyncMock()
            mock_aioredis.from_url.return_value = mock_client

            result = await redis_client.get_redis()
            assert result is mock_client
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_redis_returns_same_instance(self) -> None:
        """get_redis returns the same client on subsequent calls."""
        with patch("kfchess.redis.client.aioredis") as mock_aioredis:
            mock_client = AsyncMock()
            mock_aioredis.from_url.return_value = mock_client

            r1 = await redis_client.get_redis()
            r2 = await redis_client.get_redis()
            assert r1 is r2
            assert mock_aioredis.from_url.call_count == 1

    @pytest.mark.asyncio
    async def test_close_redis_closes_client(self) -> None:
        """close_redis closes the connection and resets the global."""
        mock_client = AsyncMock()
        redis_client._redis_client = mock_client

        await redis_client.close_redis()

        mock_client.aclose.assert_called_once()
        assert redis_client._redis_client is None

    @pytest.mark.asyncio
    async def test_close_redis_noop_when_not_connected(self) -> None:
        """close_redis is safe to call when no client exists."""
        await redis_client.close_redis()  # Should not raise

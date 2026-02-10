"""Tests for Redis heartbeat."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from kfchess.redis.heartbeat import (
    HEARTBEAT_TTL_SECONDS,
    _heartbeat_key,
    is_server_alive,
    start_heartbeat,
    stop_heartbeat,
)


@pytest.fixture
def redis():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestHeartbeat:
    """Tests for heartbeat lifecycle."""

    @pytest.mark.asyncio
    async def test_heartbeat_sets_key(self, redis) -> None:
        """Heartbeat sets the server key in Redis."""
        await start_heartbeat(redis, "test-server")
        # Give the task a moment to run
        await asyncio.sleep(0.05)

        key = _heartbeat_key("test-server")
        value = await redis.get(key)
        assert value is not None

        await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_heartbeat_key_has_ttl(self, redis) -> None:
        """Heartbeat key has the correct TTL."""
        await start_heartbeat(redis, "test-server")
        await asyncio.sleep(0.05)

        key = _heartbeat_key("test-server")
        ttl = await redis.ttl(key)
        assert 0 < ttl <= HEARTBEAT_TTL_SECONDS

        await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_stop_heartbeat_removes_key(self, redis) -> None:
        """Stopping heartbeat deletes the key."""
        await start_heartbeat(redis, "test-server")
        await asyncio.sleep(0.05)

        await stop_heartbeat()
        await asyncio.sleep(0.05)

        key = _heartbeat_key("test-server")
        value = await redis.get(key)
        assert value is None

    @pytest.mark.asyncio
    async def test_start_heartbeat_idempotent(self, redis) -> None:
        """Starting heartbeat twice doesn't create duplicate tasks."""
        await start_heartbeat(redis, "test-server")
        await start_heartbeat(redis, "test-server")  # Should be no-op
        await asyncio.sleep(0.05)

        key = _heartbeat_key("test-server")
        value = await redis.get(key)
        assert value is not None

        await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_stop_heartbeat_idempotent(self, redis) -> None:
        """Stopping heartbeat when not running is safe."""
        await stop_heartbeat()  # Should not raise

    @pytest.mark.asyncio
    async def test_heartbeat_key_format(self) -> None:
        """Key format is server:{id}:heartbeat."""
        assert _heartbeat_key("worker1") == "server:worker1:heartbeat"


class TestIsServerAlive:
    """Tests for is_server_alive."""

    @pytest.mark.asyncio
    async def test_alive_server(self, redis) -> None:
        """Server with active heartbeat is alive."""
        await start_heartbeat(redis, "live-server")
        await asyncio.sleep(0.05)

        assert await is_server_alive(redis, "live-server") is True
        await stop_heartbeat()

    @pytest.mark.asyncio
    async def test_dead_server(self, redis) -> None:
        """Server with no heartbeat key is dead."""
        assert await is_server_alive(redis, "dead-server") is False

    @pytest.mark.asyncio
    async def test_stopped_server(self, redis) -> None:
        """Server whose heartbeat was stopped is dead."""
        await start_heartbeat(redis, "stopped-server")
        await asyncio.sleep(0.05)
        await stop_heartbeat()
        await asyncio.sleep(0.05)

        assert await is_server_alive(redis, "stopped-server") is False

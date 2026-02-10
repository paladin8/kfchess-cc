"""Tests for Redis game routing store."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from kfchess.redis.routing import (
    ROUTING_TTL_SECONDS,
    delete_game_routing,
    get_game_server,
    register_game_routing,
    register_routing_fire_and_forget,
)


@pytest.fixture
def redis():
    """Create a fakeredis async client."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestRegisterGameRouting:
    """Tests for register_game_routing."""

    @pytest.mark.asyncio
    async def test_register_sets_key(self, redis) -> None:
        """Registering a game sets the routing key."""
        await register_game_routing(redis, "GAME1234", "worker1")

        value = await redis.get("game:GAME1234:server")
        assert value == "worker1"

    @pytest.mark.asyncio
    async def test_register_sets_ttl(self, redis) -> None:
        """Routing key has the correct TTL."""
        await register_game_routing(redis, "GAME1234", "worker1")

        ttl = await redis.ttl("game:GAME1234:server")
        assert 0 < ttl <= ROUTING_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_register_overwrites_existing(self, redis) -> None:
        """Re-registering updates the server_id."""
        await register_game_routing(redis, "GAME1234", "worker1")
        await register_game_routing(redis, "GAME1234", "worker2")

        value = await redis.get("game:GAME1234:server")
        assert value == "worker2"

    @pytest.mark.asyncio
    async def test_register_refreshes_ttl(self, redis) -> None:
        """Re-registering refreshes the TTL."""
        await register_game_routing(redis, "GAME1234", "worker1")

        # Manually reduce TTL to simulate time passing
        await redis.expire("game:GAME1234:server", 100)
        ttl_before = await redis.ttl("game:GAME1234:server")
        assert ttl_before <= 100

        # Re-register should refresh TTL
        await register_game_routing(redis, "GAME1234", "worker1")
        ttl_after = await redis.ttl("game:GAME1234:server")
        assert ttl_after > 100


class TestGetGameServer:
    """Tests for get_game_server."""

    @pytest.mark.asyncio
    async def test_get_existing_game(self, redis) -> None:
        """Get returns the server_id for a registered game."""
        await register_game_routing(redis, "GAME1234", "worker1")

        result = await get_game_server(redis, "GAME1234")
        assert result == "worker1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_game(self, redis) -> None:
        """Get returns None for an unregistered game."""
        result = await get_game_server(redis, "NOTEXIST")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_different_games(self, redis) -> None:
        """Different games can be on different servers."""
        await register_game_routing(redis, "GAME1111", "worker1")
        await register_game_routing(redis, "GAME2222", "worker2")

        assert await get_game_server(redis, "GAME1111") == "worker1"
        assert await get_game_server(redis, "GAME2222") == "worker2"


class TestDeleteGameRouting:
    """Tests for delete_game_routing."""

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, redis) -> None:
        """Deleting a routing entry removes it."""
        await register_game_routing(redis, "GAME1234", "worker1")
        await delete_game_routing(redis, "GAME1234")

        result = await get_game_server(redis, "GAME1234")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_noop(self, redis) -> None:
        """Deleting a missing key doesn't raise."""
        await delete_game_routing(redis, "NOTEXIST")  # Should not raise

    @pytest.mark.asyncio
    async def test_delete_doesnt_affect_other_keys(self, redis) -> None:
        """Deleting one game doesn't affect others."""
        await register_game_routing(redis, "GAME1111", "worker1")
        await register_game_routing(redis, "GAME2222", "worker2")

        await delete_game_routing(redis, "GAME1111")

        assert await get_game_server(redis, "GAME1111") is None
        assert await get_game_server(redis, "GAME2222") == "worker2"

    @pytest.mark.asyncio
    async def test_delete_doesnt_affect_snapshot(self, redis) -> None:
        """Deleting routing doesn't affect snapshot key."""
        await register_game_routing(redis, "GAME1234", "worker1")
        await redis.set("game:GAME1234:snapshot", '{"data": "test"}', ex=7200)

        await delete_game_routing(redis, "GAME1234")

        # Routing gone, snapshot still there
        assert await get_game_server(redis, "GAME1234") is None
        assert await redis.get("game:GAME1234:snapshot") is not None


class TestRegisterRoutingFireAndForget:
    """Tests for register_routing_fire_and_forget."""

    @pytest.mark.asyncio
    async def test_fire_and_forget_writes_to_redis(self) -> None:
        """Fire-and-forget registers the routing key in Redis."""
        mock_redis = AsyncMock()

        with (
            patch("kfchess.redis.routing.get_redis", return_value=mock_redis),
            patch(
                "kfchess.redis.routing.get_settings",
                return_value=MagicMock(effective_server_id="worker1"),
            ),
        ):
            register_routing_fire_and_forget("FF_GAME1")
            await asyncio.sleep(0.05)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "game:FF_GAME1:server"
        assert call_args[0][1] == "worker1"

    @pytest.mark.asyncio
    async def test_fire_and_forget_error_does_not_propagate(self) -> None:
        """Redis error in fire-and-forget doesn't crash."""
        with patch(
            "kfchess.redis.routing.get_redis",
            side_effect=ConnectionError("Redis down"),
        ):
            register_routing_fire_and_forget("FF_ERR01")
            await asyncio.sleep(0.05)
            # Should not raise — error is logged and swallowed

    @pytest.mark.asyncio
    async def test_fire_and_forget_uses_effective_server_id(self) -> None:
        """Fire-and-forget uses the effective_server_id from settings."""
        mock_redis = AsyncMock()

        with (
            patch("kfchess.redis.routing.get_redis", return_value=mock_redis),
            patch(
                "kfchess.redis.routing.get_settings",
                return_value=MagicMock(effective_server_id="custom-server-42"),
            ),
        ):
            register_routing_fire_and_forget("FF_SID01")
            await asyncio.sleep(0.05)

        call_args = mock_redis.set.call_args
        assert call_args[0][1] == "custom-server-42"

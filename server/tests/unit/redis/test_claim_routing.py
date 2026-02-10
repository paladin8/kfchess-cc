"""Tests for Redis CAS game routing claim."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from kfchess.redis.routing import (
    ROUTING_TTL_SECONDS,
    claim_game_routing,
    get_game_server,
    register_game_routing,
)


@pytest.fixture
def redis():
    """Create a fakeredis async client with Lua support."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestClaimGameRouting:
    """Tests for atomic CAS game routing claim."""

    @pytest.mark.asyncio
    async def test_claim_succeeds_when_expected_matches(self, redis) -> None:
        """CAS succeeds when current owner matches expected."""
        await register_game_routing(redis, "GAME0001", "dead-server")

        result = await claim_game_routing(
            redis, "GAME0001", "dead-server", "new-server"
        )

        assert result is True
        assert await get_game_server(redis, "GAME0001") == "new-server"

    @pytest.mark.asyncio
    async def test_claim_fails_when_different_owner(self, redis) -> None:
        """CAS fails when current owner doesn't match expected."""
        await register_game_routing(redis, "GAME0001", "other-server")

        result = await claim_game_routing(
            redis, "GAME0001", "dead-server", "new-server"
        )

        assert result is False
        # Value should be unchanged
        assert await get_game_server(redis, "GAME0001") == "other-server"

    @pytest.mark.asyncio
    async def test_claim_fails_on_missing_key(self, redis) -> None:
        """CAS fails when the routing key doesn't exist."""
        result = await claim_game_routing(
            redis, "GAME0001", "dead-server", "new-server"
        )

        assert result is False
        assert await get_game_server(redis, "GAME0001") is None

    @pytest.mark.asyncio
    async def test_claim_sets_ttl(self, redis) -> None:
        """Successful CAS sets the TTL on the routing key."""
        await register_game_routing(redis, "GAME0001", "dead-server")

        await claim_game_routing(redis, "GAME0001", "dead-server", "new-server")

        ttl = await redis.ttl("game:GAME0001:server")
        assert 0 < ttl <= ROUTING_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_claim_preserves_ttl_on_failure(self, redis) -> None:
        """Failed CAS doesn't modify the key's TTL."""
        await register_game_routing(redis, "GAME0001", "other-server")
        ttl_before = await redis.ttl("game:GAME0001:server")

        await claim_game_routing(redis, "GAME0001", "dead-server", "new-server")

        ttl_after = await redis.ttl("game:GAME0001:server")
        # TTL should be roughly the same (within 1 second)
        assert abs(ttl_after - ttl_before) <= 1

    @pytest.mark.asyncio
    async def test_claim_is_atomic_concurrent(self, redis) -> None:
        """Two concurrent claims — exactly one succeeds."""
        await register_game_routing(redis, "GAME0001", "dead-server")

        result1, result2 = await asyncio.gather(
            claim_game_routing(redis, "GAME0001", "dead-server", "server-A"),
            claim_game_routing(redis, "GAME0001", "dead-server", "server-B"),
        )

        # Exactly one should succeed
        assert (result1 is True) != (result2 is True), (
            f"Expected exactly one success, got result1={result1}, result2={result2}"
        )

        # The winner should own the key
        owner = await get_game_server(redis, "GAME0001")
        if result1:
            assert owner == "server-A"
        else:
            assert owner == "server-B"

    @pytest.mark.asyncio
    async def test_claim_empty_expected_matches_empty_value(self, redis) -> None:
        """CAS with expected='' matches a key set to ''."""
        await redis.set("game:GAME0001:server", "", ex=7200)

        result = await claim_game_routing(redis, "GAME0001", "", "new-server")

        assert result is True
        assert await get_game_server(redis, "GAME0001") == "new-server"

    @pytest.mark.asyncio
    async def test_claim_different_games_independent(self, redis) -> None:
        """Claims on different games don't interfere."""
        await register_game_routing(redis, "GAME0001", "dead-server")
        await register_game_routing(redis, "GAME0002", "dead-server")

        result1 = await claim_game_routing(
            redis, "GAME0001", "dead-server", "server-A"
        )
        result2 = await claim_game_routing(
            redis, "GAME0002", "dead-server", "server-B"
        )

        assert result1 is True
        assert result2 is True
        assert await get_game_server(redis, "GAME0001") == "server-A"
        assert await get_game_server(redis, "GAME0002") == "server-B"

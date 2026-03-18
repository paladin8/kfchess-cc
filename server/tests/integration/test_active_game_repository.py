"""Integration tests for ActiveGameRepository.

These tests hit the real PostgreSQL database to catch issues like:
- JSON serialization of player data
- Filtering correctness (speed, player_count, game_type)
- Stale cleanup with datetime comparisons
- Server-based cleanup
- Constraint violations

Run with: uv run pytest tests/integration/test_active_game_repository.py -v
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.db.models import ActiveGame
from kfchess.db.repositories.active_games import ActiveGameRepository

from .conftest import generate_test_id


def _make_players(count: int = 2) -> list[dict]:
    """Build a sample players list."""
    players = []
    for i in range(1, count + 1):
        players.append({"slot": i, "username": f"player{i}", "is_ai": i > 1})
    return players


class TestRegister:
    """Tests for registering active games."""

    @pytest.mark.asyncio
    async def test_register_quickplay(self, db_session: AsyncSession):
        game_id = generate_test_id()
        try:
            repo = ActiveGameRepository(db_session)
            await repo.register(
                game_id=game_id,
                game_type="quickplay",
                speed="standard",
                player_count=2,
                board_type="standard",
                players=_make_players(),
                server_id="test-server",
            )
            await db_session.commit()

            # Verify it's in the list
            games = await repo.list_active()
            game_ids = [g.game_id for g in games]
            assert game_id in game_ids

            # Verify fields
            game = next(g for g in games if g.game_id == game_id)
            assert game.game_type == "quickplay"
            assert game.speed == "standard"
            assert game.player_count == 2
            assert game.board_type == "standard"
            assert game.server_id == "test-server"
            assert game.lobby_code is None
            assert game.campaign_level_id is None
            assert game.started_at is not None
        finally:
            await repo.deregister(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_register_lobby_game(self, db_session: AsyncSession):
        game_id = generate_test_id()
        try:
            repo = ActiveGameRepository(db_session)
            await repo.register(
                game_id=game_id,
                game_type="lobby",
                speed="lightning",
                player_count=4,
                board_type="four_player",
                players=_make_players(4),
                server_id="test-server",
                lobby_code="ABC123",
            )
            await db_session.commit()

            games = await repo.list_active()
            game = next(g for g in games if g.game_id == game_id)
            assert game.game_type == "lobby"
            assert game.lobby_code == "ABC123"
            assert game.player_count == 4
            assert game.board_type == "four_player"
        finally:
            await repo.deregister(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_register_campaign_game(self, db_session: AsyncSession):
        game_id = generate_test_id()
        try:
            repo = ActiveGameRepository(db_session)
            await repo.register(
                game_id=game_id,
                game_type="campaign",
                speed="standard",
                player_count=2,
                board_type="standard",
                players=[{"slot": 1, "username": "hero", "is_ai": False}],
                server_id="test-server",
                campaign_level_id=5,
            )
            await db_session.commit()

            games = await repo.list_active()
            game = next(g for g in games if g.game_id == game_id)
            assert game.game_type == "campaign"
            assert game.campaign_level_id == 5
        finally:
            await repo.deregister(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_register_with_timezone_aware_started_at(self, db_session: AsyncSession):
        """Restored games pass a tz-aware started_at from the snapshot.

        The DB column is TIMESTAMP WITHOUT TIME ZONE, so the repository must
        strip tzinfo to avoid asyncpg's "can't subtract offset-naive and
        offset-aware datetimes" error.
        """
        game_id = generate_test_id()
        tz_aware_dt = datetime(2026, 2, 11, 20, 59, 50, 151296, tzinfo=UTC)
        try:
            repo = ActiveGameRepository(db_session)
            await repo.register(
                game_id=game_id,
                game_type="restored",
                speed="standard",
                player_count=2,
                board_type="standard",
                players=_make_players(),
                server_id="test-server",
                started_at=tz_aware_dt,
            )
            await db_session.commit()

            # Query directly by game_id to avoid list_active()'s limit=50
            # excluding old started_at values
            result = await db_session.execute(
                select(ActiveGame).where(ActiveGame.game_id == game_id)
            )
            game = result.scalar_one()
            assert game.started_at == tz_aware_dt.replace(tzinfo=None)
        finally:
            await repo.deregister(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_register_preserves_player_json(self, db_session: AsyncSession):
        """Verify that player data round-trips through JSON correctly."""
        game_id = generate_test_id()
        players = [
            {"slot": 1, "username": "user:abc_123-def", "is_ai": False},
            {"slot": 2, "username": "Bot (novice)", "is_ai": True},
        ]
        try:
            repo = ActiveGameRepository(db_session)
            await repo.register(
                game_id=game_id,
                game_type="quickplay",
                speed="standard",
                player_count=2,
                board_type="standard",
                players=players,
                server_id="test-server",
            )
            await db_session.commit()

            games = await repo.list_active()
            game = next(g for g in games if g.game_id == game_id)
            assert game.players == players
        finally:
            await repo.deregister(game_id)
            await db_session.commit()


class TestDeregister:
    """Tests for deregistering active games."""

    @pytest.mark.asyncio
    async def test_deregister_existing(self, db_session: AsyncSession):
        game_id = generate_test_id()
        repo = ActiveGameRepository(db_session)
        await repo.register(
            game_id=game_id,
            game_type="quickplay",
            speed="standard",
            player_count=2,
            board_type="standard",
            players=_make_players(),
            server_id="test-server",
        )
        await db_session.commit()

        removed = await repo.deregister(game_id)
        await db_session.commit()

        assert removed is True

        # Verify it's gone
        games = await repo.list_active()
        game_ids = [g.game_id for g in games]
        assert game_id not in game_ids

    @pytest.mark.asyncio
    async def test_deregister_nonexistent(self, db_session: AsyncSession):
        repo = ActiveGameRepository(db_session)
        removed = await repo.deregister("nonexistent-game-id")
        assert removed is False

    @pytest.mark.asyncio
    async def test_deregister_idempotent(self, db_session: AsyncSession):
        """Deregistering the same game twice should not fail."""
        game_id = generate_test_id()
        repo = ActiveGameRepository(db_session)
        await repo.register(
            game_id=game_id,
            game_type="quickplay",
            speed="standard",
            player_count=2,
            board_type="standard",
            players=_make_players(),
            server_id="test-server",
        )
        await db_session.commit()

        assert await repo.deregister(game_id) is True
        await db_session.commit()
        assert await repo.deregister(game_id) is False


class TestListActive:
    """Tests for listing active games with filters."""

    @pytest.mark.asyncio
    async def test_list_empty(self, db_session: AsyncSession):
        """Listing when no games are registered returns empty list."""
        repo = ActiveGameRepository(db_session)
        # Use a unique game_type filter to avoid seeing other test data
        games = await repo.list_active(game_type="nonexistent_type_xyz")
        assert games == []

    @pytest.mark.asyncio
    async def test_list_ordered_by_started_at_desc(self, db_session: AsyncSession):
        """Games should be returned newest first."""
        ids = [generate_test_id() for _ in range(3)]
        repo = ActiveGameRepository(db_session)
        try:
            # Use future timestamps so these games always appear in the
            # top 50 results of list_active() (ordered by started_at DESC)
            base = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
            for i, gid in enumerate(ids):
                await repo.register(
                    game_id=gid,
                    game_type="quickplay",
                    speed="standard",
                    player_count=2,
                    board_type="standard",
                    players=_make_players(),
                    server_id="test-order",
                )
                await db_session.flush()
                # Manually set started_at to control ordering
                await db_session.execute(
                    update(ActiveGame)
                    .where(ActiveGame.game_id == gid)
                    .values(started_at=base + timedelta(minutes=i))
                )
            await db_session.commit()

            games = await repo.list_active()
            # Filter to just our test games
            our_games = [g for g in games if g.game_id in ids]
            assert len(our_games) == 3
            # Newest first (i=2 -> latest datetime)
            assert our_games[0].game_id == ids[2]
            assert our_games[1].game_id == ids[1]
            assert our_games[2].game_id == ids[0]
        finally:
            for gid in ids:
                await repo.deregister(gid)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_speed(self, db_session: AsyncSession):
        ids = [generate_test_id() for _ in range(2)]
        repo = ActiveGameRepository(db_session)
        try:
            await repo.register(
                game_id=ids[0], game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await repo.register(
                game_id=ids[1], game_type="quickplay", speed="lightning",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await db_session.commit()

            standard_games = await repo.list_active(speed="standard")
            standard_ids = [g.game_id for g in standard_games]
            assert ids[0] in standard_ids
            assert ids[1] not in standard_ids

            lightning_games = await repo.list_active(speed="lightning")
            lightning_ids = [g.game_id for g in lightning_games]
            assert ids[1] in lightning_ids
            assert ids[0] not in lightning_ids
        finally:
            for gid in ids:
                await repo.deregister(gid)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_player_count(self, db_session: AsyncSession):
        ids = [generate_test_id() for _ in range(2)]
        repo = ActiveGameRepository(db_session)
        try:
            await repo.register(
                game_id=ids[0], game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(2), server_id="test-filter",
            )
            await repo.register(
                game_id=ids[1], game_type="lobby", speed="standard",
                player_count=4, board_type="four_player",
                players=_make_players(4), server_id="test-filter",
            )
            await db_session.commit()

            two_player = await repo.list_active(player_count=2)
            two_ids = [g.game_id for g in two_player]
            assert ids[0] in two_ids
            assert ids[1] not in two_ids
        finally:
            for gid in ids:
                await repo.deregister(gid)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_game_type(self, db_session: AsyncSession):
        ids = [generate_test_id() for _ in range(3)]
        repo = ActiveGameRepository(db_session)
        try:
            await repo.register(
                game_id=ids[0], game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await repo.register(
                game_id=ids[1], game_type="lobby", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await repo.register(
                game_id=ids[2], game_type="campaign", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await db_session.commit()

            lobby_games = await repo.list_active(game_type="lobby")
            lobby_ids = [g.game_id for g in lobby_games]
            assert ids[1] in lobby_ids
            assert ids[0] not in lobby_ids
            assert ids[2] not in lobby_ids
        finally:
            for gid in ids:
                await repo.deregister(gid)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_filter_combined(self, db_session: AsyncSession):
        """Multiple filters should combine with AND."""
        ids = [generate_test_id() for _ in range(3)]
        repo = ActiveGameRepository(db_session)
        try:
            await repo.register(
                game_id=ids[0], game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await repo.register(
                game_id=ids[1], game_type="quickplay", speed="lightning",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await repo.register(
                game_id=ids[2], game_type="lobby", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-filter",
            )
            await db_session.commit()

            games = await repo.list_active(game_type="quickplay", speed="standard")
            game_ids = [g.game_id for g in games]
            assert ids[0] in game_ids
            assert ids[1] not in game_ids  # wrong speed
            assert ids[2] not in game_ids  # wrong game_type
        finally:
            for gid in ids:
                await repo.deregister(gid)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_limit(self, db_session: AsyncSession):
        ids = [generate_test_id() for _ in range(5)]
        repo = ActiveGameRepository(db_session)
        try:
            for gid in ids:
                await repo.register(
                    game_id=gid, game_type="quickplay", speed="standard",
                    player_count=2, board_type="standard",
                    players=_make_players(), server_id="test-limit",
                )
            await db_session.commit()

            games = await repo.list_active(limit=3)
            # May include other games from parallel tests, but should be <= 3
            assert len(games) <= 3
        finally:
            for gid in ids:
                await repo.deregister(gid)
            await db_session.commit()


class TestCleanupStale:
    """Tests for cleaning up stale entries."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_entries(self, db_session: AsyncSession):
        """Entries older than max_age_hours should be removed."""
        old_id = generate_test_id()
        new_id = generate_test_id()
        repo = ActiveGameRepository(db_session)
        try:
            # Register both games
            await repo.register(
                game_id=old_id, game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-stale",
            )
            await repo.register(
                game_id=new_id, game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-stale",
            )
            await db_session.flush()

            # Backdate the old game to 3 hours ago
            three_hours_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=3)
            await db_session.execute(
                update(ActiveGame)
                .where(ActiveGame.game_id == old_id)
                .values(started_at=three_hours_ago)
            )
            await db_session.commit()

            # Cleanup with 2-hour threshold
            count = await repo.cleanup_stale(max_age_hours=2)
            await db_session.commit()

            assert count >= 1

            # Old game should be gone, new game should remain
            games = await repo.list_active()
            game_ids = [g.game_id for g in games]
            assert old_id not in game_ids
            assert new_id in game_ids
        finally:
            await repo.deregister(new_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_entries(self, db_session: AsyncSession):
        """Entries newer than max_age_hours should be preserved."""
        game_id = generate_test_id()
        repo = ActiveGameRepository(db_session)
        try:
            await repo.register(
                game_id=game_id, game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="test-stale",
            )
            await db_session.commit()

            await repo.cleanup_stale(max_age_hours=2)
            await db_session.commit()

            # The game we just registered should not be cleaned up
            games = await repo.list_active()
            game_ids = [g.game_id for g in games]
            assert game_id in game_ids
        finally:
            await repo.deregister(game_id)
            await db_session.commit()


class TestCleanupByServer:
    """Tests for server-based cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_all_games_for_server(self, db_session: AsyncSession):
        ids = [generate_test_id() for _ in range(3)]
        other_id = generate_test_id()
        repo = ActiveGameRepository(db_session)
        try:
            # Register games on target server
            for gid in ids:
                await repo.register(
                    game_id=gid, game_type="quickplay", speed="standard",
                    player_count=2, board_type="standard",
                    players=_make_players(), server_id="server-to-clean",
                )
            # Register game on different server
            await repo.register(
                game_id=other_id, game_type="quickplay", speed="standard",
                player_count=2, board_type="standard",
                players=_make_players(), server_id="other-server",
            )
            await db_session.commit()

            count = await repo.cleanup_by_server("server-to-clean")
            await db_session.commit()

            assert count == 3

            games = await repo.list_active()
            game_ids = [g.game_id for g in games]
            for gid in ids:
                assert gid not in game_ids
            assert other_id in game_ids
        finally:
            await repo.deregister(other_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_server(self, db_session: AsyncSession):
        repo = ActiveGameRepository(db_session)
        count = await repo.cleanup_by_server("nonexistent-server-xyz")
        assert count == 0

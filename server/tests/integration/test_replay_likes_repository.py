"""Integration tests for ReplayLikesRepository and like-related ReplayRepository methods.

These tests verify the like system works correctly with the real database.

Run with: uv run pytest tests/integration/test_replay_likes_repository.py -v
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.db.models import User
from kfchess.db.repositories.replay_likes import ReplayLikesRepository
from kfchess.db.repositories.replays import ReplayRepository
from kfchess.game.board import BoardType
from kfchess.game.replay import Replay
from kfchess.game.state import Speed

from .conftest import generate_test_id


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for like tests."""
    user = User(
        email="like_test_user@example.com",
        hashed_password="test_hash",
        is_active=True,
        is_verified=True,
        username="LikeTestUser",
        ratings={},
    )
    db_session.add(user)
    await db_session.flush()

    yield user

    await db_session.delete(user)
    await db_session.commit()


@pytest.fixture
async def test_users(db_session: AsyncSession) -> tuple[User, User]:
    """Create two test users for like tests."""
    user1 = User(
        email="like_test_user1@example.com",
        hashed_password="test_hash_1",
        is_active=True,
        is_verified=True,
        username="LikeTestUser1",
        ratings={},
    )
    user2 = User(
        email="like_test_user2@example.com",
        hashed_password="test_hash_2",
        is_active=True,
        is_verified=True,
        username="LikeTestUser2",
        ratings={},
    )
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    yield user1, user2

    await db_session.delete(user1)
    await db_session.delete(user2)
    await db_session.commit()


def create_test_replay() -> Replay:
    """Create a minimal replay for testing."""
    return Replay(
        version=2,
        speed=Speed.STANDARD,
        board_type=BoardType.STANDARD,
        players={1: "player1", 2: "player2"},
        moves=[],
        total_ticks=100,
        winner=1,
        win_reason="king_captured",
        created_at=datetime.now(UTC),
    )


class TestReplayLikesRepositoryLike:
    """Tests for the like operation."""

    @pytest.mark.asyncio
    async def test_like_replay(self, db_session: AsyncSession, test_user: User):
        """Test liking a replay."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            # Create a replay first
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Like it
            added = await likes_repo.like(game_id, test_user.id)
            await db_session.commit()

            assert added is True

            # Verify like count increased
            like_count = await replay_repo.get_like_count(game_id)
            assert like_count == 1
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_like_idempotent(self, db_session: AsyncSession, test_user: User):
        """Test that liking twice doesn't increase count."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Like twice
            added1 = await likes_repo.like(game_id, test_user.id)
            await db_session.commit()
            added2 = await likes_repo.like(game_id, test_user.id)
            await db_session.commit()

            assert added1 is True
            assert added2 is False  # Second attempt should return False

            # Count should still be 1
            like_count = await replay_repo.get_like_count(game_id)
            assert like_count == 1
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_multiple_users_can_like(
        self, db_session: AsyncSession, test_users: tuple[User, User]
    ):
        """Test that multiple users can like the same replay."""
        user1, user2 = test_users
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            await likes_repo.like(game_id, user1.id)
            await db_session.commit()
            await likes_repo.like(game_id, user2.id)
            await db_session.commit()

            like_count = await replay_repo.get_like_count(game_id)
            assert like_count == 2
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()


class TestReplayLikesRepositoryUnlike:
    """Tests for the unlike operation."""

    @pytest.mark.asyncio
    async def test_unlike_replay(self, db_session: AsyncSession, test_user: User):
        """Test unliking a replay."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Like then unlike
            await likes_repo.like(game_id, test_user.id)
            await db_session.commit()

            removed = await likes_repo.unlike(game_id, test_user.id)
            await db_session.commit()

            assert removed is True

            # Count should be 0
            like_count = await replay_repo.get_like_count(game_id)
            assert like_count == 0
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_unlike_idempotent(self, db_session: AsyncSession, test_user: User):
        """Test that unliking when not liked returns False."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Unlike without liking first
            removed = await likes_repo.unlike(game_id, test_user.id)
            await db_session.commit()

            assert removed is False

            # Count should still be 0
            like_count = await replay_repo.get_like_count(game_id)
            assert like_count == 0
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_unlike_does_not_go_negative(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that like count never goes negative."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Multiple unlikes should not make count negative
            for _ in range(5):
                await likes_repo.unlike(game_id, test_user.id)
                await db_session.commit()

            like_count = await replay_repo.get_like_count(game_id)
            assert like_count == 0
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()


class TestReplayLikesRepositoryHasLiked:
    """Tests for checking like status."""

    @pytest.mark.asyncio
    async def test_has_liked_true(self, db_session: AsyncSession, test_user: User):
        """Test has_liked returns True when user has liked."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            await likes_repo.like(game_id, test_user.id)
            await db_session.commit()

            has_liked = await likes_repo.has_liked(game_id, test_user.id)
            assert has_liked is True
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_has_liked_false(self, db_session: AsyncSession, test_user: User):
        """Test has_liked returns False when user has not liked."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            has_liked = await likes_repo.has_liked(game_id, test_user.id)
            assert has_liked is False
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()


class TestReplayLikesRepositoryBatch:
    """Tests for batch operations."""

    @pytest.mark.asyncio
    async def test_get_likes_for_replays(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test batch fetching like status for multiple replays."""
        game_ids = [generate_test_id() for _ in range(3)]
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            # Create replays
            for game_id in game_ids:
                await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Like only the first and third
            await likes_repo.like(game_ids[0], test_user.id)
            await likes_repo.like(game_ids[2], test_user.id)
            await db_session.commit()

            # Check batch status
            statuses = await likes_repo.get_likes_for_replays(game_ids, test_user.id)

            assert statuses[game_ids[0]] is True
            assert statuses[game_ids[1]] is False
            assert statuses[game_ids[2]] is True
        finally:
            for game_id in game_ids:
                await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_get_likes_for_replays_no_user(self, db_session: AsyncSession):
        """Test batch fetch with None user returns all False."""
        game_ids = [generate_test_id() for _ in range(2)]
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            for game_id in game_ids:
                await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            statuses = await likes_repo.get_likes_for_replays(game_ids, None)

            assert statuses[game_ids[0]] is False
            assert statuses[game_ids[1]] is False
        finally:
            for game_id in game_ids:
                await replay_repo.delete(game_id)
            await db_session.commit()


class TestReplayRepositoryLikeCounts:
    """Tests for ReplayRepository like count methods."""

    @pytest.mark.asyncio
    async def test_get_like_count(self, db_session: AsyncSession, test_user: User):
        """Test get_like_count returns correct count."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # Initial count should be 0
            assert await replay_repo.get_like_count(game_id) == 0

            await likes_repo.like(game_id, test_user.id)
            await db_session.commit()

            # Count should be 1
            assert await replay_repo.get_like_count(game_id) == 1
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_get_like_count_nonexistent(self, db_session: AsyncSession):
        """Test get_like_count returns 0 for nonexistent replay."""
        replay_repo = ReplayRepository(db_session)
        count = await replay_repo.get_like_count("NONEXISTENT")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_like_counts_batch(
        self, db_session: AsyncSession, test_users: tuple[User, User]
    ):
        """Test batch fetching like counts."""
        user1, user2 = test_users
        game_ids = [generate_test_id() for _ in range(3)]
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            for game_id in game_ids:
                await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # First replay: 2 likes, second: 0 likes, third: 1 like
            await likes_repo.like(game_ids[0], user1.id)
            await likes_repo.like(game_ids[0], user2.id)
            await likes_repo.like(game_ids[2], user1.id)
            await db_session.commit()

            counts = await replay_repo.get_like_counts_batch(game_ids)

            assert counts[game_ids[0]] == 2
            assert counts[game_ids[1]] == 0
            assert counts[game_ids[2]] == 1
        finally:
            for game_id in game_ids:
                await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_get_like_counts_batch_empty(self, db_session: AsyncSession):
        """Test batch fetch with empty list."""
        replay_repo = ReplayRepository(db_session)
        counts = await replay_repo.get_like_counts_batch([])
        assert counts == {}


class TestReplayRepositoryListTop:
    """Tests for the list_top method."""

    @pytest.mark.asyncio
    async def test_list_top_orders_by_likes(
        self, db_session: AsyncSession, test_users: tuple[User, User]
    ):
        """Test that list_top returns replays ordered by like count."""
        user1, user2 = test_users
        game_ids = [generate_test_id() for _ in range(3)]
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        try:
            for game_id in game_ids:
                await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            # game_ids[1] gets most likes (2), game_ids[2] gets 1, game_ids[0] gets 0
            await likes_repo.like(game_ids[1], user1.id)
            await likes_repo.like(game_ids[1], user2.id)
            await likes_repo.like(game_ids[2], user1.id)
            await db_session.commit()

            # List top replays
            top_replays, total = await replay_repo.list_top(limit=10)

            # Should only include replays with likes > 0, ordered by like count
            assert len(top_replays) >= 2
            assert total >= 2

            # Find our test replays in results
            result_ids = [r[0] for r in top_replays]

            # game_ids[1] (2 likes) should come before game_ids[2] (1 like)
            if game_ids[1] in result_ids and game_ids[2] in result_ids:
                idx1 = result_ids.index(game_ids[1])
                idx2 = result_ids.index(game_ids[2])
                assert idx1 < idx2

            # game_ids[0] (0 likes) should not be in results
            assert game_ids[0] not in result_ids
        finally:
            for game_id in game_ids:
                await replay_repo.delete(game_id)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_list_top_excludes_zero_likes(self, db_session: AsyncSession):
        """Test that list_top excludes replays with 0 likes."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)

        try:
            await replay_repo.save(game_id, create_test_replay())
            await db_session.commit()

            top_replays, _total = await replay_repo.list_top(limit=10)
            result_ids = [r[0] for r in top_replays]

            assert game_id not in result_ids
        finally:
            await replay_repo.delete(game_id)
            await db_session.commit()


class TestReplayLikesCascadeDelete:
    """Tests for cascade delete behavior."""

    @pytest.mark.asyncio
    async def test_deleting_replay_removes_likes(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that deleting a replay removes associated likes."""
        game_id = generate_test_id()
        replay_repo = ReplayRepository(db_session)
        likes_repo = ReplayLikesRepository(db_session)

        # Create replay and like it
        await replay_repo.save(game_id, create_test_replay())
        await db_session.commit()

        await likes_repo.like(game_id, test_user.id)
        await db_session.commit()

        # Verify like exists
        assert await likes_repo.has_liked(game_id, test_user.id) is True

        # Delete replay (should cascade delete likes)
        await replay_repo.delete(game_id)
        await db_session.commit()

        # Like should be gone (query should not fail)
        assert await likes_repo.has_liked(game_id, test_user.id) is False

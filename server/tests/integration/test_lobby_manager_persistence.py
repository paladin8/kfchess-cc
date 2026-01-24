"""Integration tests for LobbyManager with database persistence.

These tests verify the end-to-end flow:
- Create lobby via manager -> persisted to DB
- Join lobby -> player added to DB
- Leave lobby -> player removed from DB
- Delete lobby -> removed from DB

Run with: uv run pytest tests/integration/test_lobby_manager_persistence.py -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kfchess.db.repositories.lobbies import LobbyRepository
from kfchess.lobby.manager import LobbyManager
from kfchess.lobby.models import LobbySettings, LobbyStatus
from kfchess.settings import get_settings


@pytest.fixture
async def session_factory():
    """Create a session factory for the manager."""
    engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        pool_pre_ping=True,
    )

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield factory

    await engine.dispose()


@pytest.fixture
async def manager(session_factory):
    """Create a LobbyManager with database persistence."""
    return LobbyManager(session_factory=session_factory)


@pytest.fixture
async def db_session(session_factory):
    """Create a database session for verification."""
    async with session_factory() as session:
        yield session


class TestLobbyManagerPersistence:
    """Integration tests for LobbyManager with persistence."""

    @pytest.mark.asyncio
    async def test_create_lobby_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that creating a lobby saves it to the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="TestHost",
            player_id="guest:test123",
        )

        assert not isinstance(result, tuple) or len(result) == 2
        lobby, _ = result
        code = lobby.code

        try:
            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert db_lobby.code == code
            assert db_lobby.status == LobbyStatus.WAITING
            assert len(db_lobby.players) == 1
            assert db_lobby.players[1].username == "TestHost"
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_join_lobby_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that joining a lobby updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
        )
        lobby, _ = result
        code = lobby.code

        try:
            # Join the lobby
            join_result = await manager.join_lobby(
                code=code,
                user_id=None,
                username="Player2",
                player_id="guest:player2",
            )

            assert not isinstance(join_result, tuple) or len(join_result) == 3
            lobby, _, slot = join_result
            assert slot == 2

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert len(db_lobby.players) == 2
            assert db_lobby.players[2].username == "Player2"
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_leave_lobby_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that leaving a lobby updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
        )
        lobby, host_key = result
        code = lobby.code

        try:
            # Join the lobby
            join_result = await manager.join_lobby(
                code=code,
                user_id=None,
                username="Player2",
                player_id="guest:player2",
            )
            _, player_key, _ = join_result

            # Leave the lobby
            await manager.leave_lobby(code, player_key, "guest:player2")

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert len(db_lobby.players) == 1
            assert 2 not in db_lobby.players
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_delete_lobby_removes_from_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that deleting a lobby removes it from the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
        )
        lobby, _ = result
        code = lobby.code

        # Verify lobby exists in DB
        repository = LobbyRepository(db_session)
        assert await repository.get_by_code(code) is not None

        # Delete the lobby
        deleted = await manager.delete_lobby(code)
        assert deleted is True

        # Verify removed from DB
        assert await repository.get_by_code(code) is None

    @pytest.mark.asyncio
    async def test_set_ready_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that setting ready state updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
        )
        lobby, host_key = result
        code = lobby.code

        try:
            # Set ready
            await manager.set_ready(code, host_key, True)

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert db_lobby.players[1].is_ready is True
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_update_settings_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that updating settings updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
        )
        lobby, host_key = result
        code = lobby.code

        try:
            # Update settings
            new_settings = LobbySettings(
                is_public=False,
                speed="lightning",
                player_count=4,
            )
            await manager.update_settings(code, host_key, new_settings)

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert db_lobby.settings.is_public is False
            assert db_lobby.settings.speed == "lightning"
            assert db_lobby.settings.player_count == 4
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_add_ai_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that adding AI player updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
        )
        lobby, host_key = result
        code = lobby.code

        try:
            # Add AI
            await manager.add_ai(code, host_key, "bot:dummy")

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert len(db_lobby.players) == 2
            assert db_lobby.players[2].is_ai is True
            assert db_lobby.players[2].ai_type == "bot:dummy"
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_start_game_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that starting a game updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
            add_ai=True,
        )
        lobby, host_key = result
        code = lobby.code

        try:
            # Start game (host is auto-readied)
            start_result = await manager.start_game(code, host_key)
            assert isinstance(start_result, tuple)
            game_id, _ = start_result

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert db_lobby.status == LobbyStatus.IN_GAME
            assert db_lobby.current_game_id == game_id
        finally:
            await manager.delete_lobby(code)

    @pytest.mark.asyncio
    async def test_end_game_persists_to_db(
        self, manager: LobbyManager, db_session: AsyncSession
    ):
        """Test that ending a game updates the database."""
        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
            player_id="guest:host",
            add_ai=True,
        )
        lobby, host_key = result
        code = lobby.code

        try:
            # Start game
            await manager.start_game(code, host_key)

            # End game
            await manager.end_game(code, winner=1)

            # Verify in database
            repository = LobbyRepository(db_session)
            db_lobby = await repository.get_by_code(code)

            assert db_lobby is not None
            assert db_lobby.status == LobbyStatus.FINISHED
        finally:
            await manager.delete_lobby(code)


class TestLobbyManagerWithoutPersistence:
    """Test that manager works without persistence (in-memory only)."""

    @pytest.mark.asyncio
    async def test_create_lobby_without_session_factory(self):
        """Test that manager works without database."""
        manager = LobbyManager()  # No session factory

        result = await manager.create_lobby(
            host_user_id=None,
            host_username="Host",
        )

        lobby, host_key = result
        assert lobby.code is not None
        assert manager.get_lobby(lobby.code) is not None

        # Cleanup
        await manager.delete_lobby(lobby.code)
        assert manager.get_lobby(lobby.code) is None

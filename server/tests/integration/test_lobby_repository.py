"""Integration tests for LobbyRepository.

These tests hit the real PostgreSQL database to verify:
- Lobby creation and persistence
- Player management
- Status transitions
- Cascade deletes

Run with: uv run pytest tests/integration/test_lobby_repository.py -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.db.repositories.lobbies import LobbyRepository
from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus

from .conftest import generate_test_id


def create_test_lobby(
    code: str,
    settings: LobbySettings | None = None,
    players: dict[int, LobbyPlayer] | None = None,
    status: LobbyStatus = LobbyStatus.WAITING,
) -> Lobby:
    """Create a test lobby with sensible defaults.

    Note: The lobby ID (0) is a placeholder. The DB will generate the actual ID.
    """
    if settings is None:
        settings = LobbySettings()
    if players is None:
        players = {
            1: LobbyPlayer(
                slot=1,
                user_id=None,
                username="TestHost",
            )
        }
    return Lobby(
        id=0,  # Placeholder - DB will generate the actual ID
        code=code,
        host_slot=1,
        settings=settings,
        players=players,
        status=status,
    )


class TestLobbyRepositorySave:
    """Integration tests for saving lobbies to PostgreSQL."""

    @pytest.mark.asyncio
    async def test_save_basic_lobby(self, db_session: AsyncSession):
        """Test saving a basic lobby."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        try:
            repository = LobbyRepository(db_session)
            record = await repository.save(lobby)
            await db_session.commit()

            assert record.code == code
            assert record.status == "waiting"
            assert record.is_public is True
            assert record.id > 0  # DB generated ID

            # Verify we can read it back
            loaded = await repository.get_by_code(code)
            assert loaded is not None
            assert loaded.code == code
            assert loaded.status == LobbyStatus.WAITING
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_save_lobby_with_multiple_players(self, db_session: AsyncSession):
        """Test saving a lobby with multiple players."""
        code = generate_test_id()
        players = {
            1: LobbyPlayer(slot=1, user_id=None, username="Host"),
            2: LobbyPlayer(slot=2, user_id=None, username="Player2"),
        }
        lobby = create_test_lobby(code=code, players=players)

        try:
            repository = LobbyRepository(db_session)
            await repository.save(lobby)
            await db_session.commit()

            loaded = await repository.get_by_code(code)
            assert loaded is not None
            assert len(loaded.players) == 2
            assert loaded.players[1].username == "Host"
            assert loaded.players[2].username == "Player2"
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_save_lobby_with_ai_player(self, db_session: AsyncSession):
        """Test saving a lobby with an AI player."""
        code = generate_test_id()
        players = {
            1: LobbyPlayer(slot=1, user_id=None, username="Host"),
            2: LobbyPlayer(
                slot=2,
                user_id=None,
                username="AI (dummy)",
                is_ai=True,
                ai_type="bot:dummy",
            ),
        }
        lobby = create_test_lobby(code=code, players=players)

        try:
            repository = LobbyRepository(db_session)
            await repository.save(lobby)
            await db_session.commit()

            loaded = await repository.get_by_code(code)
            assert loaded is not None
            assert loaded.players[2].is_ai is True
            assert loaded.players[2].ai_type == "bot:dummy"
            assert loaded.players[2].is_ready is True  # AI always ready
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_save_lobby_with_custom_settings(self, db_session: AsyncSession):
        """Test saving a lobby with custom settings."""
        code = generate_test_id()
        settings = LobbySettings(
            is_public=False,
            speed="lightning",
            player_count=4,
            is_ranked=False,
        )
        lobby = create_test_lobby(code=code, settings=settings)

        try:
            repository = LobbyRepository(db_session)
            await repository.save(lobby)
            await db_session.commit()

            loaded = await repository.get_by_code(code)
            assert loaded is not None
            assert loaded.settings.is_public is False
            assert loaded.settings.speed == "lightning"
            assert loaded.settings.player_count == 4
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_update_existing_lobby(self, db_session: AsyncSession):
        """Test updating an existing lobby."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        try:
            repository = LobbyRepository(db_session)
            await repository.save(lobby)
            await db_session.commit()

            # Re-load the lobby to get the DB-generated ID
            lobby = await repository.get_by_code(code)
            assert lobby is not None

            # Modify the lobby
            lobby.status = LobbyStatus.IN_GAME
            lobby.current_game_id = "GAME123"
            await repository.save(lobby)
            await db_session.commit()

            # Verify changes
            loaded = await repository.get_by_code(code)
            assert loaded is not None
            assert loaded.status == LobbyStatus.IN_GAME
            assert loaded.current_game_id == "GAME123"
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()


class TestLobbyRepositoryGet:
    """Integration tests for retrieving lobbies."""

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session: AsyncSession):
        """Test getting a lobby by ID."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        try:
            repository = LobbyRepository(db_session)
            record = await repository.save(lobby)
            await db_session.commit()

            # Use the DB-generated ID
            loaded = await repository.get_by_id(record.id)
            assert loaded is not None
            assert loaded.code == code
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_get_by_code_not_found(self, db_session: AsyncSession):
        """Test getting a nonexistent lobby."""
        repository = LobbyRepository(db_session)
        loaded = await repository.get_by_code("NOTFOUND")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_exists(self, db_session: AsyncSession):
        """Test checking lobby existence."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        try:
            repository = LobbyRepository(db_session)
            record = await repository.save(lobby)
            await db_session.commit()

            # Use the DB-generated ID
            assert await repository.exists(record.id) is True
            assert await repository.exists(9999999) is False
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()


class TestLobbyRepositoryList:
    """Integration tests for listing lobbies."""

    @pytest.mark.asyncio
    async def test_list_public_waiting(self, db_session: AsyncSession):
        """Test listing public waiting lobbies."""
        code1 = generate_test_id()
        code2 = generate_test_id()

        lobby1 = create_test_lobby(code=code1)
        lobby2 = create_test_lobby(
            code=code2,
            settings=LobbySettings(is_public=False),
        )

        try:
            repository = LobbyRepository(db_session)
            await repository.save(lobby1)
            await repository.save(lobby2)
            await db_session.commit()

            lobbies = await repository.list_public_waiting()
            codes = [lobby.code for lobby in lobbies]

            assert code1 in codes  # Public lobby
            assert code2 not in codes  # Private lobby
        finally:
            await repository.delete_by_code(code1)
            await repository.delete_by_code(code2)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_list_public_waiting_filter_by_speed(self, db_session: AsyncSession):
        """Test filtering lobbies by speed."""
        code1 = generate_test_id()
        code2 = generate_test_id()

        lobby1 = create_test_lobby(code=code1)
        lobby2 = create_test_lobby(
            code=code2,
            settings=LobbySettings(speed="lightning"),
        )

        try:
            repository = LobbyRepository(db_session)
            await repository.save(lobby1)
            await repository.save(lobby2)
            await db_session.commit()

            lobbies = await repository.list_public_waiting(speed="lightning")
            codes = [lobby.code for lobby in lobbies]

            assert code1 not in codes  # Standard speed
            assert code2 in codes  # Lightning speed
        finally:
            await repository.delete_by_code(code1)
            await repository.delete_by_code(code2)
            await db_session.commit()


class TestLobbyRepositoryDelete:
    """Integration tests for deleting lobbies."""

    @pytest.mark.asyncio
    async def test_delete_removes_lobby(self, db_session: AsyncSession):
        """Test that delete removes the lobby."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        repository = LobbyRepository(db_session)
        record = await repository.save(lobby)
        await db_session.commit()

        lobby_id = record.id
        assert await repository.exists(lobby_id) is True

        deleted = await repository.delete(lobby_id)
        await db_session.commit()

        assert deleted is True
        assert await repository.exists(lobby_id) is False

    @pytest.mark.asyncio
    async def test_delete_by_code(self, db_session: AsyncSession):
        """Test deleting a lobby by code."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        repository = LobbyRepository(db_session)
        await repository.save(lobby)
        await db_session.commit()

        deleted = await repository.delete_by_code(code)
        await db_session.commit()

        assert deleted is True
        assert await repository.get_by_code(code) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db_session: AsyncSession):
        """Test deleting a nonexistent lobby."""
        repository = LobbyRepository(db_session)
        deleted = await repository.delete(9999)
        assert deleted is False


class TestLobbyRepositoryStatusTransitions:
    """Integration tests for lobby status changes."""

    @pytest.mark.asyncio
    async def test_update_status_to_in_game(self, db_session: AsyncSession):
        """Test transitioning lobby to IN_GAME status."""
        code = generate_test_id()
        lobby = create_test_lobby(code=code)

        try:
            repository = LobbyRepository(db_session)
            record = await repository.save(lobby)
            await db_session.commit()

            lobby_id = record.id
            updated = await repository.update_status(
                lobby_id,
                LobbyStatus.IN_GAME,
                game_id="GAME456",
            )
            await db_session.commit()

            assert updated is True

            loaded = await repository.get_by_id(lobby_id)
            assert loaded is not None
            assert loaded.status == LobbyStatus.IN_GAME
            assert loaded.current_game_id == "GAME456"
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_update_status_to_finished(self, db_session: AsyncSession):
        """Test transitioning lobby to FINISHED status."""
        code = generate_test_id()
        lobby = create_test_lobby(
            code=code,
            status=LobbyStatus.IN_GAME,
        )
        lobby.current_game_id = "GAME789"

        try:
            repository = LobbyRepository(db_session)
            record = await repository.save(lobby)
            await db_session.commit()

            lobby_id = record.id
            updated = await repository.update_status(lobby_id, LobbyStatus.FINISHED)
            await db_session.commit()

            assert updated is True

            loaded = await repository.get_by_id(lobby_id)
            assert loaded is not None
            assert loaded.status == LobbyStatus.FINISHED
        finally:
            await repository.delete_by_code(code)
            await db_session.commit()

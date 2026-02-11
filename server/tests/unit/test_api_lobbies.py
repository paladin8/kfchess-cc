"""Tests for the lobbies API endpoints."""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import patch

import pytest
from fakeredis import FakeRedis as SyncFakeRedis
from fakeredis import FakeServer
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from kfchess.lobby.manager import reset_lobby_manager
from kfchess.main import app
from kfchess.services.game_service import get_game_service

_fake_server = FakeServer()


async def _fake_get_redis() -> FakeRedis:
    return FakeRedis(server=_fake_server, decode_responses=True, version=(7,))


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_state() -> Generator[None, None, None]:
    """Clear lobbies and games before each test."""
    global _fake_server
    _fake_server = FakeServer()

    reset_lobby_manager()
    service = get_game_service()
    service.games.clear()

    with (
        patch("kfchess.redis.lobby_store.get_redis", _fake_get_redis),
        patch("kfchess.ws.lobby_handler.get_redis", _fake_get_redis),
    ):
        yield


class TestCreateLobby:
    """Tests for POST /api/lobbies."""

    def test_create_lobby_default(self, client: TestClient) -> None:
        """Test creating a lobby with defaults."""
        response = client.post(
            "/api/lobbies",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "code" in data
        assert "playerKey" in data
        assert data["slot"] == 1
        assert "lobby" in data
        lobby = data["lobby"]
        assert lobby["hostSlot"] == 1
        assert lobby["settings"]["isPublic"] is True
        assert lobby["settings"]["speed"] == "standard"
        assert lobby["settings"]["playerCount"] == 2
        assert lobby["status"] == "waiting"
        # Unauthenticated users show as "Guest"
        assert lobby["players"]["1"]["username"] == "Guest"

    def test_create_lobby_with_settings(self, client: TestClient) -> None:
        """Test creating a lobby with custom settings."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {
                    "isPublic": False,
                    "speed": "lightning",
                    "playerCount": 4,
                    "isRanked": False,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        lobby = data["lobby"]
        assert lobby["settings"]["isPublic"] is False
        assert lobby["settings"]["speed"] == "lightning"
        assert lobby["settings"]["playerCount"] == 4

    def test_create_lobby_with_ai(self, client: TestClient) -> None:
        """Test creating a lobby with AI player."""
        response = client.post(
            "/api/lobbies",
            json={
                "addAi": True,
                "aiType": "bot:dummy",
            },
        )

        assert response.status_code == 200
        data = response.json()
        lobby = data["lobby"]
        # Should have 2 players (host + AI)
        assert len(lobby["players"]) == 2
        # Player 2 should be AI
        player2 = lobby["players"]["2"]
        assert player2["isAi"] is True
        assert player2["aiType"] == "bot:dummy"
        assert player2["isReady"] is True  # AI is always ready

    def test_create_lobby_4player_with_ai(self, client: TestClient) -> None:
        """Test creating a 4-player lobby with AI."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"playerCount": 4},
                "addAi": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        lobby = data["lobby"]
        # Should have 4 players (host + 3 AI)
        assert len(lobby["players"]) == 4
        for slot in ["2", "3", "4"]:
            assert lobby["players"][slot]["isAi"] is True

    def test_create_lobby_invalid_speed(self, client: TestClient) -> None:
        """Test creating a lobby with invalid speed."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"speed": "invalid"},
            },
        )

        assert response.status_code == 400

    def test_create_lobby_invalid_player_count(self, client: TestClient) -> None:
        """Test creating a lobby with invalid player count."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"playerCount": 3},
            },
        )

        assert response.status_code == 400

    def test_create_multiple_lobbies(self, client: TestClient) -> None:
        """Test that a player can create multiple lobbies (no lock)."""
        guest_id = "test-guest-123"

        # Create first lobby
        response1 = client.post(
            "/api/lobbies",
            json={"guestId": guest_id},
        )
        assert response1.status_code == 200
        code1 = response1.json()["code"]

        # Create second lobby with same guest
        response2 = client.post(
            "/api/lobbies",
            json={"guestId": guest_id},
        )
        assert response2.status_code == 200
        code2 = response2.json()["code"]

        assert code1 != code2

        # Both lobbies should exist (no one-lobby-per-player restriction)
        get1 = client.get(f"/api/lobbies/{code1}")
        get2 = client.get(f"/api/lobbies/{code2}")
        assert get1.status_code == 200
        assert get2.status_code == 200


class TestListLobbies:
    """Tests for GET /api/lobbies."""

    def test_list_lobbies_empty(self, client: TestClient) -> None:
        """Test listing lobbies when none exist."""
        response = client.get("/api/lobbies")

        assert response.status_code == 200
        data = response.json()
        assert data["lobbies"] == []

    def test_list_lobbies(self, client: TestClient) -> None:
        """Test listing public lobbies."""
        # Create a public lobby
        client.post(
            "/api/lobbies",
            json={},
        )

        response = client.get("/api/lobbies")

        assert response.status_code == 200
        data = response.json()
        assert len(data["lobbies"]) == 1
        lobby = data["lobbies"][0]
        assert "code" in lobby
        assert lobby["hostUsername"] == "Guest"
        assert lobby["currentPlayers"] == 1

    def test_list_lobbies_excludes_private(self, client: TestClient) -> None:
        """Test that private lobbies are not listed."""
        # Create a private lobby
        client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": False},
            },
        )

        response = client.get("/api/lobbies")

        assert response.status_code == 200
        data = response.json()
        assert len(data["lobbies"]) == 0

    def test_list_lobbies_filter_by_speed(self, client: TestClient) -> None:
        """Test filtering lobbies by speed."""
        # Create standard lobby
        client.post(
            "/api/lobbies",
            json={"settings": {"speed": "standard"}},
        )
        # Create lightning lobby
        client.post(
            "/api/lobbies",
            json={"settings": {"speed": "lightning"}},
        )

        # Filter by standard
        response = client.get("/api/lobbies", params={"speed": "standard"})

        assert response.status_code == 200
        data = response.json()
        assert len(data["lobbies"]) == 1
        assert data["lobbies"][0]["settings"]["speed"] == "standard"

    def test_list_lobbies_filter_by_player_count(self, client: TestClient) -> None:
        """Test filtering lobbies by player count."""
        # Create 2-player lobby
        client.post(
            "/api/lobbies",
            json={"settings": {"playerCount": 2}},
        )
        # Create 4-player lobby
        client.post(
            "/api/lobbies",
            json={"settings": {"playerCount": 4}},
        )

        # Filter by 4-player
        response = client.get("/api/lobbies", params={"playerCount": 4})

        assert response.status_code == 200
        data = response.json()
        assert len(data["lobbies"]) == 1
        assert data["lobbies"][0]["settings"]["playerCount"] == 4


class TestGetLobby:
    """Tests for GET /api/lobbies/{code}."""

    def test_get_lobby(self, client: TestClient) -> None:
        """Test getting lobby details."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={},
        )
        code = create_response.json()["code"]

        # Get lobby
        response = client.get(f"/api/lobbies/{code}")

        assert response.status_code == 200
        data = response.json()
        assert "lobby" in data
        assert data["lobby"]["code"] == code
        assert data["lobby"]["hostSlot"] == 1

    def test_get_lobby_not_found(self, client: TestClient) -> None:
        """Test getting nonexistent lobby."""
        response = client.get("/api/lobbies/NOTFOUND")

        assert response.status_code == 404


class TestJoinLobby:
    """Tests for POST /api/lobbies/{code}/join."""

    def test_join_lobby(self, client: TestClient) -> None:
        """Test joining an existing lobby."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={},
        )
        code = create_response.json()["code"]

        # Join lobby
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert "playerKey" in data
        assert data["slot"] == 2
        lobby = data["lobby"]
        assert len(lobby["players"]) == 2
        # Unauthenticated users show as "Guest"
        assert lobby["players"]["2"]["username"] == "Guest"

    def test_join_lobby_preferred_slot(self, client: TestClient) -> None:
        """Test joining with preferred slot."""
        # Create a 4-player lobby
        create_response = client.post(
            "/api/lobbies",
            json={
                "settings": {"playerCount": 4},
            },
        )
        code = create_response.json()["code"]

        # Join with preferred slot 3
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={"preferredSlot": 3},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slot"] == 3

    def test_join_lobby_not_found(self, client: TestClient) -> None:
        """Test joining nonexistent lobby."""
        response = client.post(
            "/api/lobbies/NOTFOUND/join",
            json={},
        )

        assert response.status_code == 404

    def test_join_lobby_full(self, client: TestClient) -> None:
        """Test joining a full lobby."""
        # Create a lobby with AI (will be full)
        create_response = client.post(
            "/api/lobbies",
            json={
                "addAi": True,
            },
        )
        code = create_response.json()["code"]

        # Try to join full lobby
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={},
        )

        assert response.status_code == 409
        assert "full" in response.json()["detail"].lower()

    def test_join_multiple_lobbies(self, client: TestClient) -> None:
        """Test that a player can join multiple lobbies (no lock)."""
        guest_id = "test-guest-456"

        # Create first lobby
        response1 = client.post(
            "/api/lobbies",
            json={},
        )
        code1 = response1.json()["code"]

        # Create second lobby
        response2 = client.post(
            "/api/lobbies",
            json={},
        )
        code2 = response2.json()["code"]

        # Join first lobby
        join1 = client.post(
            f"/api/lobbies/{code1}/join",
            json={"guestId": guest_id},
        )
        assert join1.status_code == 200

        # Join second lobby with same guest
        join2 = client.post(
            f"/api/lobbies/{code2}/join",
            json={"guestId": guest_id},
        )
        assert join2.status_code == 200

        # Player should be in both lobbies
        get1 = client.get(f"/api/lobbies/{code1}")
        get2 = client.get(f"/api/lobbies/{code2}")
        lobby1 = get1.json()["lobby"]
        lobby2 = get2.json()["lobby"]

        assert "2" in lobby1["players"]
        assert "2" in lobby2["players"]

    def test_join_private_lobby_allowed(self, client: TestClient) -> None:
        """Test that private lobbies can be joined via direct link/code."""
        # Create a private lobby
        create_response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": False},
            },
        )
        code = create_response.json()["code"]

        # Join the private lobby (allowed with direct code)
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert "playerKey" in data
        assert data["slot"] == 2


class TestDeleteLobby:
    """Tests for DELETE /api/lobbies/{code}."""

    def test_delete_lobby(self, client: TestClient) -> None:
        """Test deleting a lobby as host."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={},
        )
        data = create_response.json()
        code = data["code"]
        player_key = data["playerKey"]

        # Delete lobby
        response = client.delete(
            f"/api/lobbies/{code}",
            params={"player_key": player_key},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify lobby is deleted
        get_response = client.get(f"/api/lobbies/{code}")
        assert get_response.status_code == 404

    def test_delete_lobby_not_host(self, client: TestClient) -> None:
        """Test that non-host cannot delete lobby."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={},
        )
        code = create_response.json()["code"]

        # Another player joins
        join_response = client.post(
            f"/api/lobbies/{code}/join",
            json={},
        )
        player2_key = join_response.json()["playerKey"]

        # Player2 tries to delete
        response = client.delete(
            f"/api/lobbies/{code}",
            params={"player_key": player2_key},
        )

        assert response.status_code == 403

    def test_delete_lobby_invalid_key(self, client: TestClient) -> None:
        """Test deleting with invalid key."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={},
        )
        code = create_response.json()["code"]

        # Try to delete with invalid key
        response = client.delete(
            f"/api/lobbies/{code}",
            params={"player_key": "invalid"},
        )

        assert response.status_code == 403

    def test_delete_lobby_not_found(self, client: TestClient) -> None:
        """Test deleting nonexistent lobby."""
        response = client.delete(
            "/api/lobbies/NOTFOUND",
            params={"player_key": "test"},
        )

        assert response.status_code == 403  # Invalid key first

    def test_delete_lobby_during_game(self, client: TestClient) -> None:
        """Test that lobbies cannot be deleted during games."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={},
        )
        data = create_response.json()
        code = data["code"]
        player_key = data["playerKey"]

        # Directly set lobby status to in_game via sync Redis
        sync_redis = SyncFakeRedis(
            server=_fake_server, decode_responses=True, version=(7,)
        )
        raw = sync_redis.get(f"lobby:{code}")
        lobby_data = json.loads(raw)
        lobby_data["status"] = "in_game"
        sync_redis.set(f"lobby:{code}", json.dumps(lobby_data))

        # Try to delete lobby
        response = client.delete(
            f"/api/lobbies/{code}",
            params={"player_key": player_key},
        )

        assert response.status_code == 409
        assert "in progress" in response.json()["detail"].lower()


class TestLiveGames:
    """Tests for GET /api/games/live (DB-backed active games registry)."""

    def test_list_live_games_empty(self, client: TestClient) -> None:
        """Test listing live games when none are registered."""
        from unittest.mock import AsyncMock, patch

        mock_repo = AsyncMock()
        mock_repo.list_active.return_value = []

        with patch("kfchess.api.games.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch("kfchess.api.games.ActiveGameRepository", return_value=mock_repo):
                response = client.get("/api/games/live")

        assert response.status_code == 200
        data = response.json()
        assert data["games"] == []

    def test_list_live_games_returns_registered_games(self, client: TestClient) -> None:
        """Test that registered active games are returned."""
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_record = MagicMock()
        mock_record.game_id = "test-game-123"
        mock_record.game_type = "lobby"
        mock_record.lobby_code = "ABC123"
        mock_record.campaign_level_id = None
        mock_record.speed = "standard"
        mock_record.player_count = 2
        mock_record.board_type = "standard"
        mock_record.server_id = "remote-server"
        mock_record.players = [
            {"slot": 1, "username": "Player1", "is_ai": False},
            {"slot": 2, "username": "Bot", "is_ai": True},
        ]
        mock_record.started_at = datetime(2026, 1, 1, 12, 0, 0)

        mock_repo = AsyncMock()
        mock_repo.list_active.return_value = [mock_record]

        with patch("kfchess.api.games.async_session_factory") as mock_factory, \
             patch("kfchess.api.games.ActiveGameRepository", return_value=mock_repo), \
             patch("kfchess.api.games.get_redis", new_callable=AsyncMock) as mock_redis, \
             patch("kfchess.api.games.get_game_server", new_callable=AsyncMock, return_value="remote-server"), \
             patch("kfchess.api.games.is_server_alive", new_callable=AsyncMock, return_value=True), \
             patch("kfchess.api.games.get_settings") as mock_settings:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_settings.return_value.effective_server_id = "my-server"
            mock_redis.return_value = MagicMock()
            response = client.get("/api/games/live")

        assert response.status_code == 200
        data = response.json()
        assert len(data["games"]) == 1
        assert data["games"][0]["game_id"] == "test-game-123"
        assert data["games"][0]["game_type"] == "lobby"
        assert data["games"][0]["lobby_code"] == "ABC123"
        assert len(data["games"][0]["players"]) == 2

    def test_list_live_games_filters_by_game_type(self, client: TestClient) -> None:
        """Test filtering live games by game_type query param."""
        from unittest.mock import AsyncMock, patch

        mock_repo = AsyncMock()
        mock_repo.list_active.return_value = []

        with patch("kfchess.api.games.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch("kfchess.api.games.ActiveGameRepository", return_value=mock_repo):
                response = client.get("/api/games/live?game_type=campaign")

        assert response.status_code == 200
        mock_repo.list_active.assert_called_once_with(
            speed=None,
            player_count=None,
            game_type="campaign",
        )

    def test_list_live_games_filters_by_speed(self, client: TestClient) -> None:
        """Test filtering live games by speed query param."""
        from unittest.mock import AsyncMock, patch

        mock_repo = AsyncMock()
        mock_repo.list_active.return_value = []

        with patch("kfchess.api.games.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            with patch("kfchess.api.games.ActiveGameRepository", return_value=mock_repo):
                response = client.get("/api/games/live?speed=lightning")

        assert response.status_code == 200
        mock_repo.list_active.assert_called_once_with(
            speed="lightning",
            player_count=None,
            game_type=None,
        )

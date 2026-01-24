"""Tests for the lobbies API endpoints."""

import pytest
from fastapi.testclient import TestClient

from kfchess.lobby.manager import get_lobby_manager
from kfchess.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_lobbies() -> None:
    """Clear lobbies and games before each test."""
    from kfchess.services.game_service import get_game_service

    manager = get_lobby_manager()
    manager._lobbies.clear()
    manager._player_keys.clear()
    manager._key_to_slot.clear()
    manager._player_to_lobby.clear()

    game_service = get_game_service()
    game_service.games.clear()


class TestCreateLobby:
    """Tests for POST /api/lobbies."""

    def test_create_lobby_default(self, client: TestClient) -> None:
        """Test creating a lobby with defaults."""
        response = client.post(
            "/api/lobbies",
            json={"username": "TestHost"},
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

    def test_create_lobby_with_settings(self, client: TestClient) -> None:
        """Test creating a lobby with custom settings."""
        response = client.post(
            "/api/lobbies",
            json={
                "username": "TestHost",
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
                "username": "TestHost",
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
                "username": "TestHost",
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
                "username": "TestHost",
                "settings": {"speed": "invalid"},
            },
        )

        assert response.status_code == 400

    def test_create_lobby_invalid_player_count(self, client: TestClient) -> None:
        """Test creating a lobby with invalid player count."""
        response = client.post(
            "/api/lobbies",
            json={
                "username": "TestHost",
                "settings": {"playerCount": 3},
            },
        )

        assert response.status_code == 400

    def test_create_lobby_player_lock(self, client: TestClient) -> None:
        """Test that creating a new lobby leaves the old one."""
        guest_id = "test-guest-123"

        # Create first lobby
        response1 = client.post(
            "/api/lobbies",
            json={"username": "TestHost", "guestId": guest_id},
        )
        assert response1.status_code == 200
        code1 = response1.json()["code"]

        # Create second lobby with same guest
        response2 = client.post(
            "/api/lobbies",
            json={"username": "TestHost", "guestId": guest_id},
        )
        assert response2.status_code == 200
        code2 = response2.json()["code"]

        assert code1 != code2

        # First lobby should be deleted (no human players left)
        manager = get_lobby_manager()
        assert manager.get_lobby(code1) is None
        assert manager.get_lobby(code2) is not None


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
            json={"username": "Host1"},
        )

        response = client.get("/api/lobbies")

        assert response.status_code == 200
        data = response.json()
        assert len(data["lobbies"]) == 1
        lobby = data["lobbies"][0]
        assert "code" in lobby
        assert lobby["hostUsername"] == "Host1"
        assert lobby["currentPlayers"] == 1

    def test_list_lobbies_excludes_private(self, client: TestClient) -> None:
        """Test that private lobbies are not listed."""
        # Create a private lobby
        client.post(
            "/api/lobbies",
            json={
                "username": "Host1",
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
            json={"username": "Host1", "settings": {"speed": "standard"}},
        )
        # Create lightning lobby
        client.post(
            "/api/lobbies",
            json={"username": "Host2", "settings": {"speed": "lightning"}},
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
            json={"username": "Host1", "settings": {"playerCount": 2}},
        )
        # Create 4-player lobby
        client.post(
            "/api/lobbies",
            json={"username": "Host2", "settings": {"playerCount": 4}},
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
            json={"username": "TestHost"},
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
            json={"username": "Host"},
        )
        code = create_response.json()["code"]

        # Join lobby
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={"username": "Player2"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "playerKey" in data
        assert data["slot"] == 2
        lobby = data["lobby"]
        assert len(lobby["players"]) == 2
        assert lobby["players"]["2"]["username"] == "Player2"

    def test_join_lobby_preferred_slot(self, client: TestClient) -> None:
        """Test joining with preferred slot."""
        # Create a 4-player lobby
        create_response = client.post(
            "/api/lobbies",
            json={
                "username": "Host",
                "settings": {"playerCount": 4},
            },
        )
        code = create_response.json()["code"]

        # Join with preferred slot 3
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={"username": "Player", "preferredSlot": 3},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slot"] == 3

    def test_join_lobby_not_found(self, client: TestClient) -> None:
        """Test joining nonexistent lobby."""
        response = client.post(
            "/api/lobbies/NOTFOUND/join",
            json={"username": "Player"},
        )

        assert response.status_code == 404

    def test_join_lobby_full(self, client: TestClient) -> None:
        """Test joining a full lobby."""
        # Create a lobby with AI (will be full)
        create_response = client.post(
            "/api/lobbies",
            json={
                "username": "Host",
                "addAi": True,
            },
        )
        code = create_response.json()["code"]

        # Try to join full lobby
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={"username": "Player"},
        )

        assert response.status_code == 409
        assert "full" in response.json()["detail"].lower()

    def test_join_lobby_player_lock(self, client: TestClient) -> None:
        """Test that joining a new lobby leaves the old one."""
        guest_id = "test-guest-456"

        # Create first lobby
        response1 = client.post(
            "/api/lobbies",
            json={"username": "Host1"},
        )
        code1 = response1.json()["code"]

        # Create second lobby
        response2 = client.post(
            "/api/lobbies",
            json={"username": "Host2"},
        )
        code2 = response2.json()["code"]

        # Join first lobby
        client.post(
            f"/api/lobbies/{code1}/join",
            json={"username": "Player", "guestId": guest_id},
        )

        # Join second lobby with same guest
        join_response = client.post(
            f"/api/lobbies/{code2}/join",
            json={"username": "Player", "guestId": guest_id},
        )

        assert join_response.status_code == 200

        # Player should be in second lobby, not first
        manager = get_lobby_manager()
        lobby1 = manager.get_lobby(code1)
        lobby2 = manager.get_lobby(code2)

        assert 2 not in lobby1.players  # Left first lobby
        assert 2 in lobby2.players  # Joined second lobby

    def test_join_private_lobby_forbidden(self, client: TestClient) -> None:
        """Test that private lobbies cannot be joined via API."""
        # Create a private lobby
        create_response = client.post(
            "/api/lobbies",
            json={
                "username": "Host",
                "settings": {"isPublic": False},
            },
        )
        code = create_response.json()["code"]

        # Try to join the private lobby
        response = client.post(
            f"/api/lobbies/{code}/join",
            json={"username": "Player2"},
        )

        assert response.status_code == 403
        assert "private" in response.json()["detail"].lower()


class TestDeleteLobby:
    """Tests for DELETE /api/lobbies/{code}."""

    def test_delete_lobby(self, client: TestClient) -> None:
        """Test deleting a lobby as host."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={"username": "Host"},
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
        manager = get_lobby_manager()
        assert manager.get_lobby(code) is None

    def test_delete_lobby_not_host(self, client: TestClient) -> None:
        """Test that non-host cannot delete lobby."""
        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={"username": "Host"},
        )
        code = create_response.json()["code"]

        # Another player joins
        join_response = client.post(
            f"/api/lobbies/{code}/join",
            json={"username": "Player2"},
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
            json={"username": "Host"},
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
        from kfchess.lobby.models import LobbyStatus

        # Create a lobby
        create_response = client.post(
            "/api/lobbies",
            json={"username": "Host"},
        )
        data = create_response.json()
        code = data["code"]
        player_key = data["playerKey"]

        # Manually set lobby status to IN_GAME
        manager = get_lobby_manager()
        lobby = manager.get_lobby(code)
        lobby.status = LobbyStatus.IN_GAME

        # Try to delete lobby
        response = client.delete(
            f"/api/lobbies/{code}",
            params={"player_key": player_key},
        )

        assert response.status_code == 409
        assert "in progress" in response.json()["detail"].lower()


class TestLiveGames:
    """Tests for GET /api/games/live."""

    def test_list_live_games_empty(self, client: TestClient) -> None:
        """Test listing live games when none exist."""
        response = client.get("/api/games/live")

        assert response.status_code == 200
        data = response.json()
        assert data["games"] == []

    def test_list_live_games_excludes_waiting(self, client: TestClient) -> None:
        """Test that waiting lobbies are not in live games."""
        # Create a lobby (waiting status)
        client.post(
            "/api/lobbies",
            json={"username": "Host"},
        )

        response = client.get("/api/games/live")

        assert response.status_code == 200
        data = response.json()
        assert data["games"] == []

    def test_list_live_games_excludes_private(self, client: TestClient) -> None:
        """Test that private games in progress are not listed."""
        from kfchess.lobby.models import LobbyStatus

        # Create a private lobby
        create_response = client.post(
            "/api/lobbies",
            json={
                "username": "Host",
                "settings": {"isPublic": False},
            },
        )
        code = create_response.json()["code"]

        # Manually set lobby status to IN_GAME
        manager = get_lobby_manager()
        lobby = manager.get_lobby(code)
        lobby.status = LobbyStatus.IN_GAME
        lobby.current_game_id = "test-game-123"

        # Private games should not appear in live games
        response = client.get("/api/games/live")

        assert response.status_code == 200
        data = response.json()
        assert data["games"] == []

    def test_list_live_games_shows_public_in_game(self, client: TestClient) -> None:
        """Test that public games in progress are listed."""
        from kfchess.lobby.models import LobbyStatus
        from kfchess.services.game_service import get_game_service

        # Create a public lobby
        create_response = client.post(
            "/api/lobbies",
            json={"username": "Host"},
        )
        code = create_response.json()["code"]

        # Create a game via game service so it's tracked
        game_service = get_game_service()
        from kfchess.game.board import BoardType
        from kfchess.game.state import Speed

        game_id, _, _ = game_service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:dummy",
        )

        # Set lobby status to IN_GAME with the game ID
        manager = get_lobby_manager()
        lobby = manager.get_lobby(code)
        lobby.status = LobbyStatus.IN_GAME
        lobby.current_game_id = game_id

        # Public games should appear in live games
        response = client.get("/api/games/live")

        assert response.status_code == 200
        data = response.json()
        assert len(data["games"]) == 1
        assert data["games"][0]["game_id"] == game_id
        assert data["games"][0]["lobby_code"] == code

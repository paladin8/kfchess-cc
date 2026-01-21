"""Tests for the games API endpoints."""

import pytest
from fastapi.testclient import TestClient

from kfchess.main import app
from kfchess.services.game_service import get_game_service


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_games() -> None:
    """Clear games before each test."""
    service = get_game_service()
    service.games.clear()


class TestCreateGame:
    """Tests for POST /api/games."""

    def test_create_game_default(self, client: TestClient) -> None:
        """Test creating a game with defaults."""
        response = client.post("/api/games", json={})

        assert response.status_code == 200
        data = response.json()
        assert "game_id" in data
        assert "player_key" in data
        assert data["player_number"] == 1
        assert data["board_type"] == "standard"
        assert data["status"] == "waiting"

    def test_create_game_4player(self, client: TestClient) -> None:
        """Test creating a 4-player game."""
        response = client.post(
            "/api/games",
            json={"board_type": "four_player"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["board_type"] == "four_player"

    def test_create_game_invalid_speed(self, client: TestClient) -> None:
        """Test creating a game with invalid speed."""
        response = client.post(
            "/api/games",
            json={"speed": "invalid"},
        )

        assert response.status_code == 400

    def test_create_game_invalid_board_type(self, client: TestClient) -> None:
        """Test creating a game with invalid board type."""
        response = client.post(
            "/api/games",
            json={"board_type": "invalid"},
        )

        assert response.status_code == 400


class TestGetGame:
    """Tests for GET /api/games/{game_id}."""

    def test_get_game(self, client: TestClient) -> None:
        """Test getting game state."""
        # Create a game first
        create_response = client.post("/api/games", json={})
        game_id = create_response.json()["game_id"]

        # Get game state
        response = client.get(f"/api/games/{game_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == game_id
        assert data["status"] == "waiting"
        assert "board" in data
        assert "pieces" in data["board"]
        assert len(data["board"]["pieces"]) == 32  # Standard chess

    def test_get_game_4player(self, client: TestClient) -> None:
        """Test getting 4-player game state."""
        # Create a 4-player game
        create_response = client.post(
            "/api/games",
            json={"board_type": "four_player"},
        )
        game_id = create_response.json()["game_id"]

        # Get game state
        response = client.get(f"/api/games/{game_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["board"]["board_type"] == "four_player"
        assert data["board"]["width"] == 12
        assert data["board"]["height"] == 12
        assert len(data["board"]["pieces"]) == 64  # 4 players x 16 pieces

    def test_get_game_not_found(self, client: TestClient) -> None:
        """Test getting nonexistent game."""
        response = client.get("/api/games/NOTFOUND")

        assert response.status_code == 404


class TestMarkReady:
    """Tests for POST /api/games/{game_id}/ready."""

    def test_mark_ready_starts_game(self, client: TestClient) -> None:
        """Test marking ready starts the game."""
        # Create a game
        create_response = client.post("/api/games", json={})
        data = create_response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        # Mark ready
        response = client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": player_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["game_started"] is True
        assert data["status"] == "playing"

    def test_mark_ready_invalid_key(self, client: TestClient) -> None:
        """Test marking ready with invalid key."""
        # Create a game
        create_response = client.post("/api/games", json={})
        game_id = create_response.json()["game_id"]

        # Mark ready with invalid key
        response = client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": "invalid"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_mark_ready_not_found(self, client: TestClient) -> None:
        """Test marking ready on nonexistent game."""
        response = client.post(
            "/api/games/NOTFOUND/ready",
            json={"player_key": "test"},
        )

        assert response.status_code == 404


class TestMakeMove:
    """Tests for POST /api/games/{game_id}/move."""

    def test_make_valid_move(self, client: TestClient) -> None:
        """Test making a valid move."""
        # Create and start a game
        create_response = client.post("/api/games", json={})
        data = create_response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": player_key},
        )

        # Make a move
        response = client.post(
            f"/api/games/{game_id}/move",
            json={
                "player_key": player_key,
                "piece_id": "P:1:6:0",
                "to_row": 5,
                "to_col": 0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["move"] is not None

    def test_make_invalid_move(self, client: TestClient) -> None:
        """Test making an invalid move."""
        # Create and start a game
        create_response = client.post("/api/games", json={})
        data = create_response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": player_key},
        )

        # Try invalid move
        response = client.post(
            f"/api/games/{game_id}/move",
            json={
                "player_key": player_key,
                "piece_id": "P:1:6:0",
                "to_row": 3,  # Too far for pawn
                "to_col": 0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "invalid_move"

    def test_make_move_wrong_piece(self, client: TestClient) -> None:
        """Test moving opponent's piece."""
        # Create and start a game
        create_response = client.post("/api/games", json={})
        data = create_response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": player_key},
        )

        # Try to move opponent's piece
        response = client.post(
            f"/api/games/{game_id}/move",
            json={
                "player_key": player_key,
                "piece_id": "P:2:1:0",
                "to_row": 2,
                "to_col": 0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "not_your_piece"

    def test_make_move_not_found(self, client: TestClient) -> None:
        """Test making move on nonexistent game."""
        response = client.post(
            "/api/games/NOTFOUND/move",
            json={
                "player_key": "test",
                "piece_id": "P:1:6:0",
                "to_row": 5,
                "to_col": 0,
            },
        )

        assert response.status_code == 404


class TestGetLegalMoves:
    """Tests for GET /api/games/{game_id}/legal-moves."""

    def test_get_legal_moves(self, client: TestClient) -> None:
        """Test getting legal moves."""
        # Create and start a game
        create_response = client.post("/api/games", json={})
        data = create_response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": player_key},
        )

        # Get legal moves
        response = client.get(
            f"/api/games/{game_id}/legal-moves",
            params={"player_key": player_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert "moves" in data
        assert len(data["moves"]) > 0

        # Check structure
        for move in data["moves"]:
            assert "piece_id" in move
            assert "targets" in move

    def test_get_legal_moves_invalid_key(self, client: TestClient) -> None:
        """Test getting legal moves with invalid key."""
        # Create and start a game
        create_response = client.post("/api/games", json={})
        game_id = create_response.json()["game_id"]

        # Get legal moves with invalid key
        response = client.get(
            f"/api/games/{game_id}/legal-moves",
            params={"player_key": "invalid"},
        )

        assert response.status_code == 403

    def test_get_legal_moves_not_found(self, client: TestClient) -> None:
        """Test getting legal moves for nonexistent game."""
        response = client.get(
            "/api/games/NOTFOUND/legal-moves",
            params={"player_key": "test"},
        )

        assert response.status_code == 404

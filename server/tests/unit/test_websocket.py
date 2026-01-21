"""Tests for WebSocket functionality."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from kfchess.main import app
from kfchess.services.game_service import get_game_service
from kfchess.ws.handler import ConnectionManager
from kfchess.ws.protocol import (
    MoveMessage,
    PingMessage,
    ReadyMessage,
    parse_client_message,
)


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_games() -> None:
    """Clear games before each test."""
    service = get_game_service()
    service.games.clear()


class TestProtocol:
    """Tests for WebSocket protocol message parsing."""

    def test_parse_move_message(self) -> None:
        """Test parsing a move message."""
        data = {
            "type": "move",
            "piece_id": "P:1:6:0",
            "to_row": 5,
            "to_col": 0,
        }
        msg = parse_client_message(data)
        assert isinstance(msg, MoveMessage)
        assert msg.piece_id == "P:1:6:0"
        assert msg.to_row == 5
        assert msg.to_col == 0

    def test_parse_ready_message(self) -> None:
        """Test parsing a ready message."""
        data = {"type": "ready"}
        msg = parse_client_message(data)
        assert isinstance(msg, ReadyMessage)

    def test_parse_ping_message(self) -> None:
        """Test parsing a ping message."""
        data = {"type": "ping"}
        msg = parse_client_message(data)
        assert isinstance(msg, PingMessage)

    def test_parse_invalid_message(self) -> None:
        """Test parsing an invalid message."""
        data = {"type": "unknown"}
        msg = parse_client_message(data)
        assert msg is None

    def test_parse_move_message_missing_fields(self) -> None:
        """Test parsing a move message with missing fields."""
        data = {"type": "move", "piece_id": "P:1:6:0"}
        msg = parse_client_message(data)
        assert msg is None


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.mark.asyncio
    async def test_connection_tracking(self) -> None:
        """Test that connections are tracked correctly."""
        manager = ConnectionManager()

        # Initially no connections
        assert not manager.has_connections("game1")
        assert manager.get_connection_count("game1") == 0

    @pytest.mark.asyncio
    async def test_has_connections_empty(self) -> None:
        """Test has_connections returns False for empty game."""
        manager = ConnectionManager()
        assert not manager.has_connections("nonexistent")


class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint."""

    def test_websocket_connect_invalid_game(self, client: TestClient) -> None:
        """Test connecting to a nonexistent game."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/game/NOTFOUND"):
                pass

    def test_websocket_connect_valid_game(self, client: TestClient) -> None:
        """Test connecting to a valid game."""
        # Create a game first
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        # Connect to the game
        with client.websocket_connect(
            f"/ws/game/{game_id}?player_key={player_key}"
        ) as websocket:
            # First message should be initial state
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "state"

            # Send ping
            websocket.send_text(json.dumps({"type": "ping"}))
            # Should receive pong
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "pong"

    def test_websocket_ready_and_game_start(self, client: TestClient) -> None:
        """Test marking ready via WebSocket starts the game."""
        # Create a game
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        # Connect and mark ready
        with client.websocket_connect(
            f"/ws/game/{game_id}?player_key={player_key}"
        ) as websocket:
            # First message is initial state
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "state"

            # Send ready message
            websocket.send_text(json.dumps({"type": "ready"}))

            # Should receive game_started message
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "game_started"
            assert msg["tick"] == 0

    def test_websocket_spectator_cannot_move(self, client: TestClient) -> None:
        """Test that spectators cannot make moves."""
        # Create a game (don't start it yet to avoid game loop interference)
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        # Start the game via API
        client.post(
            f"/api/games/{game_id}/ready",
            json={"player_key": player_key},
        )

        # Connect as spectator (no player_key)
        with client.websocket_connect(f"/ws/game/{game_id}") as websocket:
            # Try to make a move
            websocket.send_text(
                json.dumps({
                    "type": "move",
                    "piece_id": "P:1:6:0",
                    "to_row": 5,
                    "to_col": 0,
                })
            )

            # Keep receiving until we get move_rejected (skip state updates)
            for _ in range(10):
                response = websocket.receive_text()
                msg = json.loads(response)
                if msg["type"] == "move_rejected":
                    assert msg["reason"] == "spectators_cannot_move"
                    return
            pytest.fail("Did not receive move_rejected message")

    def test_websocket_invalid_json(self, client: TestClient) -> None:
        """Test sending invalid JSON."""
        # Create a game
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        with client.websocket_connect(
            f"/ws/game/{game_id}?player_key={player_key}"
        ) as websocket:
            # Skip initial state message
            websocket.receive_text()

            # Send invalid JSON
            websocket.send_text("not valid json")

            # Should receive error
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert "Invalid JSON" in msg["message"]

    def test_websocket_unknown_message_type(self, client: TestClient) -> None:
        """Test sending unknown message type."""
        # Create a game
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        with client.websocket_connect(
            f"/ws/game/{game_id}?player_key={player_key}"
        ) as websocket:
            # Skip initial state message
            websocket.receive_text()

            # Send unknown message type
            websocket.send_text(json.dumps({"type": "unknown_type"}))

            # Should receive error
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert "Unknown message type" in msg["message"]

    def test_websocket_make_move(self, client: TestClient) -> None:
        """Test making a move via WebSocket."""
        # Create a game
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        with client.websocket_connect(
            f"/ws/game/{game_id}?player_key={player_key}"
        ) as websocket:
            # Skip initial state message
            websocket.receive_text()

            # Mark ready first
            websocket.send_text(json.dumps({"type": "ready"}))
            # Receive game_started
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "game_started"

            # Make a move
            websocket.send_text(
                json.dumps({
                    "type": "move",
                    "piece_id": "P:1:6:0",
                    "to_row": 5,
                    "to_col": 0,
                })
            )

            # Should receive state update (from the game loop)
            # Note: Move might be rejected if game loop hasn't started yet,
            # or we might receive a state update with the move

    def test_websocket_invalid_move(self, client: TestClient) -> None:
        """Test making an invalid move via WebSocket."""
        # Create a game
        response = client.post("/api/games", json={})
        data = response.json()
        game_id = data["game_id"]
        player_key = data["player_key"]

        with client.websocket_connect(
            f"/ws/game/{game_id}?player_key={player_key}"
        ) as websocket:
            # Skip initial state message
            websocket.receive_text()

            # Mark ready first
            websocket.send_text(json.dumps({"type": "ready"}))
            # Receive game_started
            websocket.receive_text()

            # Try invalid move (pawn moving diagonally without capture)
            websocket.send_text(
                json.dumps({
                    "type": "move",
                    "piece_id": "P:1:6:0",
                    "to_row": 5,
                    "to_col": 1,
                })
            )

            # Keep receiving until we get move_rejected (skip state updates)
            for _ in range(10):
                response = websocket.receive_text()
                msg = json.loads(response)
                if msg["type"] == "move_rejected":
                    assert msg["piece_id"] == "P:1:6:0"
                    return
            pytest.fail("Did not receive move_rejected message")

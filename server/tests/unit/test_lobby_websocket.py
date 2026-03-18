"""Tests for lobby WebSocket functionality.

These tests use fakeredis to provide a Redis backend for the
RedisLobbyManager, and Starlette's sync TestClient for WebSocket testing.
"""

import contextlib
import json
from collections.abc import Generator
from concurrent.futures import CancelledError
from unittest.mock import patch

import pytest
from fakeredis import FakeServer
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kfchess.lobby.manager import reset_lobby_manager
from kfchess.main import app
from kfchess.services.game_service import get_game_service
from kfchess.ws.lobby_handler import (
    serialize_lobby,
    serialize_player,
    serialize_settings,
)

_fake_server = FakeServer()


async def _fake_get_redis() -> FakeRedis:
    """Return a fakeredis client backed by the shared FakeServer."""
    return FakeRedis(server=_fake_server, decode_responses=True, version=(7,))


@contextlib.contextmanager
def ws_connect(client: TestClient, url: str):
    """Connect to a WebSocket, suppressing CancelledError on close.

    Starlette's sync TestClient can race between sending the WebSocket
    close frame and cancelling the ASGI handler's CancelScope. When the
    handler is still shutting down (e.g. pub/sub cleanup) at the moment
    the scope is cancelled, CancelledError escapes from the handler and
    causes the Future to be cancelled. This is harmless — the handler
    has already processed the disconnect — so we suppress it.
    """
    try:
        with client.websocket_connect(url) as ws:
            yield ws
    except CancelledError:
        pass


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_state() -> Generator[None, None, None]:
    """Clear lobbies, games, and Redis before each test."""
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


class TestSerialization:
    """Tests for lobby serialization functions."""

    def test_serialize_player(self) -> None:
        """Test serializing a LobbyPlayer."""
        from kfchess.lobby.models import LobbyPlayer

        player = LobbyPlayer(
            slot=1,
            user_id=123,
            username="TestPlayer",
            is_ai=False,
            ai_type=None,
        )
        player.is_ready = True

        result = serialize_player(player)

        assert result["slot"] == 1
        assert result["userId"] == 123
        assert result["username"] == "TestPlayer"
        assert result["isAi"] is False
        assert result["aiType"] is None
        assert result["isReady"] is True

    def test_serialize_ai_player(self) -> None:
        """Test serializing an AI player."""
        from kfchess.lobby.models import LobbyPlayer

        player = LobbyPlayer(
            slot=2,
            user_id=None,
            username="AI (dummy)",
            is_ai=True,
            ai_type="bot:dummy",
        )

        result = serialize_player(player)

        assert result["slot"] == 2
        assert result["userId"] is None
        assert result["isAi"] is True
        assert result["aiType"] == "bot:dummy"
        assert result["isReady"] is True  # AI always ready

    def test_serialize_settings(self) -> None:
        """Test serializing LobbySettings."""
        from kfchess.lobby.models import LobbySettings

        settings = LobbySettings(
            is_public=False,
            speed="lightning",
            player_count=4,
            is_ranked=True,
        )

        result = serialize_settings(settings)

        assert result["isPublic"] is False
        assert result["speed"] == "lightning"
        assert result["playerCount"] == 4
        assert result["isRanked"] is True

    def test_serialize_lobby(self) -> None:
        """Test serializing a Lobby."""
        from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus

        lobby = Lobby(
            id=1,
            code="ABC123",
            host_slot=1,
            settings=LobbySettings(),
        )
        lobby.players[1] = LobbyPlayer(slot=1, user_id=None, username="Host")
        lobby.status = LobbyStatus.WAITING
        lobby.current_game_id = None
        lobby.games_played = 0

        result = serialize_lobby(lobby)

        assert result["id"] == 1
        assert result["code"] == "ABC123"
        assert result["hostSlot"] == 1
        assert result["status"] == "waiting"
        assert result["currentGameId"] is None
        assert result["gamesPlayed"] == 0
        assert "settings" in result
        assert "players" in result
        assert 1 in result["players"]


class TestLobbyWebSocketEndpoint:
    """Tests for lobby WebSocket endpoint."""

    def test_websocket_connect_invalid_key(self, client: TestClient) -> None:
        """Test connecting with an invalid player key."""
        with pytest.raises(WebSocketDisconnect):
            with ws_connect(client,"/ws/lobby/NOTFOUND?player_key=invalid"):
                pass

    def test_websocket_connect_missing_key(self, client: TestClient) -> None:
        """Test connecting without a player key (should fail)."""
        with pytest.raises(WebSocketDisconnect):
            with ws_connect(client,"/ws/lobby/NOTFOUND"):
                pass

    def test_websocket_connect_valid_lobby(self, client: TestClient) -> None:
        """Test connecting to a valid lobby."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "lobby_state"
            assert "lobby" in msg
            assert msg["lobby"]["code"] == code

    def test_websocket_ping_pong(self, client: TestClient) -> None:
        """Test ping/pong functionality."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "ping"}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "pong"

    def test_websocket_invalid_json(self, client: TestClient) -> None:
        """Test sending invalid JSON."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text("not valid json")

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert msg["code"] == "invalid_json"

    def test_websocket_unknown_message_type(self, client: TestClient) -> None:
        """Test sending unknown message type."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "unknown_type"}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert msg["code"] == "unknown_message"


class TestLobbyReadyState:
    """Tests for lobby ready state via WebSocket."""

    def test_set_ready(self, client: TestClient) -> None:
        """Test setting ready state via WebSocket."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "ready", "ready": True}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "player_ready"
            assert msg["slot"] == 1
            assert msg["ready"] is True

    def test_set_unready(self, client: TestClient) -> None:
        """Test unsetting ready state via WebSocket."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "ready", "ready": True}))
            websocket.receive_text()  # player_ready

            websocket.send_text(json.dumps({"type": "ready", "ready": False}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "player_ready"
            assert msg["slot"] == 1
            assert msg["ready"] is False


class TestLobbyHostActions:
    """Tests for host-only lobby actions via WebSocket."""

    def test_update_settings(self, client: TestClient) -> None:
        """Test updating settings via WebSocket (host only)."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(
                json.dumps({
                    "type": "update_settings",
                    "settings": {
                        "isPublic": False,
                        "speed": "lightning",
                        "playerCount": 4,
                        "isRanked": False,
                    },
                })
            )

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "settings_updated"
            assert msg["settings"]["isPublic"] is False
            assert msg["settings"]["speed"] == "lightning"
            assert msg["settings"]["playerCount"] == 4

    def test_add_ai_player(self, client: TestClient) -> None:
        """Test adding an AI player via WebSocket (host only)."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "add_ai", "aiType": "bot:dummy"}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "player_joined"
            assert msg["slot"] == 2
            assert msg["player"]["isAi"] is True
            assert msg["player"]["aiType"] == "bot:dummy"

    def test_remove_ai_player(self, client: TestClient) -> None:
        """Test removing an AI player via WebSocket (host only)."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "remove_ai", "slot": 2}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "player_left"
            assert msg["slot"] == 2
            assert msg["reason"] == "removed"


class TestLobbyGameStart:
    """Tests for starting a game from a lobby via WebSocket."""

    def test_start_game_with_ai(self, client: TestClient) -> None:
        """Test starting game with AI (host auto-readied)."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            # Host auto-readied on start_game
            websocket.send_text(json.dumps({"type": "start_game"}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "game_starting"
            assert "gameId" in msg
            assert "playerKey" in msg
            assert msg["lobbyCode"] == code

    def test_start_game_all_ready(self, client: TestClient) -> None:
        """Test starting game when all players are ready."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "ready", "ready": True}))
            websocket.receive_text()  # player_ready

            websocket.send_text(json.dumps({"type": "start_game"}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "game_starting"
            assert "gameId" in msg
            assert "playerKey" in msg
            assert msg["lobbyCode"] == code


class TestLobbyNonHostErrors:
    """Tests for non-host attempting host-only actions."""

    def test_non_host_cannot_update_settings(self, client: TestClient) -> None:
        """Test that non-host cannot update settings."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]

        response = client.post(f"/api/lobbies/{code}/join", json={})
        data = response.json()
        player2_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player2_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(
                json.dumps({
                    "type": "update_settings",
                    "settings": {"isPublic": False},
                })
            )

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert msg["code"] == "not_host"

    def test_non_host_cannot_start_game(self, client: TestClient) -> None:
        """Test that non-host cannot start game."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]

        response = client.post(f"/api/lobbies/{code}/join", json={})
        data = response.json()
        player2_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player2_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "start_game"}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert msg["code"] == "not_host"


class TestLobbyKick:
    """Tests for kicking players via WebSocket."""

    def test_kick_player(self, client: TestClient) -> None:
        """Test kicking a player via WebSocket."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        client.post(f"/api/lobbies/{code}/join", json={})

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "kick", "slot": 2}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "player_left"
            assert msg["slot"] == 2
            assert msg["reason"] == "kicked"

    def test_cannot_kick_self(self, client: TestClient) -> None:
        """Test that host cannot kick themselves."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "kick", "slot": 1}))

            response = websocket.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "error"
            assert msg["code"] == "invalid_action"


class TestLobbyReturnToLobby:
    """Tests for returning to lobby after game."""

    def test_return_to_lobby(self, client: TestClient) -> None:
        """Test returning to lobby after game finished."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state

            # Start game
            websocket.send_text(json.dumps({"type": "ready", "ready": True}))
            websocket.receive_text()  # player_ready
            websocket.send_text(json.dumps({"type": "start_game"}))
            websocket.receive_text()  # game_starting

            # Simulate game ending via the notify_game_ended path
            # (normally called by game handler, here we call manager directly)
            import asyncio

            from kfchess.ws.lobby_handler import notify_game_ended

            loop = asyncio.new_event_loop()
            loop.run_until_complete(notify_game_ended(code, winner=1, reason="king_captured"))
            loop.close()

            # Should receive game_ended via pub/sub
            response_text = websocket.receive_text()
            msg = json.loads(response_text)
            assert msg["type"] == "game_ended"

            # Return to lobby
            websocket.send_text(json.dumps({"type": "return_to_lobby"}))

            response_text = websocket.receive_text()
            msg = json.loads(response_text)
            assert msg["type"] == "lobby_state"
            assert msg["lobby"]["status"] == "waiting"


class TestPlayerJoinedBroadcast:
    """Tests for player_joined broadcast when WebSocket connects."""

    def test_player_joined_broadcast_to_host(self, client: TestClient) -> None:
        """Test that host receives player_joined when second player connects."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        response = client.post(f"/api/lobbies/{code}/join", json={})
        player2_data = response.json()
        player2_key = player2_data["playerKey"]
        player2_slot = player2_data["slot"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as host_ws:
            response = host_ws.receive_text()
            msg = json.loads(response)
            assert msg["type"] == "lobby_state"

            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state

                # Host should receive player_joined via pub/sub
                response = host_ws.receive_text()
                msg = json.loads(response)
                assert msg["type"] == "player_joined"
                assert msg["slot"] == player2_slot
                assert "player" in msg
                assert msg["player"]["slot"] == player2_slot


class TestFindLobbyByGame:
    """Tests for finding lobby by game ID."""

    def test_find_lobby_by_game_after_start(self, client: TestClient) -> None:
        """Test finding lobby code by game ID after game starts."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={player_key}") as websocket:
            websocket.receive_text()  # lobby_state
            websocket.send_text(json.dumps({"type": "ready", "ready": True}))
            websocket.receive_text()  # player_ready
            websocket.send_text(json.dumps({"type": "start_game"}))

            response_text = websocket.receive_text()
            msg = json.loads(response_text)
            assert msg["type"] == "game_starting"
            game_id = msg["gameId"]

            # Verify lobby can be found by game ID
            import asyncio

            from kfchess.lobby.manager import get_lobby_manager

            manager = get_lobby_manager()
            loop = asyncio.new_event_loop()
            found_code = loop.run_until_complete(manager.find_lobby_by_game(game_id))
            loop.close()
            assert found_code == code

    def test_find_lobby_by_game_not_found(self) -> None:
        """Test finding lobby returns None for unknown game ID."""
        import asyncio

        from kfchess.lobby.manager import get_lobby_manager

        manager = get_lobby_manager()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(manager.find_lobby_by_game("UNKNOWN_GAME"))
        loop.close()
        assert result is None


class TestMultipleHumanPlayers:
    """Tests for lobbies with multiple human players."""

    def test_two_humans_receive_game_starting(self, client: TestClient) -> None:
        """Test that both human players receive game_starting message."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        response = client.post(f"/api/lobbies/{code}/join", json={})
        player2_data = response.json()
        player2_key = player2_data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as host_ws:
            host_ws.receive_text()  # lobby_state

            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state
                host_ws.receive_text()  # player_joined for player 2

                # Both players set ready
                host_ws.send_text(json.dumps({"type": "ready", "ready": True}))
                p2_ws.send_text(json.dumps({"type": "ready", "ready": True}))

                # Receive ready broadcasts (each player sees both readys via pub/sub)
                host_ws.receive_text()  # player_ready
                host_ws.receive_text()  # player_ready
                p2_ws.receive_text()  # player_ready
                p2_ws.receive_text()  # player_ready

                # Host starts game
                host_ws.send_text(json.dumps({"type": "start_game"}))

                # Both should receive game_starting
                host_response = host_ws.receive_text()
                host_msg = json.loads(host_response)
                assert host_msg["type"] == "game_starting"
                assert "gameId" in host_msg
                assert "playerKey" in host_msg

                p2_response = p2_ws.receive_text()
                p2_msg = json.loads(p2_response)
                assert p2_msg["type"] == "game_starting"
                assert p2_msg["gameId"] == host_msg["gameId"]
                assert "playerKey" in p2_msg


class TestChangeAiType:
    """Tests for changing AI type via WebSocket."""

    def test_change_ai_type(self, client: TestClient) -> None:
        """Test changing AI difficulty via WebSocket."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(
                json.dumps({"type": "change_ai_type", "slot": 2, "aiType": "bot:expert"})
            )

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "ai_type_changed"
            assert msg["slot"] == 2
            assert msg["aiType"] == "bot:expert"
            assert "Expert" in msg["player"]["username"]

    def test_change_ai_type_missing_slot(self, client: TestClient) -> None:
        """Test change_ai_type with missing slot returns error."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "change_ai_type", "aiType": "bot:expert"}))

            msg = json.loads(websocket.receive_text())
            assert msg["type"] == "error"
            assert msg["code"] == "missing_slot"


class TestLeaveViaWebSocket:
    """Tests for the leave message type via WebSocket."""

    def test_leave_publishes_player_left(self, client: TestClient) -> None:
        """Test that sending leave publishes player_left to other players."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        # Join a second player
        response = client.post(f"/api/lobbies/{code}/join", json={})
        player2_data = response.json()
        player2_key = player2_data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as host_ws:
            host_ws.receive_text()  # lobby_state

            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state
                host_ws.receive_text()  # player_joined for p2

                # Player 2 sends leave
                p2_ws.send_text(json.dumps({"type": "leave"}))

                # Both should receive player_left via pub/sub
                # (player 2 sees their own leave since it's not filtered)
                p2_msg = json.loads(p2_ws.receive_text())
                assert p2_msg["type"] == "player_left"
                assert p2_msg["slot"] == 2
                assert p2_msg["reason"] == "left"

            # Host should also receive player_left
            host_msg = json.loads(host_ws.receive_text())
            assert host_msg["type"] == "player_left"
            assert host_msg["slot"] == 2

    def test_last_human_leave_deletes_lobby(self, client: TestClient) -> None:
        """Test that the last human leaving deletes the lobby."""
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {"isPublic": True, "speed": "standard", "playerCount": 2},
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as websocket:
            websocket.receive_text()  # lobby_state

            websocket.send_text(json.dumps({"type": "leave"}))

        # Lobby should be deleted
        get_response = client.get(f"/api/lobbies/{code}")
        assert get_response.status_code == 404


class TestDisconnectFlow:
    """Tests for WebSocket disconnect handling."""

    def test_disconnect_publishes_player_disconnected(self, client: TestClient) -> None:
        """Test that disconnecting publishes player_disconnected to other players."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        # Join a second player
        response = client.post(f"/api/lobbies/{code}/join", json={})
        player2_data = response.json()
        player2_key = player2_data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as host_ws:
            host_ws.receive_text()  # lobby_state

            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state
                host_ws.receive_text()  # player_joined for p2

            # Player 2 WS disconnected (exited context manager)
            # Host should receive player_disconnected via pub/sub
            msg = json.loads(host_ws.receive_text())
            assert msg["type"] == "player_disconnected"
            assert msg["slot"] == 2


class TestReconnectFlow:
    """Tests for WebSocket reconnection handling."""

    def test_reconnect_publishes_player_reconnected(self, client: TestClient) -> None:
        """Test that reconnecting publishes player_reconnected to other players."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        # Join a second player
        response = client.post(f"/api/lobbies/{code}/join", json={})
        player2_data = response.json()
        player2_key = player2_data["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as host_ws:
            host_ws.receive_text()  # lobby_state

            # Player 2 connects then disconnects
            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state
                host_ws.receive_text()  # player_joined for p2

            # Player 2 disconnected
            host_ws.receive_text()  # player_disconnected

            # Player 2 reconnects
            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_lobby_state = json.loads(p2_ws.receive_text())
                assert p2_lobby_state["type"] == "lobby_state"

                # Host should receive player_reconnected
                msg = json.loads(host_ws.receive_text())
                assert msg["type"] == "player_reconnected"
                assert msg["slot"] == 2

    def test_reconnecting_player_does_not_see_own_reconnect(self, client: TestClient) -> None:
        """Test that the reconnecting player doesn't receive their own player_reconnected."""
        response = client.post(
            "/api/lobbies",
            json={"settings": {"isPublic": True, "speed": "standard", "playerCount": 2}},
        )
        data = response.json()
        code = data["code"]
        host_key = data["playerKey"]

        response = client.post(f"/api/lobbies/{code}/join", json={})
        player2_key = response.json()["playerKey"]

        with ws_connect(client,f"/ws/lobby/{code}?player_key={host_key}") as host_ws:
            host_ws.receive_text()  # lobby_state

            # Player 2 connects then disconnects
            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state
                host_ws.receive_text()  # player_joined

            host_ws.receive_text()  # player_disconnected

            # Player 2 reconnects
            with ws_connect(client,
                f"/ws/lobby/{code}?player_key={player2_key}"
            ) as p2_ws:
                p2_ws.receive_text()  # lobby_state

                # Player 2 should NOT see their own player_reconnected
                # Send a ping to verify the next message is pong (not player_reconnected)
                p2_ws.send_text(json.dumps({"type": "ping"}))
                msg = json.loads(p2_ws.receive_text())
                assert msg["type"] == "pong"

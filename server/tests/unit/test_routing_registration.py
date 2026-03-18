"""Tests that routing registration is called at all game creation sites.

Verifies that register_routing is awaited when games are
created via quickplay, campaign, and lobby paths.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from concurrent.futures import CancelledError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis import FakeServer
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from kfchess.auth import current_active_user
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
    """Clear games and lobbies before each test."""
    global _fake_server
    _fake_server = FakeServer()

    service = get_game_service()
    service.games.clear()
    reset_lobby_manager()

    with (
        patch("kfchess.redis.lobby_store.get_redis", _fake_get_redis),
        patch("kfchess.ws.lobby_handler.get_redis", _fake_get_redis),
    ):
        yield


class TestQuickplayRoutingRegistration:
    """Routing registration on quickplay game creation."""

    def test_create_game_registers_routing(self, client: TestClient) -> None:
        """POST /api/games calls register_routing."""
        with patch(
            "kfchess.api.games.register_routing", new_callable=AsyncMock
        ) as mock_register:
            response = client.post("/api/games", json={})

        assert response.status_code == 200
        game_id = response.json()["game_id"]
        mock_register.assert_awaited_once_with(game_id)

    def test_create_game_with_ai_registers_routing(self, client: TestClient) -> None:
        """Quickplay vs AI also calls register_routing."""
        with patch(
            "kfchess.api.games.register_routing", new_callable=AsyncMock
        ) as mock_register:
            response = client.post(
                "/api/games", json={"opponent": "novice"}
            )

        assert response.status_code == 200
        mock_register.assert_awaited_once()


class TestCampaignRoutingRegistration:
    """Routing registration on campaign game creation."""

    def test_start_campaign_registers_routing(self, client: TestClient) -> None:
        """Starting a campaign game calls register_routing."""
        # Create a fake authenticated user
        fake_user = MagicMock()
        fake_user.id = 1
        fake_user.username = "TestPlayer"
        fake_user.picture_url = None

        app.dependency_overrides[current_active_user] = lambda: fake_user

        try:
            with (
                patch(
                    "kfchess.api.campaign.register_routing", new_callable=AsyncMock
                ) as mock_register,
                # Bypass DB progress check — level 0 is always unlocked
                patch("kfchess.api.campaign.async_session_factory") as mock_session_factory,
            ):
                # Mock the session context manager for the progress check
                mock_session = AsyncMock()
                mock_session_factory.return_value.__aenter__ = AsyncMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__aexit__ = AsyncMock(
                    return_value=False
                )
                # Mock CampaignProgressRepository + CampaignService
                mock_progress = MagicMock()
                mock_progress.is_level_unlocked.return_value = True
                with patch(
                    "kfchess.api.campaign.CampaignService"
                ) as mock_svc_cls:
                    mock_svc = AsyncMock()
                    mock_svc.get_progress.return_value = mock_progress
                    mock_svc_cls.return_value = mock_svc

                    response = client.post("/api/campaign/levels/0/start")

            assert response.status_code == 200
            game_id = response.json()["gameId"]
            mock_register.assert_awaited_once_with(game_id)
        finally:
            app.dependency_overrides.pop(current_active_user, None)


class TestLobbyRoutingRegistration:
    """Routing registration on lobby game creation."""

    def test_lobby_game_start_registers_routing(self, client: TestClient) -> None:
        """Starting a game from lobby calls register_routing."""
        # Create a lobby with AI
        response = client.post(
            "/api/lobbies",
            json={
                "settings": {
                    "isPublic": True,
                    "speed": "standard",
                    "playerCount": 2,
                },
                "addAi": True,
            },
        )
        data = response.json()
        code = data["code"]
        player_key = data["playerKey"]

        with patch(
            "kfchess.ws.lobby_handler.register_routing", new_callable=AsyncMock
        ) as mock_register:
            try:
                with client.websocket_connect(
                    f"/ws/lobby/{code}?player_key={player_key}"
                ) as websocket:
                    # Skip initial state
                    websocket.receive_text()

                    # Set ready
                    websocket.send_text(json.dumps({"type": "ready", "ready": True}))
                    websocket.receive_text()  # Skip player_ready broadcast

                    # Start game
                    websocket.send_text(json.dumps({"type": "start_game"}))

                    # Receive game_starting
                    msg = json.loads(websocket.receive_text())
                    assert msg["type"] == "game_starting"
            except CancelledError:
                pass

            mock_register.assert_awaited_once()

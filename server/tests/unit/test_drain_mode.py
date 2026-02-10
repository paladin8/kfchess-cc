"""Tests for drain mode integration with health check and game creation endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from kfchess.drain import set_draining


@pytest.fixture(autouse=True)
def _reset_drain():
    """Reset drain state before and after each test."""
    set_draining(False)
    yield
    set_draining(False)


@pytest.fixture
async def client():
    """Create an async test client that bypasses lifespan."""
    from kfchess.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthCheckDrain:
    """Tests for health check during drain mode."""

    @pytest.mark.asyncio
    async def test_health_check_ok_when_not_draining(self, client) -> None:
        """Health check returns 200 when not draining."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_check_503_when_draining(self, client) -> None:
        """Health check returns 503 during drain mode."""
        set_draining(True)

        response = await client.get("/health")
        assert response.status_code == 503
        assert "draining" in response.json()["detail"].lower()


class TestGameCreationDrain:
    """Tests for game creation blocked during drain mode."""

    @pytest.mark.asyncio
    async def test_create_game_returns_503_when_draining(self, client) -> None:
        """POST /api/games returns 503 during drain mode."""
        set_draining(True)

        response = await client.post(
            "/api/games",
            json={"speed": "standard", "board_type": "standard", "opponent": "bot:novice"},
        )
        assert response.status_code == 503
        assert "shutting down" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_campaign_start_returns_503_when_draining(self, client) -> None:
        """POST /api/campaign/levels/{id}/start returns 503 during drain mode."""
        from kfchess.auth import current_active_user
        from kfchess.db.models import User
        from kfchess.main import app

        set_draining(True)

        mock_user = User(
            id=1,
            email="test@example.com",
            hashed_password="fake",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )

        app.dependency_overrides[current_active_user] = lambda: mock_user
        try:
            response = await client.post("/api/campaign/levels/1/start")
        finally:
            app.dependency_overrides.pop(current_active_user, None)

        assert response.status_code == 503
        assert "shutting down" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_game_allowed_when_not_draining(self, client) -> None:
        """POST /api/games succeeds when not draining."""
        # Mock the game service to avoid actual game creation
        from kfchess.services.game_service import GameService

        with patch.object(
            GameService,
            "create_game",
            return_value=("GAME1234", "player_key_123", 1),
        ):
            response = await client.post(
                "/api/games",
                json={"speed": "standard", "board_type": "standard", "opponent": "bot:novice"},
            )
        assert response.status_code == 200

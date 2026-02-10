"""Tests for WebSocket game routing (redirect logic)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from kfchess.ws.handler import handle_websocket


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_service():
    """Create a mock GameService with no games."""
    service = MagicMock()
    service.get_game.return_value = None
    service.validate_player_key.return_value = None
    return service


class TestWebSocketRedirect:
    """Tests for the redirect logic in handle_websocket."""

    @pytest.mark.asyncio
    async def test_redirect_to_other_server(
        self, mock_websocket, mock_service
    ) -> None:
        """Game on another server triggers 4302 redirect."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="worker2")

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="worker1"),
            ),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.close.assert_called_once_with(code=4302, reason="worker2")

    @pytest.mark.asyncio
    async def test_no_routing_key_returns_4004(
        self, mock_websocket, mock_service
    ) -> None:
        """No routing key in Redis returns 4004."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.close.assert_called_once_with(
            code=4004, reason="Game not found"
        )

    @pytest.mark.asyncio
    async def test_stale_self_routing_returns_4004(
        self, mock_websocket, mock_service
    ) -> None:
        """Routing key pointing to our own server but game not in memory = stale."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="worker1")

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="worker1"),
            ),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.close.assert_called_once_with(
            code=4004, reason="Game not found"
        )

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_to_4004(
        self, mock_websocket, mock_service
    ) -> None:
        """Redis error during routing check falls through to 4004."""
        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch(
                "kfchess.ws.handler.get_redis",
                side_effect=Exception("Redis connection failed"),
            ),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.close.assert_called_once_with(
            code=4004, reason="Game not found"
        )

    @pytest.mark.asyncio
    async def test_redirect_preserves_server_id_in_reason(
        self, mock_websocket, mock_service
    ) -> None:
        """The server_id is passed as the close reason."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="worker3")

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="worker1"),
            ),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.close.assert_called_once_with(code=4302, reason="worker3")

    @pytest.mark.asyncio
    async def test_local_game_skips_redirect(self, mock_websocket) -> None:
        """Game found locally proceeds normally (no redirect check)."""
        mock_state = MagicMock()
        mock_state.game_id = "GAME1234"
        mock_state.status.value = "playing"
        mock_state.board.pieces = []
        mock_state.active_moves = []
        mock_state.cooldowns = []
        mock_state.current_tick = 10
        mock_state.config.ticks_per_square = 10

        mock_managed = MagicMock()
        mock_managed.state = mock_state
        mock_managed.player_keys = {}
        mock_managed.draw_offers = set()
        mock_managed.campaign_level_id = None

        mock_service = MagicMock()
        mock_service.get_game.return_value = mock_state
        mock_service.validate_player_key.return_value = None
        mock_service.games = {"GAME1234": mock_managed}
        mock_service.get_managed_game.return_value = mock_managed

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis") as mock_get_redis,
            patch(
                "kfchess.ws.handler.connection_manager"
            ) as mock_cm,
        ):
            # Make the WS accept and then disconnect
            mock_websocket.receive_text = AsyncMock(
                side_effect=Exception("disconnect")
            )
            mock_cm.connect = AsyncMock()
            mock_cm.disconnect = AsyncMock()

            await handle_websocket(mock_websocket, "GAME1234", None)

            # Redis routing should NOT have been checked
            mock_get_redis.assert_not_called()

    @pytest.mark.asyncio
    async def test_redirect_with_player_key(
        self, mock_websocket, mock_service
    ) -> None:
        """Redirect works the same with or without player_key."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="worker2")

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="worker1"),
            ),
        ):
            await handle_websocket(
                mock_websocket, "GAME1234", "p1_some_key"
            )

        # Should redirect before even checking the player key
        mock_websocket.close.assert_called_once_with(code=4302, reason="worker2")


class TestWebSocketAcceptBeforeClose:
    """Tests that WebSocket is accepted before sending custom close codes.

    ASGI servers (Uvicorn) send HTTP 403 if you close without accept,
    which means the client never receives the custom close code/reason.
    """

    @pytest.mark.asyncio
    async def test_accept_called_before_redirect_close(
        self, mock_websocket, mock_service
    ) -> None:
        """WebSocket is accepted before 4302 close."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="worker2")

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
            patch(
                "kfchess.ws.handler.get_settings",
                return_value=MagicMock(effective_server_id="worker1"),
            ),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.accept.assert_awaited_once()
        mock_websocket.close.assert_awaited_once_with(code=4302, reason="worker2")
        # accept must come before close
        assert mock_websocket.method_calls.index(
            call.accept()
        ) < mock_websocket.method_calls.index(
            call.close(code=4302, reason="worker2")
        )

    @pytest.mark.asyncio
    async def test_accept_called_before_4004_close(
        self, mock_websocket, mock_service
    ) -> None:
        """WebSocket is accepted before 4004 close."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch("kfchess.ws.handler.get_game_service", return_value=mock_service),
            patch("kfchess.ws.handler.get_redis", return_value=mock_redis),
        ):
            await handle_websocket(mock_websocket, "GAME1234", None)

        mock_websocket.accept.assert_awaited_once()
        mock_websocket.close.assert_awaited_once_with(
            code=4004, reason="Game not found"
        )

    @pytest.mark.asyncio
    async def test_accept_called_before_4001_close(self, mock_websocket) -> None:
        """WebSocket is accepted before 4001 (invalid player key) close."""
        mock_state = MagicMock()
        mock_service = MagicMock()
        mock_service.get_game.return_value = mock_state
        mock_service.validate_player_key.return_value = None

        with patch(
            "kfchess.ws.handler.get_game_service", return_value=mock_service
        ):
            await handle_websocket(mock_websocket, "GAME1234", "bad_key")

        mock_websocket.accept.assert_awaited_once()
        mock_websocket.close.assert_awaited_once_with(
            code=4001, reason="Invalid player key"
        )

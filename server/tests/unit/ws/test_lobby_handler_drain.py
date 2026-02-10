"""Tests for lobby WebSocket drain mode features."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kfchess.drain import set_draining
from kfchess.ws.lobby_handler import (
    _active_lobby_websockets,
    close_all_lobby_websockets,
)


@pytest.fixture(autouse=True)
def _reset_drain():
    """Reset drain state before and after each test."""
    set_draining(False)
    yield
    set_draining(False)


@pytest.fixture(autouse=True)
def _reset_lobby_registry():
    """Clear the lobby WS registry before and after each test."""
    _active_lobby_websockets.clear()
    yield
    _active_lobby_websockets.clear()


class TestLobbyWsRegistry:
    """Tests for lobby WebSocket connection tracking."""

    def test_registry_starts_empty(self) -> None:
        """The lobby WS registry is empty initially."""
        assert len(_active_lobby_websockets) == 0

    def test_adding_websocket(self) -> None:
        """WebSocket can be added to the registry."""
        ws = AsyncMock()
        _active_lobby_websockets.add(ws)
        assert ws in _active_lobby_websockets

    def test_discarding_websocket(self) -> None:
        """WebSocket can be removed from the registry."""
        ws = AsyncMock()
        _active_lobby_websockets.add(ws)
        _active_lobby_websockets.discard(ws)
        assert ws not in _active_lobby_websockets

    def test_discard_nonexistent_is_noop(self) -> None:
        """Discarding a non-existent WebSocket doesn't raise."""
        ws = AsyncMock()
        _active_lobby_websockets.discard(ws)  # Should not raise


class TestCloseAllLobbyWebsockets:
    """Tests for close_all_lobby_websockets."""

    @pytest.mark.asyncio
    async def test_closes_all_connections(self) -> None:
        """close_all_lobby_websockets closes every tracked connection."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        _active_lobby_websockets.add(ws1)
        _active_lobby_websockets.add(ws2)
        _active_lobby_websockets.add(ws3)

        await close_all_lobby_websockets(code=4301, reason="shutting down")

        ws1.close.assert_called_once_with(code=4301, reason="shutting down")
        ws2.close.assert_called_once_with(code=4301, reason="shutting down")
        ws3.close.assert_called_once_with(code=4301, reason="shutting down")

    @pytest.mark.asyncio
    async def test_handles_already_closed(self) -> None:
        """Handles already-closed WebSockets without crashing."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws2.close.side_effect = RuntimeError("Already closed")

        _active_lobby_websockets.add(ws1)
        _active_lobby_websockets.add(ws2)

        # Should not raise
        await close_all_lobby_websockets(code=4301, reason="shutting down")

        ws1.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_registry_is_noop(self) -> None:
        """close_all on empty registry is a no-op."""
        await close_all_lobby_websockets(code=4301, reason="shutting down")
        # Should complete without error


class TestLobbyStartGameDrain:
    """Tests for start_game blocked during drain."""

    @pytest.mark.asyncio
    async def test_start_game_blocked_during_drain(self) -> None:
        """The start_game message handler returns error during drain."""
        import json

        set_draining(True)

        ws = AsyncMock()
        ws.send_text = AsyncMock()

        # Test _handle_message directly (avoids the receive_text loop)
        from kfchess.ws.lobby_handler import _handle_message

        manager = AsyncMock()
        # cleanup_expired calls cleanup_disconnected_players — return empty to skip
        manager.cleanup_disconnected_players = AsyncMock(return_value=[])

        await _handle_message(
            ws, manager, "LOBBY1", 1, "player_key",
            {"type": "start_game"},
        )

        # Should have sent an error about draining
        ws.send_text.assert_called_once()
        sent_data = json.loads(ws.send_text.call_args[0][0])
        assert sent_data["type"] == "error"
        assert sent_data["code"] == "server_draining"

    @pytest.mark.asyncio
    async def test_start_game_allowed_when_not_draining(self) -> None:
        """The start_game message handler works normally when not draining."""
        import json

        from kfchess.lobby.manager import LobbyError
        from kfchess.ws.lobby_handler import _handle_message

        ws = AsyncMock()
        ws.send_text = AsyncMock()

        manager = AsyncMock()
        # cleanup_expired calls cleanup_disconnected_players — return empty to skip
        manager.cleanup_disconnected_players = AsyncMock(return_value=[])
        # Return an error to keep the test simple (no need to mock game creation)
        manager.start_game = AsyncMock(
            return_value=LobbyError(code="not_host", message="Only host can start")
        )

        await _handle_message(
            ws, manager, "LOBBY1", 1, "player_key",
            {"type": "start_game"},
        )

        # Should have called start_game (not blocked by drain)
        manager.start_game.assert_called_once()
        sent_data = json.loads(ws.send_text.call_args[0][0])
        assert sent_data["type"] == "error"
        assert sent_data["code"] == "not_host"

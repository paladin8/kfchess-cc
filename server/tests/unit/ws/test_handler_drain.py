"""Tests for ConnectionManager.close_all() method."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kfchess.ws.handler import ConnectionManager


@pytest.fixture
def manager():
    """Create a fresh ConnectionManager."""
    return ConnectionManager()


def _make_mock_ws(player: int | None = None):
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.close = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestConnectionManagerCloseAll:
    """Tests for close_all method."""

    @pytest.mark.asyncio
    async def test_close_all_closes_every_connection(self, manager) -> None:
        """close_all closes all connections across all games."""
        ws1 = _make_mock_ws()
        ws2 = _make_mock_ws()
        ws3 = _make_mock_ws()

        await manager.connect("GAME1", ws1, 1)
        await manager.connect("GAME1", ws2, 2)
        await manager.connect("GAME2", ws3, 1)

        await manager.close_all(code=4301, reason="shutting down")

        ws1.close.assert_called_once_with(code=4301, reason="shutting down")
        ws2.close.assert_called_once_with(code=4301, reason="shutting down")
        ws3.close.assert_called_once_with(code=4301, reason="shutting down")

    @pytest.mark.asyncio
    async def test_close_all_clears_connections_dict(self, manager) -> None:
        """After close_all, the connections dict is empty."""
        ws1 = _make_mock_ws()
        ws2 = _make_mock_ws()

        await manager.connect("GAME1", ws1, 1)
        await manager.connect("GAME2", ws2, 1)

        await manager.close_all(code=4301, reason="shutting down")

        assert manager.connections == {}
        assert not manager.has_connections("GAME1")
        assert not manager.has_connections("GAME2")

    @pytest.mark.asyncio
    async def test_close_all_handles_already_closed(self, manager) -> None:
        """close_all handles already-closed connections without error."""
        ws1 = _make_mock_ws()
        ws2 = _make_mock_ws()
        ws2.close.side_effect = RuntimeError("Already closed")

        await manager.connect("GAME1", ws1, 1)
        await manager.connect("GAME1", ws2, 2)

        # Should not raise
        await manager.close_all(code=4301, reason="shutting down")

        # ws1 should still be closed successfully
        ws1.close.assert_called_once()
        # Connections should be cleared even with errors
        assert manager.connections == {}

    @pytest.mark.asyncio
    async def test_close_all_uses_custom_code(self, manager) -> None:
        """close_all passes the correct code and reason."""
        ws = _make_mock_ws()
        await manager.connect("GAME1", ws, 1)

        await manager.close_all(code=1000, reason="normal close")

        ws.close.assert_called_once_with(code=1000, reason="normal close")

    @pytest.mark.asyncio
    async def test_close_all_on_empty_manager(self, manager) -> None:
        """close_all on empty manager is a no-op."""
        await manager.close_all(code=4301, reason="shutting down")
        assert manager.connections == {}

    @pytest.mark.asyncio
    async def test_close_all_with_spectators(self, manager) -> None:
        """close_all closes spectator connections (player=None)."""
        ws_player = _make_mock_ws()
        ws_spectator = _make_mock_ws()

        await manager.connect("GAME1", ws_player, 1)
        await manager.connect("GAME1", ws_spectator, None)

        await manager.close_all(code=4301, reason="shutting down")

        ws_player.close.assert_called_once()
        ws_spectator.close.assert_called_once()

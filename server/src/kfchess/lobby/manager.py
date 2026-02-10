"""Lobby manager for Kung Fu Chess.

This module provides the singleton access to the lobby manager.
The actual implementation is in redis.lobby_store.RedisLobbyManager.
"""

from __future__ import annotations

from kfchess.redis.lobby_store import LobbyError, RedisLobbyManager

# Re-export LobbyError for backward compatibility
__all__ = ["LobbyError", "get_lobby_manager", "reset_lobby_manager"]

# Global singleton instance
_lobby_manager: RedisLobbyManager | None = None


def get_lobby_manager() -> RedisLobbyManager:
    """Get the global lobby manager instance."""
    global _lobby_manager
    if _lobby_manager is None:
        _lobby_manager = RedisLobbyManager()
    return _lobby_manager


def reset_lobby_manager() -> None:
    """Reset the global lobby manager. Used for testing."""
    global _lobby_manager
    _lobby_manager = None

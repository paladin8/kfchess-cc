"""Lobby system for Kung Fu Chess.

This module provides the lobby functionality for pre-game player gathering.
Every game goes through a lobby, including AI games and campaign levels.
"""

from kfchess.lobby.manager import (
    LobbyError,
    LobbyManager,
    get_lobby_manager,
    init_lobby_manager,
    reset_lobby_manager,
)
from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus

__all__ = [
    "Lobby",
    "LobbyError",
    "LobbyManager",
    "LobbyPlayer",
    "LobbySettings",
    "LobbyStatus",
    "get_lobby_manager",
    "init_lobby_manager",
    "reset_lobby_manager",
]

"""WebSocket handler for lobby real-time communication."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from kfchess.lobby.manager import LobbyError, get_lobby_manager
from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus

logger = logging.getLogger(__name__)


def serialize_player(player: LobbyPlayer) -> dict[str, Any]:
    """Serialize a LobbyPlayer to JSON-compatible dict."""
    return {
        "slot": player.slot,
        "userId": player.user_id,
        "username": player.username,
        "isAi": player.is_ai,
        "aiType": player.ai_type,
        "isReady": player.is_ready,
        "isConnected": player.is_connected,
    }


def serialize_settings(settings: LobbySettings) -> dict[str, Any]:
    """Serialize LobbySettings to JSON-compatible dict."""
    return {
        "isPublic": settings.is_public,
        "speed": settings.speed,
        "playerCount": settings.player_count,
        "isRanked": settings.is_ranked,
    }


def serialize_lobby(lobby: Lobby) -> dict[str, Any]:
    """Serialize a Lobby to JSON-compatible dict."""
    return {
        "id": lobby.id,
        "code": lobby.code,
        "hostSlot": lobby.host_slot,
        "settings": serialize_settings(lobby.settings),
        "players": {slot: serialize_player(p) for slot, p in lobby.players.items()},
        "status": lobby.status.value,
        "currentGameId": lobby.current_game_id,
        "gamesPlayed": lobby.games_played,
    }


class LobbyConnectionManager:
    """Manages WebSocket connections for lobbies.

    Each lobby can have multiple connected players (but not spectators).
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        # code -> set of (websocket, slot)
        self.connections: dict[str, set[tuple[WebSocket, int]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, code: str, websocket: WebSocket, slot: int) -> None:
        """Add a WebSocket connection to a lobby.

        Args:
            code: The lobby code
            websocket: The WebSocket connection
            slot: Player slot (1-4)
        """
        await websocket.accept()
        async with self._lock:
            if code not in self.connections:
                self.connections[code] = set()
            self.connections[code].add((websocket, slot))
        logger.info(f"Player slot {slot} connected to lobby {code}")

    async def disconnect(self, code: str, websocket: WebSocket) -> int | None:
        """Remove a WebSocket connection from a lobby.

        Args:
            code: The lobby code
            websocket: The WebSocket connection

        Returns:
            The slot of the disconnected player, or None if not found
        """
        async with self._lock:
            if code not in self.connections:
                return None

            # Find and remove this websocket
            to_remove = None
            slot = None
            for conn in self.connections[code]:
                if conn[0] == websocket:
                    to_remove = conn
                    slot = conn[1]
                    break
            if to_remove:
                self.connections[code].discard(to_remove)
                logger.info(f"Player slot {slot} disconnected from lobby {code}")

            # Clean up empty lobby connections
            if not self.connections[code]:
                del self.connections[code]

            return slot

    async def broadcast(self, code: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all connections for a lobby.

        Args:
            code: The lobby code
            message: The message to send (will be JSON encoded)
        """
        async with self._lock:
            connections = self.connections.get(code, set()).copy()

        if not connections:
            return

        data = json.dumps(message)
        disconnected: list[tuple[WebSocket, int]] = []

        for websocket, slot in connections:
            try:
                await websocket.send_text(data)
            except Exception:
                disconnected.append((websocket, slot))

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                if code in self.connections:
                    for conn in disconnected:
                        self.connections[code].discard(conn)

    async def send_to_slot(self, code: str, slot: int, message: dict[str, Any]) -> None:
        """Send a message to a specific player slot.

        Args:
            code: The lobby code
            slot: The player slot
            message: The message to send
        """
        async with self._lock:
            connections = self.connections.get(code, set()).copy()

        data = json.dumps(message)

        for websocket, player_slot in connections:
            if player_slot == slot:
                try:
                    await websocket.send_text(data)
                except Exception:
                    pass  # Will be cleaned up on next broadcast

    async def broadcast_to_others(
        self, code: str, exclude_slot: int, message: dict[str, Any]
    ) -> None:
        """Broadcast a message to all connections except the specified slot.

        Args:
            code: The lobby code
            exclude_slot: The slot to exclude from broadcast
            message: The message to send (will be JSON encoded)
        """
        async with self._lock:
            connections = self.connections.get(code, set()).copy()

        if not connections:
            return

        data = json.dumps(message)
        disconnected: list[tuple[WebSocket, int]] = []

        for websocket, slot in connections:
            if slot == exclude_slot:
                continue
            try:
                await websocket.send_text(data)
            except Exception:
                disconnected.append((websocket, slot))

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                if code in self.connections:
                    for conn in disconnected:
                        self.connections[code].discard(conn)

    def has_connections(self, code: str) -> bool:
        """Check if a lobby has any connections."""
        return code in self.connections and len(self.connections[code]) > 0

    async def remove_lobby(self, code: str) -> None:
        """Remove all connections for a lobby (used when lobby is deleted)."""
        async with self._lock:
            if code in self.connections:
                del self.connections[code]


# Global connection manager instance
lobby_connection_manager = LobbyConnectionManager()


async def _cleanup_and_broadcast(code: str) -> None:
    """Clean up expired disconnected players and broadcast removals.

    Args:
        code: The lobby code
    """
    manager = get_lobby_manager()
    cleaned_slots = await manager.cleanup_disconnected_players(code)

    # Broadcast player removals
    for slot in cleaned_slots:
        await lobby_connection_manager.broadcast(
            code,
            {"type": "player_left", "slot": slot, "reason": "disconnected"},
        )

    # Check if host changed (if host was removed)
    if cleaned_slots:
        lobby = manager.get_lobby(code)
        if lobby:
            # Broadcast updated lobby state so clients have correct host
            await lobby_connection_manager.broadcast(
                code,
                {"type": "lobby_state", "lobby": serialize_lobby(lobby)},
            )


async def handle_lobby_websocket(
    websocket: WebSocket,
    code: str,
    player_key: str,
) -> None:
    """Handle a WebSocket connection for a lobby.

    Args:
        websocket: The WebSocket connection
        code: The lobby code
        player_key: The player's secret key
    """
    logger.info(f"Lobby WebSocket connection attempt: code={code}")

    manager = get_lobby_manager()

    # Clean up any expired disconnected players (stateless grace period check)
    await _cleanup_and_broadcast(code)

    # Validate player key
    slot = manager.validate_player_key(code, player_key)
    if slot is None:
        logger.warning(f"Lobby WebSocket rejected: invalid player key for lobby {code}")
        await websocket.close(code=4001, reason="Invalid player key")
        return

    # Get lobby
    lobby = manager.get_lobby(code)
    if lobby is None:
        logger.warning(f"Lobby WebSocket rejected: lobby {code} not found")
        await websocket.close(code=4004, reason="Lobby not found")
        return

    # Check if this is a reconnection (player exists but was marked disconnected)
    player = lobby.players.get(slot)
    is_reconnection = player is not None and not player.is_connected

    if is_reconnection:
        logger.info(f"Player slot {slot} reconnected to lobby {code}")

        # Mark player as connected
        await manager.set_connected(code, slot, True)

        # Refresh lobby state after update
        lobby = manager.get_lobby(code)
        if lobby is None:
            await websocket.close(code=4004, reason="Lobby not found")
            return

    # Connect
    await lobby_connection_manager.connect(code, websocket, slot)

    # Send initial state to the connecting player
    await websocket.send_text(
        json.dumps(
            {
                "type": "lobby_state",
                "lobby": serialize_lobby(lobby),
            }
        )
    )

    # Broadcast to OTHER connected players
    player = lobby.players.get(slot)
    if player:
        if is_reconnection:
            # Broadcast reconnection
            await lobby_connection_manager.broadcast_to_others(
                code,
                slot,
                {"type": "player_reconnected", "slot": slot, "player": serialize_player(player)},
            )
        else:
            # Broadcast player_joined
            await lobby_connection_manager.broadcast_to_others(
                code,
                slot,
                {"type": "player_joined", "slot": slot, "player": serialize_player(player)},
            )

    try:
        while True:
            # Receive message
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            # Parse message
            try:
                msg_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "code": "invalid_json", "message": "Invalid JSON"})
                )
                continue

            # Handle message
            await _handle_message(websocket, code, slot, player_key, msg_data)

    except Exception as e:
        logger.exception(f"Error in lobby WebSocket handler for {code}: {e}")
    finally:
        # Disconnect
        disconnected_slot = await lobby_connection_manager.disconnect(code, websocket)
        if disconnected_slot is not None:
            await _handle_disconnect(code, player_key, disconnected_slot)


async def _handle_message(
    websocket: WebSocket,
    code: str,
    slot: int,
    player_key: str,
    data: dict[str, Any],
) -> None:
    """Handle a WebSocket message.

    Args:
        websocket: The WebSocket connection
        code: The lobby code
        slot: The player's slot
        player_key: The player's secret key
        data: The parsed message data
    """
    msg_type = data.get("type")
    manager = get_lobby_manager()

    if msg_type == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
        return

    # Clean up expired disconnected players on any non-ping action
    await _cleanup_and_broadcast(code)

    if msg_type == "ready":
        ready = data.get("ready", True)
        result = await manager.set_ready(code, player_key, ready)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        # Broadcast ready state change
        await lobby_connection_manager.broadcast(
            code,
            {"type": "player_ready", "slot": slot, "ready": ready},
        )

    elif msg_type == "update_settings":
        # Verify host
        lobby = manager.get_lobby(code)
        if lobby and lobby.host_slot != slot:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "code": "not_host",
                        "message": "Only the host can change settings",
                    }
                )
            )
            return

        settings_data = data.get("settings", {})
        settings = LobbySettings(
            is_public=settings_data.get("isPublic", True),
            speed=settings_data.get("speed", "standard"),
            player_count=settings_data.get("playerCount", 2),
            is_ranked=settings_data.get("isRanked", False),
        )

        result = await manager.update_settings(code, player_key, settings)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        # Broadcast settings update
        await lobby_connection_manager.broadcast(
            code,
            {"type": "settings_updated", "settings": serialize_settings(result.settings)},
        )

        # Also broadcast that all players are now unready
        for player_slot, player in result.players.items():
            if not player.is_ai:
                await lobby_connection_manager.broadcast(
                    code,
                    {"type": "player_ready", "slot": player_slot, "ready": player.is_ready},
                )

    elif msg_type == "kick":
        target_slot = data.get("slot")
        if target_slot is None:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "code": "missing_slot", "message": "Missing slot parameter"}
                )
            )
            return

        result = await manager.kick_player(code, player_key, target_slot)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        # Broadcast player left (kicked)
        await lobby_connection_manager.broadcast(
            code,
            {"type": "player_left", "slot": target_slot, "reason": "kicked"},
        )

    elif msg_type == "add_ai":
        ai_type = data.get("aiType", "bot:dummy")

        # Get current slots before adding to identify the new one
        lobby_before = manager.get_lobby(code)
        existing_slots = set(lobby_before.players.keys()) if lobby_before else set()

        result = await manager.add_ai(code, player_key, ai_type)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        # Find the slot that was just added
        new_slots = set(result.players.keys())
        added_slots = new_slots - existing_slots
        if not added_slots:
            logger.warning(f"add_ai succeeded but no new slot found in lobby {code}")
            return

        added_slot = added_slots.pop()
        ai_player = result.players[added_slot]

        # Broadcast player joined
        await lobby_connection_manager.broadcast(
            code,
            {"type": "player_joined", "slot": added_slot, "player": serialize_player(ai_player)},
        )

    elif msg_type == "remove_ai":
        target_slot = data.get("slot")
        if target_slot is None:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "code": "missing_slot", "message": "Missing slot parameter"}
                )
            )
            return

        result = await manager.remove_ai(code, player_key, target_slot)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        # Broadcast player left
        await lobby_connection_manager.broadcast(
            code,
            {"type": "player_left", "slot": target_slot, "reason": "removed"},
        )

    elif msg_type == "start_game":
        result = await manager.start_game(code, player_key)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        game_id, game_player_keys = result

        # Create the actual game using GameService
        lobby = manager.get_lobby(code)
        if lobby:
            await _create_game_from_lobby(code, lobby, game_id, game_player_keys)

    elif msg_type == "leave":
        # Player explicitly leaving
        await _handle_leave(code, player_key, slot, "left")

    elif msg_type == "return_to_lobby":
        result = await manager.return_to_lobby(code)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        # Broadcast updated lobby state
        await lobby_connection_manager.broadcast(
            code,
            {"type": "lobby_state", "lobby": serialize_lobby(result)},
        )

    else:
        await websocket.send_text(
            json.dumps(
                {"type": "error", "code": "unknown_message", "message": f"Unknown message type: {msg_type}"}
            )
        )


async def _create_game_from_lobby(
    code: str,
    lobby: Lobby,
    game_id: str,
    game_player_keys: dict[int, str],
) -> None:
    """Create a game from a lobby and notify all players.

    Args:
        code: The lobby code
        lobby: The lobby object
        game_id: The generated game ID (from lobby manager, unused - we generate new one)
        game_player_keys: Player keys for the game {slot: key} (from lobby manager)
    """
    from kfchess.game.board import BoardType
    from kfchess.game.state import Speed
    from kfchess.services.game_service import get_game_service

    service = get_game_service()

    # Map settings to game parameters
    speed = Speed.LIGHTNING if lobby.settings.speed == "lightning" else Speed.STANDARD
    board_type = BoardType.FOUR_PLAYER if lobby.settings.player_count == 4 else BoardType.STANDARD

    # Separate human players and AI players
    human_player_keys: dict[int, str] = {}
    ai_players_config: dict[int, str] = {}

    for slot, player in lobby.players.items():
        if player.is_ai:
            ai_type = (player.ai_type or "bot:dummy").removeprefix("bot:")
            ai_players_config[slot] = ai_type
        else:
            # Use the lobby-generated keys for human players
            if slot in game_player_keys:
                human_player_keys[slot] = game_player_keys[slot]

    # Create the game with all player keys registered
    game_id_created = service.create_lobby_game(
        speed=speed,
        board_type=board_type,
        player_keys=human_player_keys,
        ai_players_config=ai_players_config if ai_players_config else None,
    )

    # Update lobby with actual game ID
    lobby.current_game_id = game_id_created

    # Update the game-to-lobby mapping
    manager = get_lobby_manager()
    manager._game_to_lobby[game_id_created] = code

    # Send game_starting message to ALL human players
    for slot, player in lobby.players.items():
        if not player.is_ai:
            player_game_key = human_player_keys.get(slot)
            if player_game_key:
                await lobby_connection_manager.send_to_slot(
                    code,
                    slot,
                    {
                        "type": "game_starting",
                        "gameId": game_id_created,
                        "lobbyCode": code,
                        "playerKey": player_game_key,
                    },
                )

    logger.info(f"Game {game_id_created} created from lobby {code}")


async def _handle_leave(code: str, player_key: str, slot: int, reason: str) -> None:
    """Handle a player leaving the lobby.

    Args:
        code: The lobby code
        player_key: The player's secret key
        slot: The player's slot
        reason: Why the player left ("left", "disconnected")
    """
    manager = get_lobby_manager()
    lobby = manager.get_lobby(code)
    if lobby is None:
        return

    was_host = lobby.host_slot == slot

    # Remove player from lobby
    result = await manager.leave_lobby(code, player_key)

    if result is None:
        # Lobby was deleted (no human players left)
        await lobby_connection_manager.remove_lobby(code)
        logger.info(f"Lobby {code} deleted after last player left")
        return

    # Broadcast player left
    await lobby_connection_manager.broadcast(
        code,
        {"type": "player_left", "slot": slot, "reason": reason},
    )

    # If host changed, broadcast that too
    if was_host and result.host_slot != slot:
        await lobby_connection_manager.broadcast(
            code,
            {"type": "host_changed", "newHostSlot": result.host_slot},
        )


async def _handle_disconnect(code: str, player_key: str, slot: int) -> None:
    """Handle a player disconnecting from the WebSocket.

    The player is marked as disconnected with a timestamp. Cleanup happens
    lazily when the lobby is next accessed, making this stateless and
    compatible with multiple server processes.

    Args:
        code: The lobby code
        player_key: The player's secret key (unused but kept for signature consistency)
        slot: The player's slot
    """
    manager = get_lobby_manager()
    lobby = manager.get_lobby(code)
    if lobby is None:
        return

    # If the game is in progress, don't mark as disconnected (handled by game)
    if lobby.status == LobbyStatus.IN_GAME:
        logger.info(f"Player slot {slot} disconnected from lobby {code} during game, not removing")
        return

    player = lobby.players.get(slot)
    if player is None or player.is_ai:
        return

    # Mark player as disconnected (sets disconnected_at timestamp)
    await manager.set_connected(code, slot, False)

    # Broadcast disconnection status to other players
    await lobby_connection_manager.broadcast(
        code,
        {
            "type": "player_disconnected",
            "slot": slot,
        },
    )

    logger.info(f"Player slot {slot} disconnected from lobby {code}, grace period started")


async def notify_game_ended(code: str, winner: int | None, reason: str) -> None:
    """Notify a lobby that its game has ended.

    Called by the game service when a game finishes.

    Args:
        code: The lobby code
        winner: The winning player slot (1-4) or None for draw
        reason: The reason the game ended (e.g., "king_captured")
    """
    manager = get_lobby_manager()

    # Update lobby state
    lobby = await manager.end_game(code, winner)
    if lobby is None:
        return

    # Broadcast game ended to all connected clients
    await lobby_connection_manager.broadcast(
        code,
        {"type": "game_ended", "winner": winner or 0, "reason": reason},
    )

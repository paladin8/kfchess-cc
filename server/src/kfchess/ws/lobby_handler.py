"""WebSocket handler for lobby real-time communication.

Uses Redis Pub/Sub for cross-server broadcasting. Each WebSocket
connection subscribes to the lobby's pub/sub channel and runs two
concurrent tasks: a relay that forwards pub/sub events to the WS,
and a message handler that processes incoming WS messages.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from kfchess.drain import is_draining
from kfchess.game.board import BoardType
from kfchess.game.state import Speed
from kfchess.lobby.manager import LobbyError, get_lobby_manager
from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus
from kfchess.redis.client import get_redis
from kfchess.redis.lobby_store import RedisLobbyManager, _pubsub_channel
from kfchess.redis.routing import register_routing
from kfchess.services.game_registry import register_game_fire_and_forget
from kfchess.services.game_service import get_game_service
from kfchess.ws.game_loop import start_game_loop_if_needed

logger = logging.getLogger(__name__)

# Track active lobby WebSocket connections for drain mode
_active_lobby_websockets: set[WebSocket] = set()


async def close_all_lobby_websockets(code: int = 1000, reason: str = "") -> None:
    """Close all active lobby WebSocket connections.

    Used during server drain to gracefully disconnect all lobby clients.
    The finally block in handle_lobby_websocket will handle Redis cleanup
    (marking players as disconnected) when each WS is closed.
    """
    closed = 0
    for ws in list(_active_lobby_websockets):
        try:
            await ws.close(code=code, reason=reason)
            closed += 1
        except Exception:
            pass  # Client may already be disconnected
    logger.info(f"Closed {closed} lobby WebSocket connections (code={code})")


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


# ── Main WebSocket handler ────────────────────────────────────────


async def handle_lobby_websocket(
    websocket: WebSocket,
    code: str,
    player_key: str,
) -> None:
    """Handle a WebSocket connection for a lobby.

    Architecture: Each connection subscribes to a Redis pub/sub channel
    and runs two concurrent tasks — a relay (pub/sub → WS) and a message
    handler (WS → manager calls → pub/sub events).
    """
    logger.debug(f"Lobby WebSocket connection attempt: code={code}")

    manager = get_lobby_manager()

    # 1. Clean up expired disconnected players
    await _cleanup_expired(manager, code)

    # 2. Validate player key
    slot = await manager.validate_player_key(code, player_key)
    if slot is None:
        logger.debug(f"Lobby WebSocket rejected: invalid player key for lobby {code}")
        await websocket.close(code=4001, reason="Invalid player key")
        return

    # 3. Get lobby and check reconnection
    lobby = await manager.get_lobby(code)
    if lobby is None:
        logger.debug(f"Lobby WebSocket rejected: lobby {code} not found")
        await websocket.close(code=4004, reason="Lobby not found")
        return

    player = lobby.players.get(slot)
    is_reconnection = player is not None and not player.is_connected

    if is_reconnection:
        logger.info(f"Player slot {slot} reconnected to lobby {code}")
        await manager.set_connected(code, slot, True)

    # 4. Accept WebSocket
    await websocket.accept()
    _active_lobby_websockets.add(websocket)
    logger.info(f"Player slot {slot} connected to lobby {code}")

    # 5. Subscribe to pub/sub before sending state (avoid missing events)
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(_pubsub_channel(code))

    try:
        # 6. Send current lobby state
        lobby = await manager.get_lobby(code)
        if lobby is None:
            await websocket.close(code=4004, reason="Lobby not found")
            return

        await websocket.send_text(
            json.dumps({"type": "lobby_state", "lobby": serialize_lobby(lobby)})
        )

        # 7. Publish join/reconnect for other players
        player = lobby.players.get(slot)
        if player:
            if is_reconnection:
                await manager.publish_event(
                    code,
                    {"type": "player_reconnected", "slot": slot, "player": serialize_player(player)},
                )
            else:
                await manager.publish_event(
                    code,
                    {"type": "player_joined", "slot": slot, "player": serialize_player(player)},
                )

        # 8. Run concurrent tasks: pub/sub relay + WS message handler
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_relay_pubsub_to_ws(pubsub, websocket, slot))
            tg.create_task(_handle_ws_messages(websocket, manager, code, slot, player_key))

    except* WebSocketDisconnect:
        pass
    except* Exception as eg:
        for exc in eg.exceptions:
            if not isinstance(exc, WebSocketDisconnect):
                logger.exception(f"Error in lobby WebSocket handler for {code}: {exc}")
    finally:
        _active_lobby_websockets.discard(websocket)
        await pubsub.unsubscribe(_pubsub_channel(code))
        await pubsub.aclose()
        await _handle_disconnect(manager, code, slot)


# ── Pub/Sub relay ─────────────────────────────────────────────────


async def _relay_pubsub_to_ws(
    pubsub: Any,
    websocket: WebSocket,
    slot: int,
) -> None:
    """Relay events from Redis pub/sub to the WebSocket.

    Forwards all lobby events to this client. Filters game_starting
    events to include only this player's key.
    """
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        try:
            data = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            continue

        event_type = data.get("type")

        # Skip self-referencing join/reconnect events (player already has lobby_state)
        if event_type in ("player_joined", "player_reconnected"):
            if data.get("slot") == slot:
                continue

        if event_type == "game_starting":
            # Filter: send only this player's key
            player_keys = data.get("playerKeys", {})
            my_key = player_keys.get(str(slot))
            if my_key:
                await websocket.send_text(
                    json.dumps({
                        "type": "game_starting",
                        "gameId": data["gameId"],
                        "lobbyCode": data["lobbyCode"],
                        "playerKey": my_key,
                    })
                )
            # AI players or players without keys don't get game_starting
            continue

        # Forward all other events as-is
        await websocket.send_text(message["data"])


# ── WS message handler ───────────────────────────────────────────


async def _handle_ws_messages(
    websocket: WebSocket,
    manager: RedisLobbyManager,
    code: str,
    slot: int,
    player_key: str,
) -> None:
    """Handle incoming WebSocket messages from a lobby client."""
    while True:
        data = await websocket.receive_text()

        try:
            msg_data = json.loads(data)
        except json.JSONDecodeError:
            await websocket.send_text(
                json.dumps({"type": "error", "code": "invalid_json", "message": "Invalid JSON"})
            )
            continue

        await _handle_message(websocket, manager, code, slot, player_key, msg_data)


async def _handle_message(
    websocket: WebSocket,
    manager: RedisLobbyManager,
    code: str,
    slot: int,
    player_key: str,
    data: dict[str, Any],
) -> None:
    """Process a single WebSocket message."""
    msg_type = data.get("type")

    if msg_type == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
        return

    # Clean up expired disconnected players on any non-ping action
    await _cleanup_expired(manager, code)

    if msg_type == "ready":
        ready = data.get("ready", True)
        result = await manager.set_ready(code, player_key, ready)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        await manager.publish_event(
            code,
            {"type": "player_ready", "slot": slot, "ready": ready},
        )

    elif msg_type == "update_settings":
        # Verify host
        lobby = await manager.get_lobby(code)
        if lobby and lobby.host_slot != slot:
            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "code": "not_host",
                    "message": "Only the host can change settings",
                })
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

        # Publish settings update
        await manager.publish_event(
            code,
            {"type": "settings_updated", "settings": serialize_settings(result.settings)},
        )

        # Publish unready state for all human players
        for player_slot, player in result.players.items():
            if not player.is_ai:
                await manager.publish_event(
                    code,
                    {"type": "player_ready", "slot": player_slot, "ready": player.is_ready},
                )

    elif msg_type == "kick":
        target_slot = data.get("slot")
        if target_slot is None:
            await websocket.send_text(
                json.dumps({"type": "error", "code": "missing_slot", "message": "Missing slot parameter"})
            )
            return

        result = await manager.kick_player(code, player_key, target_slot)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        await manager.publish_event(
            code,
            {"type": "player_left", "slot": target_slot, "reason": "kicked"},
        )

    elif msg_type == "add_ai":
        ai_type = data.get("aiType", "bot:novice")

        # Get current slots before adding to identify the new one
        lobby_before = await manager.get_lobby(code)
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

        await manager.publish_event(
            code,
            {"type": "player_joined", "slot": added_slot, "player": serialize_player(ai_player)},
        )

    elif msg_type == "remove_ai":
        target_slot = data.get("slot")
        if target_slot is None:
            await websocket.send_text(
                json.dumps({"type": "error", "code": "missing_slot", "message": "Missing slot parameter"})
            )
            return

        result = await manager.remove_ai(code, player_key, target_slot)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        await manager.publish_event(
            code,
            {"type": "player_left", "slot": target_slot, "reason": "removed"},
        )

    elif msg_type == "change_ai_type":
        target_slot = data.get("slot")
        ai_type = data.get("aiType", "bot:novice")
        if target_slot is None:
            await websocket.send_text(
                json.dumps({"type": "error", "code": "missing_slot", "message": "Missing slot parameter"})
            )
            return

        result = await manager.change_ai_type(code, player_key, target_slot, ai_type)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        ai_player = result.players.get(target_slot)
        if ai_player:
            await manager.publish_event(
                code,
                {
                    "type": "ai_type_changed",
                    "slot": target_slot,
                    "aiType": ai_type,
                    "player": serialize_player(ai_player),
                },
            )

    elif msg_type == "start_game":
        if is_draining():
            await websocket.send_text(
                json.dumps({"type": "error", "code": "server_draining", "message": "Server is shutting down"})
            )
            return

        result = await manager.start_game(code, player_key)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        game_id, game_player_keys = result

        # Create the actual game using GameService
        lobby = await manager.get_lobby(code)
        if lobby:
            await _create_game_from_lobby(manager, code, lobby, game_id, game_player_keys)

    elif msg_type == "leave":
        await _handle_leave(manager, code, player_key, slot, "left")

    elif msg_type == "return_to_lobby":
        result = await manager.return_to_lobby(code)

        if isinstance(result, LobbyError):
            await websocket.send_text(
                json.dumps({"type": "error", "code": result.code, "message": result.message})
            )
            return

        await manager.publish_event(
            code,
            {"type": "lobby_state", "lobby": serialize_lobby(result)},
        )

    else:
        await websocket.send_text(
            json.dumps(
                {"type": "error", "code": "unknown_message", "message": f"Unknown message type: {msg_type}"}
            )
        )


# ── Game creation ─────────────────────────────────────────────────


async def _create_game_from_lobby(
    manager: RedisLobbyManager,
    code: str,
    lobby: Lobby,
    game_id: str,
    game_player_keys: dict[int, str],
) -> None:
    """Create a game from a lobby and publish game_starting via pub/sub."""
    service = get_game_service()

    # Map settings to game parameters
    speed = Speed.LIGHTNING if lobby.settings.speed == "lightning" else Speed.STANDARD
    board_type = BoardType.FOUR_PLAYER if lobby.settings.player_count == 4 else BoardType.STANDARD

    # Build player info
    human_player_keys: dict[int, str] = {}
    human_player_ids: dict[int, str] = {}
    ai_players_config: dict[int, str] = {}

    for slot, player in lobby.players.items():
        if player.is_ai:
            ai_type = (player.ai_type or "bot:novice").removeprefix("bot:")
            ai_players_config[slot] = ai_type
        else:
            if slot in game_player_keys:
                key = game_player_keys[slot]
                human_player_keys[slot] = key
                # Use player_id from lobby model (stored in Redis)
                if player.player_id:
                    human_player_ids[slot] = player.player_id
                elif player.user_id:
                    human_player_ids[slot] = f"u:{player.user_id}"
                else:
                    human_player_ids[slot] = "guest:unknown"

    # Create the game with pre-generated game_id from Redis
    game_id_created = service.create_lobby_game(
        speed=speed,
        board_type=board_type,
        player_keys=human_player_keys,
        player_ids=human_player_ids,
        ai_players_config=ai_players_config if ai_players_config else None,
        game_id=game_id,
    )

    # Register in active games and routing registries
    players_info = []
    for slot, player in lobby.players.items():
        if player.player_id:
            pid = player.player_id
        elif player.is_ai and player.ai_type:
            pid = player.ai_type
        elif player.user_id:
            pid = f"u:{player.user_id}"
        else:
            pid = f"guest:{slot}"
        players_info.append({
            "slot": slot,
            "player_id": pid,
            "is_ai": player.is_ai,
        })
    register_game_fire_and_forget(
        game_id=game_id_created,
        game_type="lobby",
        speed=lobby.settings.speed,
        player_count=lobby.settings.player_count,
        board_type=board_type.value,
        players=players_info,
        lobby_code=code,
    )
    await register_routing(game_id_created)

    # Start game loop immediately so draw timers run even if no WS connects
    await start_game_loop_if_needed(game_id_created)

    # Publish game_starting via pub/sub with ALL player keys
    # The relay task will filter to send only the relevant key to each player
    logger.info(
        f"Publishing game_starting for {len(human_player_keys)} "
        f"human players in lobby {code}"
    )
    await manager.publish_event(
        code,
        {
            "type": "game_starting",
            "gameId": game_id_created,
            "lobbyCode": code,
            "playerKeys": {str(slot): key for slot, key in human_player_keys.items()},
        },
    )

    logger.info(f"Game {game_id_created} created from lobby {code}")


# ── Leave / disconnect ────────────────────────────────────────────


async def _handle_leave(
    manager: RedisLobbyManager,
    code: str,
    player_key: str,
    slot: int,
    reason: str,
) -> None:
    """Handle a player leaving the lobby."""
    lobby = await manager.get_lobby(code)
    if lobby is None:
        return

    was_host = lobby.host_slot == slot

    result = await manager.leave_lobby(code, player_key)

    if result is None:
        # Lobby was deleted (no human players left)
        logger.info(f"Lobby {code} deleted after last player left")
        return

    await manager.publish_event(
        code,
        {"type": "player_left", "slot": slot, "reason": reason},
    )

    if was_host and result.host_slot != slot:
        await manager.publish_event(
            code,
            {"type": "host_changed", "newHostSlot": result.host_slot},
        )


async def _handle_disconnect(
    manager: RedisLobbyManager,
    code: str,
    slot: int,
) -> None:
    """Handle a player disconnecting from the WebSocket.

    Marks the player as disconnected with a timestamp. Cleanup happens
    lazily when the lobby is next accessed.
    """
    lobby = await manager.get_lobby(code)
    if lobby is None:
        return

    # If game is in progress, don't mark as disconnected (handled by game)
    if lobby.status == LobbyStatus.IN_GAME:
        logger.info(f"Player slot {slot} disconnected from lobby {code} during game, not removing")
        return

    player = lobby.players.get(slot)
    if player is None or player.is_ai:
        return

    await manager.set_connected(code, slot, False)

    await manager.publish_event(
        code,
        {"type": "player_disconnected", "slot": slot},
    )

    logger.info(f"Player slot {slot} disconnected from lobby {code}, grace period started")


async def _cleanup_expired(manager: RedisLobbyManager, code: str) -> None:
    """Clean up expired disconnected players and publish removals."""
    cleaned_slots = await manager.cleanup_disconnected_players(code)

    if cleaned_slots:
        for s in cleaned_slots:
            await manager.publish_event(
                code,
                {"type": "player_left", "slot": s, "reason": "disconnected"},
            )

        # Broadcast full state so clients have correct host
        lobby = await manager.get_lobby(code)
        if lobby:
            await manager.publish_event(
                code,
                {"type": "lobby_state", "lobby": serialize_lobby(lobby)},
            )


# ── External notification ─────────────────────────────────────────


async def notify_game_ended(code: str, winner: int | None, reason: str) -> None:
    """Notify a lobby that its game has ended.

    Called by the game service when a game finishes. Updates lobby
    state in Redis and publishes the event via pub/sub.
    """
    manager = get_lobby_manager()

    lobby = await manager.end_game(code, winner)
    if lobby is None:
        return

    await manager.publish_event(
        code,
        {"type": "game_ended", "winner": winner or 0, "reason": reason},
    )

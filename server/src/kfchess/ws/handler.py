"""WebSocket handler for real-time game communication."""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from kfchess.campaign.levels import get_level
from kfchess.db.repositories.replays import ReplayRepository
from kfchess.db.repositories.user_game_history import UserGameHistoryRepository
from kfchess.db.session import async_session_factory
from kfchess.game.collision import (
    get_interpolated_position,
    is_piece_moving,
    is_piece_on_cooldown,
)
from kfchess.game.snapshot import GameSnapshot
from kfchess.game.state import TICK_RATE_HZ, GameStatus
from kfchess.lobby.manager import get_lobby_manager
from kfchess.redis.client import get_redis
from kfchess.redis.heartbeat import is_server_alive
from kfchess.redis.routing import (
    claim_game_routing,
    delete_game_routing,
    get_game_server,
    register_game_routing,
)
from kfchess.redis.snapshot_store import delete_snapshot, load_snapshot, save_snapshot
from kfchess.services.game_registry import (
    deregister_game,
    register_game_fire_and_forget,
    register_restored_game,
)
from kfchess.services.game_service import ManagedGame, get_game_service
from kfchess.services.rating_service import RatingService
from kfchess.services.stats import record_tick
from kfchess.settings import get_settings
from kfchess.ws.game_loop import (
    cleanup_game_loop_lock,
    register_game_loop_factory,
    start_game_loop_if_needed,
)
from kfchess.ws.lobby_handler import notify_game_ended
from kfchess.ws.protocol import (
    CampaignLevelInfo,
    CountdownMessage,
    DrawOfferedMessage,
    ErrorMessage,
    GameOverMessage,
    GameStartedMessage,
    JoinedMessage,
    MoveMessage,
    MoveRejectedMessage,
    OfferDrawMessage,
    PongMessage,
    RatingChangeData,
    RatingUpdateMessage,
    ReadyMessage,
    ResignMessage,
    StateUpdateMessage,
    parse_client_message,
)

# Countdown duration in seconds before game starts
COUNTDOWN_SECONDS = 3

logger = logging.getLogger(__name__)

# Track games currently in countdown phase (moves rejected during countdown)
_games_in_countdown: set[str] = set()

# Snapshot every N ticks (once per second at 30 Hz)
SNAPSHOT_INTERVAL_TICKS = 30

# Check routing ownership every N ticks (~3 seconds at 30 Hz).
# Detects split-brain after transient heartbeat loss: if another server
# CAS-claimed this game, we stop our loop to avoid dual processing.
OWNERSHIP_CHECK_INTERVAL_TICKS = 90

# Background tasks for fire-and-forget snapshot operations
_snapshot_tasks: set[asyncio.Task] = set()


def _build_snapshot(game_id: str, managed_game: ManagedGame) -> GameSnapshot:
    """Build a GameSnapshot from a ManagedGame."""
    state = managed_game.state

    return GameSnapshot(
        game_id=game_id,
        state=state.to_snapshot_dict(),
        player_keys=dict(managed_game.player_keys),
        ai_config=dict(managed_game.ai_config),
        campaign_level_id=managed_game.campaign_level_id,
        campaign_user_id=managed_game.campaign_user_id,
        initial_board_str=managed_game.initial_board_str,
        resigned_piece_ids=list(managed_game.resigned_piece_ids),
        draw_offers=set(managed_game.draw_offers),
        force_broadcast=managed_game.force_broadcast,
        server_id=get_settings().effective_server_id,
        snapshot_tick=state.current_tick,
    )


def _save_snapshot_fire_and_forget(snapshot: GameSnapshot) -> None:
    """Schedule a snapshot save and routing key refresh as a fire-and-forget task."""
    async def _save() -> None:
        try:
            r = await get_redis()
            await save_snapshot(r, snapshot)
            await register_game_routing(r, snapshot.game_id, snapshot.server_id)
        except Exception:
            logger.exception(f"Failed to save snapshot for game {snapshot.game_id}")

    task = asyncio.create_task(_save())
    _snapshot_tasks.add(task)
    task.add_done_callback(_snapshot_tasks.discard)


async def _delete_snapshot_and_routing(game_id: str) -> None:
    """Delete Redis snapshot and routing key for a finished game."""
    try:
        r = await get_redis()
        await delete_snapshot(r, game_id)
        await delete_game_routing(r, game_id)
    except Exception:
        logger.exception(f"Failed to delete snapshot/routing for game {game_id}")


async def _check_routing_ownership(game_id: str) -> bool:
    """Check that this server still owns the routing key for a game.

    Returns True if we are still the owner (or the key is missing/check fails).
    Returns False if another server has claimed this game — the caller
    should stop the game loop to avoid split-brain dual processing.
    """
    try:
        r = await get_redis()
        my_server_id = get_settings().effective_server_id
        owner = await get_game_server(r, game_id)
        if owner is not None and owner != my_server_id:
            logger.warning(
                f"Split-brain detected: game {game_id} routing owned by "
                f"{owner}, not us ({my_server_id}). Stopping game loop."
            )
            return False
    except Exception:
        # If Redis is unreachable, keep running — don't kill game loops
        # on transient Redis failures (which is what caused this in the first place)
        logger.warning(
            f"Failed to check routing ownership for game {game_id}, "
            f"continuing game loop"
        )
    return True


def _has_state_changed(
    prev_active_move_ids: set[str],
    prev_cooldown_ids: set[str],
    curr_active_move_ids: set[str],
    curr_cooldown_ids: set[str],
    has_events: bool,
) -> bool:
    """Check if game state has meaningfully changed since last broadcast.

    This function determines whether a state update needs to be sent to clients.
    We only broadcast when:
    - There are events (captures, promotions, etc.)
    - Active moves have changed (piece started/finished moving)
    - Cooldowns have changed (piece entered/exited cooldown)

    Args:
        prev_active_move_ids: Set of piece IDs that were moving in the previous tick
        prev_cooldown_ids: Set of piece IDs that were on cooldown in the previous tick
        curr_active_move_ids: Set of piece IDs currently moving
        curr_cooldown_ids: Set of piece IDs currently on cooldown
        has_events: Whether there are any events to broadcast

    Returns:
        True if state has changed and should be broadcast
    """
    # Always send if there are events
    if has_events:
        return True

    # Check if active moves changed
    if prev_active_move_ids != curr_active_move_ids:
        return True

    # Check if cooldowns changed (piece entered/exited cooldown)
    if prev_cooldown_ids != curr_cooldown_ids:
        return True

    return False


class ConnectionManager:
    """Manages WebSocket connections for games.

    Each game can have multiple connected clients (players and spectators).
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        # game_id -> set of (websocket, player_number or None for spectators)
        self.connections: dict[str, set[tuple[WebSocket, int | None]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, game_id: str, websocket: WebSocket, player: int | None) -> None:
        """Add a WebSocket connection to a game.

        Args:
            game_id: The game ID
            websocket: The WebSocket connection
            player: Player number (1-4) or None for spectators
        """
        await websocket.accept()
        async with self._lock:
            if game_id not in self.connections:
                self.connections[game_id] = set()
            self.connections[game_id].add((websocket, player))
        logger.info(f"Client connected to game {game_id} as player {player}")

    async def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from a game.

        Args:
            game_id: The game ID
            websocket: The WebSocket connection
        """
        async with self._lock:
            if game_id in self.connections:
                # Find and remove this websocket
                to_remove = None
                for conn in self.connections[game_id]:
                    if conn[0] == websocket:
                        to_remove = conn
                        break
                if to_remove:
                    self.connections[game_id].discard(to_remove)
                    logger.info(f"Client disconnected from game {game_id}")
                # Clean up empty game connections
                if not self.connections[game_id]:
                    del self.connections[game_id]

    async def broadcast(self, game_id: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all connections for a game.

        Args:
            game_id: The game ID
            message: The message to send (will be JSON encoded)
        """
        async with self._lock:
            connections = self.connections.get(game_id, set()).copy()

        if not connections:
            return

        data = json.dumps(message)
        disconnected: list[tuple[WebSocket, int | None]] = []

        for websocket, player in connections:
            try:
                await websocket.send_text(data)
            except Exception:
                disconnected.append((websocket, player))

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                if game_id in self.connections:
                    for conn in disconnected:
                        self.connections[game_id].discard(conn)

    async def send_to_player(self, game_id: str, player: int, message: dict[str, Any]) -> None:
        """Send a message to a specific player.

        Args:
            game_id: The game ID
            player: The player number
            message: The message to send
        """
        async with self._lock:
            connections = self.connections.get(game_id, set()).copy()

        data = json.dumps(message)

        for websocket, p in connections:
            if p == player:
                try:
                    await websocket.send_text(data)
                except Exception:
                    pass  # Will be cleaned up on next broadcast

    def get_connection_count(self, game_id: str) -> int:
        """Get the number of connections for a game."""
        return len(self.connections.get(game_id, set()))

    def has_connections(self, game_id: str) -> bool:
        """Check if a game has any connections."""
        return game_id in self.connections and len(self.connections[game_id]) > 0

    async def close_all(self, code: int = 1000, reason: str = "") -> None:
        """Close all WebSocket connections across all games.

        Used during server drain to gracefully disconnect all clients.
        """
        async with self._lock:
            all_connections = {
                game_id: conns.copy()
                for game_id, conns in self.connections.items()
            }

        closed = 0
        for _game_id, connections in all_connections.items():
            for websocket, _player in connections:
                try:
                    await websocket.close(code=code, reason=reason)
                    closed += 1
                except Exception:
                    pass  # Client may already be disconnected

        async with self._lock:
            self.connections.clear()

        logger.info(f"Closed {closed} game WebSocket connections (code={code})")


# Global connection manager instance
connection_manager = ConnectionManager()


async def _send_initial_state(websocket: WebSocket, game_id: str, service: Any) -> None:
    """Send the current game state to a newly connected client."""
    state = service.get_game(game_id)
    if state is None:
        return

    config = state.config

    # Build piece data
    pieces_data = []
    for piece in state.board.pieces:
        if piece.captured:
            continue

        pos = get_interpolated_position(
            piece, state.active_moves, state.current_tick, config.ticks_per_square
        )
        pieces_data.append(
            {
                "id": piece.id,
                "type": piece.type.value,
                "player": piece.player,
                "row": pos[0],
                "col": pos[1],
                "captured": piece.captured,
                "moving": is_piece_moving(piece.id, state.active_moves),
                "on_cooldown": is_piece_on_cooldown(piece.id, state.cooldowns, state.current_tick),
                "moved": piece.moved,
            }
        )

    # Build active moves data
    active_moves_data = []
    for move in state.active_moves:
        total_ticks = (len(move.path) - 1) * config.ticks_per_square
        elapsed = max(0, state.current_tick - move.start_tick)
        progress = min(1.0, elapsed / total_ticks) if total_ticks > 0 else 1.0
        active_moves_data.append(
            {
                "piece_id": move.piece_id,
                "path": move.path,
                "start_tick": move.start_tick,
                "progress": progress,
            }
        )

    # Build cooldown data
    cooldowns_data = []
    for cd in state.cooldowns:
        remaining = max(0, (cd.start_tick + cd.duration) - state.current_tick)
        cooldowns_data.append(
            {
                "piece_id": cd.piece_id,
                "remaining_ticks": remaining,
            }
        )

    # Send initial state
    await websocket.send_text(
        StateUpdateMessage(
            tick=state.current_tick,
            pieces=pieces_data,
            active_moves=active_moves_data,
            cooldowns=cooldowns_data,
            events=[],
        ).model_dump_json()
    )

    # Send current draw offers if any
    managed_game = service.get_managed_game(game_id)
    if managed_game is not None and managed_game.draw_offers:
        await websocket.send_text(
            DrawOfferedMessage(
                player=0,  # Not a specific player, just a sync
                draw_offers=sorted(managed_game.draw_offers),
            ).model_dump_json()
        )


async def handle_websocket(
    websocket: WebSocket,
    game_id: str,
    player_key: str | None,
) -> None:
    """Handle a WebSocket connection for a game.

    Args:
        websocket: The WebSocket connection
        game_id: The game ID
        player_key: The player's secret key (None for spectators)
    """
    logger.info(f"WebSocket connection attempt: game_id={game_id}, has_player_key={player_key is not None}")

    service = get_game_service()

    # Validate game exists (locally, via crash recovery, or via redirect)
    state = service.get_game(game_id)
    if state is None:
        # Must accept before close so the client receives the custom close code.
        # Without accept(), ASGI servers send HTTP 403 and the client sees code 1006.
        await websocket.accept()

        # Not on this server — check Redis for routing to another server,
        # and attempt crash recovery if the owning server is dead.
        try:
            r = await get_redis()
            owner = await get_game_server(r, game_id)
            my_server_id = get_settings().effective_server_id

            if owner is not None and owner != my_server_id:
                # Check if owning server is alive
                if await is_server_alive(r, owner):
                    # Server is alive — redirect client there
                    logger.info(
                        f"WebSocket redirect: game {game_id} is on {owner}, "
                        f"sending 4302"
                    )
                    await websocket.close(code=4302, reason=owner)
                    return

                # Owner is dead — attempt CAS crash recovery
                claimed = await claim_game_routing(
                    r, game_id, owner, my_server_id
                )
                if claimed:
                    snapshot = await load_snapshot(r, game_id)
                    if snapshot is not None and service.restore_game(snapshot):
                        logger.info(
                            f"Crash recovery: claimed game {game_id} "
                            f"from dead server {owner}"
                        )
                        managed = service.get_managed_game(game_id)
                        if managed is not None:
                            register_restored_game(
                                game_id=game_id,
                                state=managed.state,
                                ai_player_nums=set(managed.ai_players.keys()),
                                campaign_level_id=snapshot.campaign_level_id,
                            )
                        # Game restored — fall through to normal join flow
                        state = service.get_game(game_id)
                    else:
                        logger.warning(
                            f"Crash recovery failed for game {game_id}: "
                            f"snapshot missing or restore failed"
                        )
                        # CAS claimed the routing key but restore failed —
                        # clean up both Redis routing and the DB active-game
                        # row so the game doesn't linger in the live list.
                        await delete_game_routing(r, game_id)
                        await deregister_game(game_id)
                        await websocket.close(
                            code=4004, reason="Game not found"
                        )
                        return
                else:
                    # Another server won the CAS race — redirect to them
                    new_owner = await get_game_server(r, game_id)
                    if new_owner and new_owner != my_server_id:
                        logger.info(
                            f"CAS race lost for game {game_id}, "
                            f"redirecting to {new_owner}"
                        )
                        await websocket.close(code=4302, reason=new_owner)
                    else:
                        await websocket.close(
                            code=4004, reason="Game not found"
                        )
                    return
        except Exception:
            logger.exception(f"Failed to check routing for game {game_id}")

        if state is None:
            logger.info(f"WebSocket rejected: game {game_id} not found")
            await websocket.close(code=4004, reason="Game not found")
            return

    # Validate player key if provided
    player: int | None = None
    if player_key:
        player = service.validate_player_key(game_id, player_key)
        if player is None:
            await websocket.accept()
            logger.warning(f"WebSocket rejected: invalid player key for game {game_id}")
            await websocket.close(code=4001, reason="Invalid player key")
            return

    logger.info(f"WebSocket accepting connection for game {game_id}, player {player}")

    # Connect
    await connection_manager.connect(game_id, websocket, player)

    # Build campaign level info if this is a campaign game
    campaign_level_info: CampaignLevelInfo | None = None
    managed_game = service.games.get(game_id)
    if managed_game and managed_game.campaign_level_id is not None:
        level = get_level(managed_game.campaign_level_id)
        if level:
            campaign_level_info = CampaignLevelInfo(
                level_id=level.level_id,
                title=level.title,
                description=level.description,
                has_next_level=get_level(level.level_id + 1) is not None,
            )

    # Send joined message with player number (0 for spectators) and tick rate
    await websocket.send_text(
        JoinedMessage(
            player_number=player if player is not None else 0,
            tick_rate_hz=TICK_RATE_HZ,
            campaign_level=campaign_level_info,
        ).model_dump_json()
    )

    # Send initial state to the connecting client
    await _send_initial_state(websocket, game_id, service)

    # Start game loop if game is playing
    await start_game_loop_if_needed(game_id)

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
                await websocket.send_text(ErrorMessage(message="Invalid JSON").model_dump_json())
                continue

            # Handle message
            message = parse_client_message(msg_data)
            if message is None:
                await websocket.send_text(
                    ErrorMessage(message="Unknown message type").model_dump_json()
                )
                continue

            await _handle_message(websocket, game_id, player, message, service)

    except Exception as e:
        logger.exception(f"Error in WebSocket handler for game {game_id}: {e}")
    finally:
        await connection_manager.disconnect(game_id, websocket)


async def _handle_message(
    websocket: WebSocket,
    game_id: str,
    player: int | None,
    message: MoveMessage | ReadyMessage | Any,
    service: Any,
) -> None:
    """Handle a parsed client message.

    Args:
        websocket: The WebSocket connection
        game_id: The game ID
        player: The player number (None for spectators)
        message: The parsed message
        service: The game service
    """
    if isinstance(message, MoveMessage):
        await _handle_move(websocket, game_id, player, message, service)
    elif isinstance(message, ReadyMessage):
        await _handle_ready(websocket, game_id, player, service)
    elif isinstance(message, ResignMessage):
        await _handle_resign(websocket, game_id, player, service)
    elif isinstance(message, OfferDrawMessage):
        await _handle_offer_draw(websocket, game_id, player, service)
    else:
        # Ping - respond with pong
        await websocket.send_text(PongMessage().model_dump_json())


async def _handle_move(
    websocket: WebSocket,
    game_id: str,
    player: int | None,
    message: MoveMessage,
    service: Any,
) -> None:
    """Handle a move message."""
    if player is None:
        await websocket.send_text(
            MoveRejectedMessage(
                piece_id=message.piece_id,
                reason="spectators_cannot_move",
            ).model_dump_json()
        )
        return

    # Reject moves during countdown period
    if game_id in _games_in_countdown:
        await websocket.send_text(
            MoveRejectedMessage(
                piece_id=message.piece_id,
                reason="countdown_active",
            ).model_dump_json()
        )
        return

    # Get player key from service
    managed_game = service.get_managed_game(game_id)
    if managed_game is None:
        return

    player_key = managed_game.player_keys.get(player)
    if player_key is None:
        return

    # Make the move
    result = service.make_move(
        game_id=game_id,
        player_key=player_key,
        piece_id=message.piece_id,
        to_row=message.to_row,
        to_col=message.to_col,
    )

    if not result.success:
        await websocket.send_text(
            MoveRejectedMessage(
                piece_id=message.piece_id,
                reason=result.error or "invalid_move",
            ).model_dump_json()
        )


async def _handle_ready(
    websocket: WebSocket,
    game_id: str,
    player: int | None,
    service: Any,
) -> None:
    """Handle a ready message."""
    if player is None:
        await websocket.send_text(
            ErrorMessage(message="Spectators cannot mark ready").model_dump_json()
        )
        return

    # Get player key from service
    managed_game = service.get_managed_game(game_id)
    if managed_game is None:
        return

    player_key = managed_game.player_keys.get(player)
    if player_key is None:
        return

    # Mark ready
    success, game_started = service.mark_ready(game_id, player_key)

    if game_started:
        # Broadcast game started
        await connection_manager.broadcast(
            game_id,
            GameStartedMessage(tick=0).model_dump(),
        )

        # Register in active games now that the game is actually playing
        managed_game = service.get_managed_game(game_id)
        if managed_game is not None:
            players_info = []
            for pnum, pid in managed_game.state.players.items():
                is_ai = pnum in managed_game.ai_players
                players_info.append({"slot": pnum, "player_id": pid, "is_ai": is_ai})
            register_game_fire_and_forget(
                game_id=game_id,
                game_type="quickplay",
                speed=managed_game.state.speed.value,
                player_count=len(managed_game.state.players),
                board_type=managed_game.state.board.board_type.value,
                players=players_info,
            )

        # Start the game loop (uses lock to prevent race conditions)
        await start_game_loop_if_needed(game_id)


async def _handle_resign(
    websocket: WebSocket,
    game_id: str,
    player: int | None,
    service: Any,
) -> None:
    """Handle a resign message."""
    if player is None:
        await websocket.send_text(
            ErrorMessage(message="Spectators cannot resign").model_dump_json()
        )
        return

    success = service.resign(game_id, player)
    if not success:
        await websocket.send_text(
            ErrorMessage(message="Cannot resign").model_dump_json()
        )


async def _handle_offer_draw(
    websocket: WebSocket,
    game_id: str,
    player: int | None,
    service: Any,
) -> None:
    """Handle a draw offer message."""
    if player is None:
        await websocket.send_text(
            ErrorMessage(message="Spectators cannot offer draw").model_dump_json()
        )
        return

    success, error = service.offer_draw(game_id, player)
    if not success:
        await websocket.send_text(
            ErrorMessage(message=error or "Cannot offer draw").model_dump_json()
        )
        return

    # Broadcast the draw offer to all players
    managed_game = service.get_managed_game(game_id)
    if managed_game is not None:
        await connection_manager.broadcast(
            game_id,
            DrawOfferedMessage(
                player=player,
                draw_offers=sorted(managed_game.draw_offers),
            ).model_dump(),
        )


async def _save_replay(game_id: str, service: Any) -> None:
    """Save the game replay to the database.

    Saves to both game_replays and user_game_history tables.
    The user_game_history table provides O(1) match history lookups.

    Args:
        game_id: The game ID
        service: The game service
    """
    try:
        replay = service.get_replay(game_id)
        if replay is None:
            logger.warning(f"Could not get replay for game {game_id}")
            return

        # Get is_ranked from lobby if available
        try:
            manager = get_lobby_manager()
            lobby_code = await manager.find_lobby_by_game(game_id)
            if lobby_code is not None:
                lobby = await manager.get_lobby(lobby_code)
                if lobby is not None:
                    replay.is_ranked = lobby.settings.is_ranked
                else:
                    logger.warning(
                        f"Lobby {lobby_code} not found when saving replay for game {game_id}, "
                        "is_ranked will default to False"
                    )
            # Note: lobby_code being None is expected for games not started from lobbies
        except Exception as e:
            logger.warning(f"Error getting lobby info for game {game_id}: {e}")

        # Save to database
        async with async_session_factory() as session:
            try:
                # Save the replay
                repository = ReplayRepository(session)
                await repository.save(game_id, replay)

                # Save to user_game_history for each human player
                history_repo = UserGameHistoryRepository(session)
                game_time = replay.created_at or datetime.now(UTC)

                for player_num, player_id in replay.players.items():
                    # Only save history for registered users (u:123 format)
                    if not player_id.startswith("u:"):
                        continue

                    try:
                        user_id = int(player_id[2:])
                    except ValueError:
                        continue

                    # Build opponents list (all other players)
                    opponents = [
                        pid for pnum, pid in replay.players.items()
                        if pnum != player_num
                    ]

                    game_info = {
                        "speed": replay.speed.value,
                        "boardType": replay.board_type.value,
                        "player": player_num,
                        "winner": replay.winner,
                        "winReason": replay.win_reason,
                        "gameId": game_id,
                        "ticks": replay.total_ticks,
                        "opponents": opponents,
                        "isRanked": replay.is_ranked,
                        "campaignLevelId": replay.campaign_level_id,
                    }

                    await history_repo.add(user_id, game_time, game_info)

                await session.commit()
                logger.info(f"Saved replay for game {game_id} ({len(replay.moves)} moves)")
            except Exception as e:
                await session.rollback()
                logger.exception(f"Failed to save replay for game {game_id}: {e}")
    except Exception as e:
        logger.exception(f"Error saving replay for game {game_id}: {e}")


async def _handle_campaign_completion(game_id: str, winner: int | None) -> None:
    """Update campaign progress when player 1 wins a campaign game.

    Args:
        game_id: The game ID
        winner: The winning player number (1 = human player won)
    """
    try:
        service = get_game_service()
        managed_game = service.get_managed_game(game_id)

        if managed_game is None:
            return

        # Only process campaign games where player 1 won
        if managed_game.campaign_level_id is None:
            return

        if winner != 1:
            logger.debug(
                f"Campaign game {game_id} level {managed_game.campaign_level_id} "
                f"ended with winner={winner}, no progress update"
            )
            return

        if managed_game.campaign_user_id is None:
            logger.warning(
                f"Campaign game {game_id} has level_id but no user_id"
            )
            return

        # Import here to avoid circular import
        from kfchess.campaign.service import CampaignService
        from kfchess.db.repositories.campaign import CampaignProgressRepository

        async with async_session_factory() as session:
            repo = CampaignProgressRepository(session)
            campaign_service = CampaignService(repo)

            new_belt = await campaign_service.complete_level(
                managed_game.campaign_user_id,
                managed_game.campaign_level_id,
            )
            await session.commit()

            if new_belt:
                logger.info(
                    f"User {managed_game.campaign_user_id} completed belt after "
                    f"level {managed_game.campaign_level_id}"
                )
            else:
                logger.info(
                    f"User {managed_game.campaign_user_id} completed campaign "
                    f"level {managed_game.campaign_level_id}"
                )

    except Exception as e:
        logger.exception(f"Error handling campaign completion for game {game_id}: {e}")


async def _notify_lobby_game_ended(game_id: str, winner: int | None, reason: str) -> None:
    """Notify the lobby that a game has ended.

    This is called when a game finishes to allow players to return to the lobby.

    Args:
        game_id: The game ID
        winner: The winning player slot (1-4) or None for draw
        reason: The reason the game ended
    """
    try:
        manager = get_lobby_manager()
        lobby_code = await manager.find_lobby_by_game(game_id)

        if lobby_code is None:
            # Game wasn't started from a lobby (e.g., quick play)
            logger.debug(f"Game {game_id} has no associated lobby")
            return

        await notify_game_ended(lobby_code, winner, reason)
        logger.info(f"Notified lobby {lobby_code} that game {game_id} ended")

    except Exception as e:
        logger.exception(f"Error notifying lobby of game end for {game_id}: {e}")


async def _update_ratings(
    game_id: str,
    state: Any,
) -> dict[int, Any] | None:
    """Update ratings after a ranked game completes.

    Args:
        game_id: The game ID
        state: The finished game state

    Returns:
        Dict of {player_num: RatingChange} or None if not eligible
    """
    try:
        manager = get_lobby_manager()
        lobby_code = await manager.find_lobby_by_game(game_id)

        if lobby_code is None:
            logger.debug(f"Game {game_id}: No lobby found for rating update")
            return None

        lobby = await manager.get_lobby(lobby_code)
        if lobby is None:
            logger.debug(f"Game {game_id}: Lobby {lobby_code} not found for rating update")
            return None

        # Build player_num -> user_id mapping
        player_user_ids: dict[int, int] = {}
        for player in lobby.players.values():
            if player.user_id is not None:
                player_user_ids[player.slot] = player.user_id

        if not player_user_ids:
            logger.debug(f"Game {game_id}: No user IDs found for rating update")
            return None

        async with async_session_factory() as session:
            try:
                rating_service = RatingService(session)
                rating_changes = await rating_service.update_ratings_for_game(
                    game_id, state, lobby, player_user_ids
                )
                await session.commit()
                return rating_changes
            except Exception as e:
                await session.rollback()
                logger.exception(f"Failed to update ratings for game {game_id}: {e}")
                return None

    except Exception as e:
        logger.exception(f"Error updating ratings for game {game_id}: {e}")
        return None


async def _broadcast_rating_update(
    game_id: str,
    rating_changes: dict[int, Any],
) -> None:
    """Send rating update message to all connected players.

    Args:
        game_id: The game ID
        rating_changes: Dict of {player_num: RatingChange}
    """
    try:
        ratings_data: dict[str, RatingChangeData] = {}
        for player_num, change in rating_changes.items():
            ratings_data[str(player_num)] = RatingChangeData(
                old_rating=change.old_rating,
                new_rating=change.new_rating,
                old_belt=change.old_belt,
                new_belt=change.new_belt,
                belt_changed=change.belt_changed,
            )

        message = RatingUpdateMessage(ratings=ratings_data)
        await connection_manager.broadcast(game_id, message.model_dump())
        logger.info(f"Broadcast rating update for game {game_id}")

    except Exception as e:
        logger.exception(f"Error broadcasting rating update for {game_id}: {e}")


async def _run_game_loop(game_id: str) -> None:
    """Run the game tick loop.

    This runs at TICK_RATE_HZ ticks/second and broadcasts
    state updates to all connected clients only when state changes.

    The optimization reduces bandwidth and CPU by only sending updates when:
    - There are events (captures, promotions, etc.)
    - Active moves have changed (piece started/finished moving)
    - Cooldowns have changed (piece entered/exited cooldown)
    """
    service = get_game_service()
    # Derive tick timing from global tick rate
    tick_interval = 1.0 / TICK_RATE_HZ
    tick_interval_ms = 1000.0 / TICK_RATE_HZ

    # Track previous state for change detection
    prev_active_move_ids: set[str] = set()
    prev_cooldown_ids: set[str] = set()
    is_first_tick = True

    logger.info(f"Starting game loop for game {game_id}")

    try:
        # === Countdown phase (before any ticks) ===
        # Only run countdown if game hasn't started yet (tick 0).
        # If the loop was restarted (e.g., after all players disconnected
        # and one reconnected), skip countdown since the game is already
        # in progress.
        managed_game = service.get_managed_game(game_id)
        if managed_game is not None and managed_game.state.current_tick == 0:
            _games_in_countdown.add(game_id)
            logger.info(f"Game {game_id} starting {COUNTDOWN_SECONDS}s countdown")

            for seconds_remaining in range(COUNTDOWN_SECONDS, 0, -1):
                # Check if game still exists
                managed_game = service.get_managed_game(game_id)
                if managed_game is None:
                    logger.info(f"Game {game_id} not found during countdown, stopping")
                    return

                # Broadcast countdown
                await connection_manager.broadcast(
                    game_id,
                    CountdownMessage(seconds=seconds_remaining).model_dump(),
                )

                # Wait 1 second
                await asyncio.sleep(1.0)

            # Countdown complete - remove from countdown set and broadcast game_started
            _games_in_countdown.discard(game_id)
            await connection_manager.broadcast(
                game_id,
                GameStartedMessage(tick=0).model_dump(),
            )
            logger.info(f"Game {game_id} countdown complete, game started")
        else:
            logger.info(f"Game {game_id} loop restarted, skipping countdown (tick={managed_game.state.current_tick if managed_game else 'N/A'})")

        # === Main game loop ===
        while True:
            tick_start_ns = time.monotonic_ns()

            # Get game state
            managed_game = service.get_managed_game(game_id)
            if managed_game is None:
                logger.info(f"Game {game_id} not found, stopping loop")
                break

            state = managed_game.state

            # Check if game ended externally (e.g., resignation)
            if state.status == GameStatus.FINISHED:
                reason = state.win_reason.value if state.win_reason else "king_captured"

                # Send final state update with all pieces (including captured)
                # so clients see the king marked as captured
                config = state.config
                final_pieces = []
                for piece in state.board.pieces:
                    pos = get_interpolated_position(
                        piece, state.active_moves, state.current_tick, config.ticks_per_square
                    )
                    final_pieces.append(
                        {
                            "id": piece.id,
                            "type": piece.type.value,
                            "player": piece.player,
                            "row": pos[0],
                            "col": pos[1],
                            "captured": piece.captured,
                            "moving": is_piece_moving(piece.id, state.active_moves),
                            "on_cooldown": is_piece_on_cooldown(
                                piece.id, state.cooldowns, state.current_tick
                            ),
                            "moved": piece.moved,
                        }
                    )
                await connection_manager.broadcast(
                    game_id,
                    StateUpdateMessage(
                        tick=state.current_tick,
                        pieces=final_pieces,
                        active_moves=[],
                        cooldowns=[],
                        events=[],
                    ).model_dump(),
                )

                await connection_manager.broadcast(
                    game_id,
                    GameOverMessage(
                        winner=state.winner or 0,
                        reason=reason,
                    ).model_dump(),
                )
                logger.info(f"Game {game_id} finished (external), winner: {state.winner}")

                await _save_replay(game_id, service)
                await _delete_snapshot_and_routing(game_id)

                # Update campaign progress if this is a campaign game
                await _handle_campaign_completion(game_id, state.winner)

                rating_changes = await _update_ratings(game_id, state)
                if rating_changes:
                    await _broadcast_rating_update(game_id, rating_changes)

                await _notify_lobby_game_ended(game_id, state.winner, reason)
                break

            if state.status != GameStatus.PLAYING:
                logger.info(f"Game {game_id} is {state.status.value}, stopping loop")
                break

            # Advance the game state
            state, events, game_finished, ai_ns, engine_ns = service.tick(game_id)
            if state is None:
                break

            config = state.config

            # Get current state IDs for change detection
            curr_active_move_ids = {m.piece_id for m in state.active_moves}
            curr_cooldown_ids = {c.piece_id for c in state.cooldowns}

            # Check if state has changed (always send on first tick)
            # Also force broadcast if flagged (e.g., 4-player resignation)
            force = managed_game.force_broadcast
            resigned_ids: set[str] = set()
            if force:
                managed_game.force_broadcast = False
                resigned_ids = set(managed_game.resigned_piece_ids)
                managed_game.resigned_piece_ids.clear()
            state_changed = is_first_tick or force or _has_state_changed(
                prev_active_move_ids,
                prev_cooldown_ids,
                curr_active_move_ids,
                curr_cooldown_ids,
                bool(events),
            )

            if state_changed:
                # Build state update message
                pieces_data = []
                for piece in state.board.pieces:
                    if piece.captured:
                        # Include captured pieces only if just captured via
                        # collision (event) or resignation
                        was_just_captured = piece.id in resigned_ids or any(
                            e.type.value == "capture" and e.data.get("captured_piece_id") == piece.id
                            for e in events
                        )
                        if not was_just_captured:
                            continue

                    pos = get_interpolated_position(
                        piece, state.active_moves, state.current_tick, config.ticks_per_square
                    )
                    pieces_data.append(
                        {
                            "id": piece.id,
                            "type": piece.type.value,
                            "player": piece.player,
                            "row": pos[0],
                            "col": pos[1],
                            "captured": piece.captured,
                            "moving": is_piece_moving(piece.id, state.active_moves),
                            "on_cooldown": is_piece_on_cooldown(
                                piece.id, state.cooldowns, state.current_tick
                            ),
                            "moved": piece.moved,
                        }
                    )

                active_moves_data = []
                for move in state.active_moves:
                    total_ticks = (len(move.path) - 1) * config.ticks_per_square
                    elapsed = max(0, state.current_tick - move.start_tick)
                    progress = min(1.0, elapsed / total_ticks) if total_ticks > 0 else 1.0
                    active_moves_data.append(
                        {
                            "piece_id": move.piece_id,
                            "path": move.path,
                            "start_tick": move.start_tick,
                            "progress": progress,
                        }
                    )

                cooldowns_data = []
                for cd in state.cooldowns:
                    remaining = max(0, (cd.start_tick + cd.duration) - state.current_tick)
                    cooldowns_data.append(
                        {
                            "piece_id": cd.piece_id,
                            "remaining_ticks": remaining,
                        }
                    )

                events_data = []
                for event in events:
                    events_data.append(
                        {
                            "type": event.type.value,
                            "tick": event.tick,
                            **event.data,
                        }
                    )

                # Calculate time_since_tick right before sending (captures actual elapsed time)
                elapsed_in_tick = (time.monotonic_ns() - tick_start_ns) / 1_000_000  # Convert to ms
                time_since_tick = min(elapsed_in_tick, tick_interval_ms)

                # Broadcast state update
                await connection_manager.broadcast(
                    game_id,
                    StateUpdateMessage(
                        tick=state.current_tick,
                        pieces=pieces_data,
                        active_moves=active_moves_data,
                        cooldowns=cooldowns_data,
                        events=events_data,
                        time_since_tick=time_since_tick,
                    ).model_dump(),
                )

            # Update previous state for next iteration
            prev_active_move_ids = curr_active_move_ids
            prev_cooldown_ids = curr_cooldown_ids
            is_first_tick = False

            # Periodic snapshot to Redis (fire-and-forget)
            if state.current_tick % SNAPSHOT_INTERVAL_TICKS == 0:
                snapshot = _build_snapshot(game_id, managed_game)
                _save_snapshot_fire_and_forget(snapshot)

            # Periodic routing ownership check (split-brain protection)
            if state.current_tick % OWNERSHIP_CHECK_INTERVAL_TICKS == 0:
                if not await _check_routing_ownership(game_id):
                    # Another server claimed this game — remove from local
                    # state and stop to avoid dual processing.
                    service.games.pop(game_id, None)
                    break

            # Check for game over after tick
            if state.status == GameStatus.FINISHED:
                reason = state.win_reason.value if state.win_reason else "king_captured"
                await connection_manager.broadcast(
                    game_id,
                    GameOverMessage(
                        winner=state.winner or 0,
                        reason=reason,
                    ).model_dump(),
                )
                logger.info(f"Game {game_id} finished, winner: {state.winner}")

                # Save replay to database
                await _save_replay(game_id, service)
                await _delete_snapshot_and_routing(game_id)

                # Update campaign progress if this is a campaign game
                await _handle_campaign_completion(game_id, state.winner)

                # Update ratings for ranked games
                rating_changes = await _update_ratings(game_id, state)
                if rating_changes:
                    await _broadcast_rating_update(game_id, rating_changes)

                # Notify lobby that game ended (for return-to-lobby flow)
                await _notify_lobby_game_ended(game_id, state.winner, reason)

                break

            # Record stats and sleep for remainder of tick interval
            compute_ns = time.monotonic_ns() - tick_start_ns
            record_tick(game_id, compute_ns, ai_ns, engine_ns)
            elapsed = compute_ns / 1_000_000_000
            if elapsed < tick_interval:
                await asyncio.sleep(tick_interval - elapsed)

    except asyncio.CancelledError:
        logger.info(f"Game loop for {game_id} was cancelled")
        raise
    finally:
        # Clean up
        _games_in_countdown.discard(game_id)
        cleanup_game_loop_lock(game_id)
        # Only deregister if the game is actually done. The loop may have
        # stopped due to no connections — the game is still alive in memory
        # and the loop will restart when someone reconnects.
        managed = service.get_managed_game(game_id)
        if managed is None or managed.state.status == GameStatus.FINISHED:
            await deregister_game(game_id)
        logger.info(f"Game loop ended for game {game_id}")


# Register _run_game_loop so the shared game_loop module can create tasks
register_game_loop_factory(_run_game_loop)

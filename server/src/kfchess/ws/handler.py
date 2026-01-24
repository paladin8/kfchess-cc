"""WebSocket handler for real-time game communication."""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from kfchess.ws.protocol import (
    ErrorMessage,
    GameOverMessage,
    GameStartedMessage,
    MoveMessage,
    MoveRejectedMessage,
    PongMessage,
    ReadyMessage,
    StateUpdateMessage,
    parse_client_message,
)

logger = logging.getLogger(__name__)

# Lock for game loop startup to prevent race conditions
_game_loop_locks: dict[str, asyncio.Lock] = {}


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


# Global connection manager instance
connection_manager = ConnectionManager()


def _get_game_loop_lock(game_id: str) -> asyncio.Lock:
    """Get or create a lock for game loop startup."""
    if game_id not in _game_loop_locks:
        _game_loop_locks[game_id] = asyncio.Lock()
    return _game_loop_locks[game_id]


async def _start_game_loop_if_needed(game_id: str) -> None:
    """Start the game loop if not already running.

    Uses a lock to prevent race conditions when multiple connections
    try to start the loop simultaneously.
    """
    from kfchess.services.game_service import get_game_service

    service = get_game_service()
    lock = _get_game_loop_lock(game_id)

    async with lock:
        managed_game = service.get_managed_game(game_id)
        if managed_game is None:
            return

        if not managed_game.state.is_playing:
            return

        if managed_game.loop_task is None or managed_game.loop_task.done():
            managed_game.loop_task = asyncio.create_task(_run_game_loop(game_id))


async def _send_initial_state(websocket: WebSocket, game_id: str, service: Any) -> None:
    """Send the current game state to a newly connected client."""
    from kfchess.game.collision import (
        get_interpolated_position,
        is_piece_moving,
        is_piece_on_cooldown,
    )

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

    # Import here to avoid circular imports
    from kfchess.services.game_service import get_game_service

    service = get_game_service()

    # Validate game exists
    state = service.get_game(game_id)
    if state is None:
        logger.warning(f"WebSocket rejected: game {game_id} not found")
        await websocket.close(code=4004, reason="Game not found")
        return

    # Validate player key if provided
    player: int | None = None
    if player_key:
        player = service.validate_player_key(game_id, player_key)
        if player is None:
            logger.warning(f"WebSocket rejected: invalid player key for game {game_id}")
            await websocket.close(code=4001, reason="Invalid player key")
            return

    logger.info(f"WebSocket accepting connection for game {game_id}, player {player}")

    # Connect
    await connection_manager.connect(game_id, websocket, player)

    # Send initial state to the connecting client
    await _send_initial_state(websocket, game_id, service)

    # Start game loop if game is playing
    await _start_game_loop_if_needed(game_id)

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

        # Start the game loop (uses lock to prevent race conditions)
        await _start_game_loop_if_needed(game_id)


async def _save_replay(game_id: str, service: Any) -> None:
    """Save the game replay to the database.

    Args:
        game_id: The game ID
        service: The game service
    """
    try:
        replay = service.get_replay(game_id)
        if replay is None:
            logger.warning(f"Could not get replay for game {game_id}")
            return

        # Save to database
        from kfchess.db.repositories.replays import ReplayRepository
        from kfchess.db.session import async_session_factory

        async with async_session_factory() as session:
            try:
                repository = ReplayRepository(session)
                await repository.save(game_id, replay)
                await session.commit()
                logger.info(f"Saved replay for game {game_id} ({len(replay.moves)} moves)")
            except Exception as e:
                await session.rollback()
                logger.exception(f"Failed to save replay for game {game_id}: {e}")
    except Exception as e:
        logger.exception(f"Error saving replay for game {game_id}: {e}")


async def _notify_lobby_game_ended(game_id: str, winner: int | None, reason: str) -> None:
    """Notify the lobby that a game has ended.

    This is called when a game finishes to allow players to return to the lobby.

    Args:
        game_id: The game ID
        winner: The winning player slot (1-4) or None for draw
        reason: The reason the game ended
    """
    try:
        from kfchess.lobby.manager import get_lobby_manager
        from kfchess.ws.lobby_handler import notify_game_ended

        manager = get_lobby_manager()
        lobby_code = manager.find_lobby_by_game(game_id)

        if lobby_code is None:
            # Game wasn't started from a lobby (e.g., quick play)
            logger.debug(f"Game {game_id} has no associated lobby")
            return

        await notify_game_ended(lobby_code, winner, reason)
        logger.info(f"Notified lobby {lobby_code} that game {game_id} ended")

    except Exception as e:
        logger.exception(f"Error notifying lobby of game end for {game_id}: {e}")


async def _run_game_loop(game_id: str) -> None:
    """Run the game tick loop.

    This runs at 10 ticks/second (100ms per tick) and broadcasts
    state updates to all connected clients.
    """
    from kfchess.game.collision import (
        get_interpolated_position,
        is_piece_moving,
        is_piece_on_cooldown,
    )
    from kfchess.game.state import GameStatus
    from kfchess.services.game_service import get_game_service

    service = get_game_service()
    tick_interval = 0.1  # 100ms

    logger.info(f"Starting game loop for game {game_id}")

    try:
        while True:
            start_time = time.monotonic()

            # Get game state
            managed_game = service.get_managed_game(game_id)
            if managed_game is None:
                logger.info(f"Game {game_id} not found, stopping loop")
                break

            state = managed_game.state

            # Check if game is still playing (before tick)
            if state.status != GameStatus.PLAYING:
                logger.info(f"Game {game_id} is {state.status.value}, stopping loop")
                break

            # Check if anyone is connected
            if not connection_manager.has_connections(game_id):
                logger.info(f"No connections for game {game_id}, stopping loop")
                break

            # Advance the game state
            state, events, game_finished = service.tick(game_id)
            if state is None:
                break

            config = state.config

            # Build state update message
            pieces_data = []
            for piece in state.board.pieces:
                if piece.captured:
                    # Only include captured pieces that were just captured
                    was_just_captured = any(
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

            # Broadcast state update
            await connection_manager.broadcast(
                game_id,
                StateUpdateMessage(
                    tick=state.current_tick,
                    pieces=pieces_data,
                    active_moves=active_moves_data,
                    cooldowns=cooldowns_data,
                    events=events_data,
                ).model_dump(),
            )

            # Check for game over after tick
            if state.status == GameStatus.FINISHED:
                reason = "king_captured"
                if state.winner == 0:
                    reason = "draw_timeout"
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

                # Notify lobby that game ended (for return-to-lobby flow)
                await _notify_lobby_game_ended(game_id, state.winner, reason)

                break

            # Sleep for remainder of tick interval
            elapsed = time.monotonic() - start_time
            if elapsed < tick_interval:
                await asyncio.sleep(tick_interval - elapsed)

    except asyncio.CancelledError:
        logger.info(f"Game loop for {game_id} was cancelled")
        raise
    finally:
        # Clean up the game loop lock
        if game_id in _game_loop_locks:
            del _game_loop_locks[game_id]
        logger.info(f"Game loop ended for game {game_id}")

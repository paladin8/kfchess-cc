"""Replay session management for WebSocket playback.

This module provides the ReplaySession class that manages replay playback
for a single client. It runs the ReplayEngine and streams state updates
via WebSocket, allowing clients to watch replays with play/pause/seek controls.

Performance Optimization:
-------------------------
This implementation uses incremental state advancement for O(n) total playback
instead of the naive O(n²) approach (recomputing from tick 0 every frame).

The key insight is that sequential playback only needs to advance by one tick,
which is an O(1) operation. We cache the current GameState and advance it
incrementally during playback. Only seeks require full recomputation.

TODO (Distributed/Multi-Server):
--------------------------------
In a distributed deployment where replay sessions can migrate between servers:
1. On session handoff, client sends current_tick in reconnect message
2. New server recomputes state from tick 0 to current_tick (O(n) one-time cost)
3. Consider keyframe caching in Redis: store state snapshots every N ticks
   to reduce seek cost from O(n) to O(n/N) in the average case
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from kfchess.game.collision import (
    get_interpolated_position,
    is_piece_moving,
    is_piece_on_cooldown,
)
from kfchess.game.replay import Replay, ReplayEngine
from kfchess.game.state import GameState

logger = logging.getLogger(__name__)


class ReplaySession:
    """Manages replay playback for a single client.

    This class handles:
    - Playback state (current tick, playing/paused)
    - WebSocket communication with the client
    - Tick-by-tick state simulation using ReplayEngine
    - Play, pause, and seek commands

    Attributes:
        replay: The replay data being played back
        websocket: WebSocket connection to the client
        current_tick: Current playback position in ticks
        is_playing: Whether playback is currently running
    """

    def __init__(
        self,
        replay: Replay,
        websocket: WebSocket,
        game_id: str,
        resolved_players: dict[int, str] | None = None,
    ) -> None:
        """Initialize the replay session.

        Args:
            replay: The replay data to play back
            websocket: WebSocket connection to the client
            game_id: The game ID for logging
            resolved_players: Pre-resolved display names for players (optional)
        """
        self.replay = replay
        self.websocket = websocket
        self.game_id = game_id
        self.resolved_players = resolved_players
        self.engine = ReplayEngine(replay)
        self.current_tick = 0
        self.is_playing = False
        self._playback_task: asyncio.Task[None] | None = None
        self._closed = False
        self._lock = asyncio.Lock()

        # Cached state for O(1) incremental playback
        # Instead of recomputing from tick 0 every frame (O(n) per frame = O(n²) total),
        # we cache the current state and advance it by one tick (O(1) per frame = O(n) total)
        self._cached_state: GameState | None = None
        self._cached_tick: int = -1  # The tick that _cached_state represents

        # Track previous state for change detection optimization
        self._prev_active_move_ids: set[str] = set()
        self._prev_cooldown_ids: set[str] = set()
        self._is_first_tick: bool = True

    async def start(self) -> None:
        """Initialize session and send replay info.

        Sends the replay metadata and initial state at tick 0.
        """
        await self._send_replay_info()
        await self._send_state_at_tick(0)

    async def handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming control message from client.

        Args:
            message: Parsed JSON message from client

        Supported message types:
        - {"type": "play"}: Start/resume playback
        - {"type": "pause"}: Pause playback
        - {"type": "seek", "tick": N}: Jump to tick N
        """
        msg_type = message.get("type")

        if msg_type == "play":
            await self.play()
        elif msg_type == "pause":
            await self.pause()
        elif msg_type == "seek":
            tick = message.get("tick", 0)
            # Validate tick is an integer
            if not isinstance(tick, int):
                try:
                    tick = int(tick)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid seek tick value: {tick}")
                    return
            await self.seek(tick)
        else:
            logger.warning(f"Unknown replay message type: {msg_type}")

    async def play(self) -> None:
        """Start or resume playback.

        If already playing, this is a no-op.
        Creates a background task that advances ticks at the configured rate.
        """
        async with self._lock:
            if self.is_playing or self._closed:
                return

            # Don't start if already at the end
            if self.current_tick >= self.replay.total_ticks:
                return

            self.is_playing = True
            await self._send_playback_status()
            self._playback_task = asyncio.create_task(self._playback_loop())
            logger.info(f"Replay {self.game_id}: playback started at tick {self.current_tick}")

    async def pause(self) -> None:
        """Pause playback.

        Stops the playback task if running and sends updated status.
        """
        task_to_cancel = None
        was_playing = False

        async with self._lock:
            was_playing = self.is_playing
            self.is_playing = False
            task_to_cancel = self._playback_task
            self._playback_task = None

        # Cancel and await task outside of lock to avoid deadlock
        if task_to_cancel:
            task_to_cancel.cancel()
            try:
                await task_to_cancel
            except asyncio.CancelledError:
                pass

        if was_playing and not self._closed:
            await self._send_playback_status()
            logger.info(f"Replay {self.game_id}: playback paused at tick {self.current_tick}")

    async def seek(self, tick: int) -> None:
        """Jump to a specific tick.

        Args:
            tick: The tick to jump to (clamped to valid range)

        If playback was running, it will resume from the new position.

        Note: Seeking invalidates the state cache, requiring O(n) recomputation
        on the next state request. Sequential playback from the new position
        will then be O(1) per tick again.

        TODO (Distributed/Keyframes): With keyframe caching, seek cost could be
        reduced from O(n) to O(n/100) by loading the nearest keyframe from Redis.
        """
        async with self._lock:
            was_playing = self.is_playing

        # Pause without holding the lock (pause acquires the lock itself)
        await self.pause()

        async with self._lock:
            if self._closed:
                return

            # Clamp tick to valid range
            self.current_tick = max(0, min(tick, self.replay.total_ticks))

            # Invalidate cache - will trigger recomputation on next _get_state_at_tick
            # The _get_state_at_tick call in _send_state_at_tick will repopulate the cache
            self._invalidate_cache()

            await self._send_state_at_tick(self.current_tick)
            await self._send_playback_status()

            logger.info(f"Replay {self.game_id}: seeked to tick {self.current_tick}")

        # Resume playback if it was running (and not at end)
        if was_playing and self.current_tick < self.replay.total_ticks:
            await self.play()

    async def close(self) -> None:
        """Clean up the session.

        Stops playback and marks the session as closed.
        """
        async with self._lock:
            self._closed = True

        await self.pause()
        logger.info(f"Replay {self.game_id}: session closed")

    async def _playback_loop(self) -> None:
        """Main playback loop - advances tick and sends state.

        Runs at the tick rate the replay was recorded at (for backwards compatibility).
        Stops when reaching the end or when paused.

        Only sends state updates when state changes (active moves or cooldowns changed).
        """
        import time

        # Use the tick rate the replay was recorded at for accurate playback
        # Old replays default to 10 Hz, new replays use current tick rate
        tick_rate_hz = self.replay.tick_rate_hz
        tick_interval = 1.0 / tick_rate_hz
        tick_interval_ms = 1000.0 / tick_rate_hz

        try:
            while True:
                await asyncio.sleep(tick_interval)
                # Track when this tick started (after sleep completes)
                tick_start_time = time.monotonic()

                async with self._lock:
                    if not self.is_playing or self._closed:
                        break

                    if self.current_tick >= self.replay.total_ticks:
                        break

                    self.current_tick += 1
                    try:
                        await self._send_state_at_tick_if_changed(
                            self.current_tick, tick_start_time, tick_interval_ms
                        )
                    except Exception as e:
                        logger.warning(f"Replay {self.game_id}: send failed, closing: {e}")
                        self._closed = True
                        self.is_playing = False
                        break

                    # Check if we've reached the end
                    if self.current_tick >= self.replay.total_ticks:
                        self.is_playing = False
                        try:
                            await self._send_game_over()
                        except Exception as e:
                            logger.warning(f"Replay {self.game_id}: game_over send failed: {e}")
                            self._closed = True
                            self.is_playing = False
                        break

        except asyncio.CancelledError:
            # Task was cancelled (pause or close)
            pass
        finally:
            async with self._lock:
                if not self._closed:
                    try:
                        await self._send_playback_status()
                    except Exception as e:
                        logger.warning(f"Replay {self.game_id}: status send failed: {e}")

    async def _send_state_at_tick(self, tick: int, time_since_tick: float = 0.0) -> None:
        """Compute and send state at the given tick.

        This method uses incremental state advancement when possible for O(1)
        performance during sequential playback. Falls back to full recomputation
        from tick 0 when the cache is invalid (after seeks or on first call).

        Performance characteristics:
        - Sequential playback (tick == cached_tick + 1): O(1) - advance one tick
        - Random access / seek: O(n) - recompute from tick 0

        Args:
            tick: The tick to compute state for
            time_since_tick: Milliseconds elapsed since tick started (for client interpolation)

        Uses the same state message format as live games.

        Raises:
            Exception: If WebSocket send fails (connection closed)

        TODO (Distributed): For server handoff, the new server receives current_tick
        from client and calls this method. Consider keyframe caching in Redis to
        reduce seek cost: store GameState snapshots every 100 ticks, then seek
        becomes O(n/100) + O(100) = O(n/100) in the average case.
        """
        if self._closed:
            return

        state = self._get_state_at_tick(tick)
        message = self._format_state_update(state, time_since_tick)
        await self.websocket.send_json(message)

    async def _send_state_at_tick_if_changed(
        self, tick: int, tick_start_time: float, tick_interval_ms: float
    ) -> None:
        """Send state at the given tick only if state has changed.

        This optimization reduces bandwidth by only sending updates when:
        - It's the first tick after starting playback
        - Active moves have changed (piece started/finished moving)
        - Cooldowns have changed (piece entered/exited cooldown)

        Args:
            tick: The tick to compute state for
            tick_start_time: Monotonic time when this tick started (from time.monotonic())
            tick_interval_ms: Tick interval in milliseconds (for clamping time_since_tick)
        """
        import time

        if self._closed:
            return

        state = self._get_state_at_tick(tick)

        # Get current state IDs for change detection
        curr_active_move_ids = {m.piece_id for m in state.active_moves}
        curr_cooldown_ids = {c.piece_id for c in state.cooldowns}

        # Check if state has changed
        state_changed = (
            self._is_first_tick
            or self._prev_active_move_ids != curr_active_move_ids
            or self._prev_cooldown_ids != curr_cooldown_ids
        )

        if state_changed:
            # Calculate time_since_tick right before sending (captures actual elapsed time)
            elapsed_in_tick = (time.monotonic() - tick_start_time) * 1000  # Convert to ms
            time_since_tick = min(elapsed_in_tick, tick_interval_ms)

            message = self._format_state_update(state, time_since_tick)
            await self.websocket.send_json(message)

        # Update previous state tracking
        self._prev_active_move_ids = curr_active_move_ids
        self._prev_cooldown_ids = curr_cooldown_ids
        self._is_first_tick = False

    def _get_state_at_tick(self, tick: int) -> GameState:
        """Get game state at the given tick, using cache when possible.

        This is the core of the O(n²) -> O(n) optimization for replay playback.

        Args:
            tick: The tick to get state for

        Returns:
            GameState at the specified tick

        Cache behavior:
        - If tick == _cached_tick: return cached state (O(1))
        - If tick == _cached_tick + 1: advance one tick (O(1))
        - Otherwise: recompute from scratch (O(n))
        """
        # Case 1: Cache hit - same tick requested
        if self._cached_state is not None and self._cached_tick == tick:
            return self._cached_state

        # Case 2: Sequential advancement - advance one tick (O(1))
        # This is the common case during playback
        if self._cached_state is not None and self._cached_tick == tick - 1:
            # Advance the cached state by one tick
            self.engine.advance_one_tick(self._cached_state)
            self._cached_tick = tick
            return self._cached_state

        # Case 3: Cache miss - need full recomputation (O(n))
        # This happens on:
        # - First call (cache is empty)
        # - After seeks (cache invalidated)
        # - Non-sequential access (unlikely during normal playback)
        #
        # TODO (Distributed/Keyframes): Check Redis for nearest keyframe before tick,
        # then only replay from keyframe to tick. Example:
        #   keyframe_tick = (tick // 100) * 100
        #   cached_state = redis.get(f"replay:{game_id}:keyframe:{keyframe_tick}")
        #   if cached_state: replay from keyframe_tick to tick (O(tick - keyframe_tick))
        #   else: replay from 0 (O(tick))
        logger.debug(
            f"Replay {self.game_id}: cache miss at tick {tick} "
            f"(cached_tick={self._cached_tick}), recomputing from tick 0"
        )
        self._cached_state = self.engine.get_state_at_tick(tick)
        self._cached_tick = tick
        return self._cached_state

    def _invalidate_cache(self) -> None:
        """Invalidate the cached state and change detection tracking.

        Called when seeking to a non-sequential tick. The next call to
        _get_state_at_tick will trigger a full recomputation.

        TODO (Distributed): When implementing keyframe caching, this method
        could instead seek to the nearest keyframe to reduce recomputation cost.
        """
        self._cached_state = None
        self._cached_tick = -1
        # Reset change detection - force state to be sent after seek
        self._prev_active_move_ids = set()
        self._prev_cooldown_ids = set()
        self._is_first_tick = True

    def _format_state_update(self, state: GameState, time_since_tick: float = 0.0) -> dict[str, Any]:
        """Format game state as a state message.

        Args:
            state: The game state to format
            time_since_tick: Milliseconds elapsed since tick started (for client interpolation)

        Returns:
            Dictionary in the same format as live game state messages
        """
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
                    "on_cooldown": is_piece_on_cooldown(
                        piece.id, state.cooldowns, state.current_tick
                    ),
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

        # Use "state" type to match live game protocol
        return {
            "type": "state",
            "tick": state.current_tick,
            "pieces": pieces_data,
            "active_moves": active_moves_data,
            "cooldowns": cooldowns_data,
            "events": [],  # Include empty events array for consistency with live games
            "time_since_tick": time_since_tick,
        }

    async def _send_replay_info(self) -> None:
        """Send replay metadata to the client."""
        if self._closed:
            return

        # Use resolved player names if available, otherwise fall back to raw IDs
        players_to_send = self.resolved_players or self.replay.players

        await self.websocket.send_json(
            {
                "type": "replay_info",
                "game_id": self.game_id,
                "speed": self.replay.speed.value,
                "board_type": self.replay.board_type.value,
                "players": {str(k): v for k, v in players_to_send.items()},
                "total_ticks": self.replay.total_ticks,
                "winner": self.replay.winner,
                "win_reason": self.replay.win_reason,
                "tick_rate_hz": self.replay.tick_rate_hz,
            }
        )

    async def _send_playback_status(self) -> None:
        """Send current playback status to the client."""
        if self._closed:
            return

        await self.websocket.send_json(
            {
                "type": "playback_status",
                "is_playing": self.is_playing,
                "current_tick": self.current_tick,
                "total_ticks": self.replay.total_ticks,
            }
        )

    async def _send_game_over(self) -> None:
        """Send game over message when replay reaches the end."""
        if self._closed:
            return

        await self.websocket.send_json(
            {
                "type": "game_over",
                "winner": self.replay.winner,
                "reason": self.replay.win_reason,
            }
        )

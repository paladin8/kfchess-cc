"""Replay session management for WebSocket playback.

This module provides the ReplaySession class that manages replay playback
for a single client. It runs the ReplayEngine and streams state updates
via WebSocket, allowing clients to watch replays with play/pause/seek controls.
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
from kfchess.game.state import SPEED_CONFIGS, GameState

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

    def __init__(self, replay: Replay, websocket: WebSocket, game_id: str) -> None:
        """Initialize the replay session.

        Args:
            replay: The replay data to play back
            websocket: WebSocket connection to the client
            game_id: The game ID for logging
        """
        self.replay = replay
        self.websocket = websocket
        self.game_id = game_id
        self.engine = ReplayEngine(replay)
        self.current_tick = 0
        self.is_playing = False
        self._playback_task: asyncio.Task[None] | None = None
        self._closed = False
        self._lock = asyncio.Lock()

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

        Runs at the configured tick rate (typically 10 ticks/second).
        Stops when reaching the end or when paused.
        """
        config = SPEED_CONFIGS[self.replay.speed]
        tick_interval = config.tick_period_ms / 1000.0

        try:
            while True:
                await asyncio.sleep(tick_interval)

                async with self._lock:
                    if not self.is_playing or self._closed:
                        break

                    if self.current_tick >= self.replay.total_ticks:
                        break

                    self.current_tick += 1
                    try:
                        await self._send_state_at_tick(self.current_tick)
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

    async def _send_state_at_tick(self, tick: int) -> None:
        """Compute and send state at the given tick.

        Args:
            tick: The tick to compute state for

        Uses the same state message format as live games.

        Raises:
            Exception: If WebSocket send fails (connection closed)
        """
        if self._closed:
            return

        state = self.engine.get_state_at_tick(tick)
        message = self._format_state_update(state)
        await self.websocket.send_json(message)

    def _format_state_update(self, state: GameState) -> dict[str, Any]:
        """Format game state as a state message.

        Args:
            state: The game state to format

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
            pieces_data.append({
                "id": piece.id,
                "type": piece.type.value,
                "player": piece.player,
                "row": pos[0],
                "col": pos[1],
                "captured": piece.captured,
                "moving": is_piece_moving(piece.id, state.active_moves),
                "on_cooldown": is_piece_on_cooldown(piece.id, state.cooldowns, state.current_tick),
                "moved": piece.moved,
            })

        # Build active moves data
        active_moves_data = []
        for move in state.active_moves:
            total_ticks = (len(move.path) - 1) * config.ticks_per_square
            elapsed = max(0, state.current_tick - move.start_tick)
            progress = min(1.0, elapsed / total_ticks) if total_ticks > 0 else 1.0
            active_moves_data.append({
                "piece_id": move.piece_id,
                "path": move.path,
                "start_tick": move.start_tick,
                "progress": progress,
            })

        # Build cooldown data
        cooldowns_data = []
        for cd in state.cooldowns:
            remaining = max(0, (cd.start_tick + cd.duration) - state.current_tick)
            cooldowns_data.append({
                "piece_id": cd.piece_id,
                "remaining_ticks": remaining,
            })

        # Use "state" type to match live game protocol
        return {
            "type": "state",
            "tick": state.current_tick,
            "pieces": pieces_data,
            "active_moves": active_moves_data,
            "cooldowns": cooldowns_data,
            "events": [],  # Include empty events array for consistency with live games
        }

    async def _send_replay_info(self) -> None:
        """Send replay metadata to the client."""
        if self._closed:
            return

        await self.websocket.send_json({
            "type": "replay_info",
            "game_id": self.game_id,
            "speed": self.replay.speed.value,
            "board_type": self.replay.board_type.value,
            "players": {str(k): v for k, v in self.replay.players.items()},
            "total_ticks": self.replay.total_ticks,
            "winner": self.replay.winner,
            "win_reason": self.replay.win_reason,
        })

    async def _send_playback_status(self) -> None:
        """Send current playback status to the client."""
        if self._closed:
            return

        await self.websocket.send_json({
            "type": "playback_status",
            "is_playing": self.is_playing,
            "current_tick": self.current_tick,
            "total_ticks": self.replay.total_ticks,
        })

    async def _send_game_over(self) -> None:
        """Send game over message when replay reaches the end."""
        if self._closed:
            return

        await self.websocket.send_json({
            "type": "game_over",
            "winner": self.replay.winner,
            "reason": self.replay.win_reason,
        })

"""AI Controller — orchestrates the AI decision pipeline."""

import random

from kfchess.ai.arrival_field import ArrivalField
from kfchess.ai.eval import Eval
from kfchess.ai.move_gen import MoveGen
from kfchess.ai.state_extractor import AIState, StateExtractor
from kfchess.game.engine import GameEngine
from kfchess.game.state import TICK_RATE_HZ, GameState, Speed

# Think delay ranges in seconds (min, max) by level and speed
THINK_DELAYS: dict[int, dict[Speed, tuple[float, float]]] = {
    1: {
        Speed.STANDARD: (1.0, 6.0),
        Speed.LIGHTNING: (1.0, 4.0),
    },
    2: {
        Speed.STANDARD: (0.6, 5.0),
        Speed.LIGHTNING: (0.6, 3.0),
    },
    3: {
        Speed.STANDARD: (0.3, 3.0),
        Speed.LIGHTNING: (0.3, 2.0),
    },
}

# Piece consideration limits by level
MAX_PIECES: dict[int, int] = {1: 4, 2: 8, 3: 16}
MAX_CANDIDATES_PER_PIECE: dict[int, int] = {1: 4, 2: 8, 3: 12}

# Minimum delay after cooldown expires before AI can move the piece (~167ms)
COOLDOWN_BUFFER_TICKS = 5

# Enemy moves younger than this are invisible to the AI (~100ms reaction delay)
REACTION_DELAY_TICKS = 3

# AI cannot move before this many ticks into the game (~500ms grace period)
GAME_START_DELAY_TICKS = 15


class AIController:
    """Orchestrates AI decision-making pipeline."""

    def __init__(self, level: int = 1, speed: Speed = Speed.STANDARD, noise: bool = True):
        self.level = min(max(level, 1), 3)
        self.speed = speed
        self.noise = noise
        self.last_move_tick: int = -9999  # Tick of last move
        self.think_delay_ticks: int = 0  # Current think delay in ticks
        self._cached_ai_state: AIState | None = None
        self._cached_tick: int = -1
        self._roll_think_delay()

    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        """Check if AI should attempt a move this tick."""
        # Don't move in the first 500ms of the game
        if current_tick < GAME_START_DELAY_TICKS:
            return False

        # Check think delay (cheap, no allocations)
        ticks_since_last = current_tick - self.last_move_tick
        if ticks_since_last < self.think_delay_ticks:
            return False

        # Quick check: any idle pieces? Avoids full state extraction.
        moving_ids = {m.piece_id for m in state.active_moves}
        cooldown_ids = {c.piece_id for c in state.cooldowns}
        has_idle = any(
            not p.captured
            and p.player == player
            and p.id not in moving_ids
            and p.id not in cooldown_ids
            and (p.cooldown_end_tick == 0
                 or current_tick - p.cooldown_end_tick >= COOLDOWN_BUFFER_TICKS)
            for p in state.board.pieces
        )
        if not has_idle:
            return False

        # Extract state and cache it for get_move()
        ai_state = StateExtractor.extract(
            state, player,
            cooldown_buffer_ticks=COOLDOWN_BUFFER_TICKS,
            reaction_delay_ticks=REACTION_DELAY_TICKS,
        )
        self._cached_ai_state = ai_state
        self._cached_tick = current_tick
        return len(ai_state.get_movable_pieces()) > 0

    def get_move(
        self, state: GameState, player: int
    ) -> tuple[str, int, int] | None:
        """Run the full AI pipeline and return the best move.

        Returns:
            (piece_id, to_row, to_col) or None
        """
        # Reuse cached state from should_move() if same tick
        if (
            self._cached_ai_state is not None
            and self._cached_tick == state.current_tick
        ):
            ai_state = self._cached_ai_state
            self._cached_ai_state = None
        else:
            ai_state = StateExtractor.extract(
                state, player,
                cooldown_buffer_ticks=COOLDOWN_BUFFER_TICKS,
                reaction_delay_ticks=REACTION_DELAY_TICKS,
            )

        # Compute enemy escape moves for L3 dodgeability.
        # Use ignore_cooldown=True so pieces on cooldown still have potential
        # escape squares — they may finish cooldown before our attack arrives.
        if self.level >= 3:
            escape_moves: dict[str, list[tuple[int, int]]] = {}
            for ep in state.players:
                if ep != player:
                    for pid, r, c in GameEngine.get_legal_moves_fast(
                        state, ep, ignore_cooldown=True,
                    ):
                        escape_moves.setdefault(pid, []).append((r, c))
            ai_state.enemy_escape_moves = escape_moves

        # Compute arrival fields for all levels
        arrival_data = None
        if ai_state.speed_config is not None:
            critical_only = ai_state.board_width > 8  # 4-player boards
            arrival_data = ArrivalField.compute(
                ai_state, ai_state.speed_config, critical_only=critical_only,
            )

        # Generate candidates
        candidates = MoveGen.generate_candidates(
            state,
            ai_state,
            player,
            max_pieces=MAX_PIECES.get(self.level, 2),
            max_candidates_per_piece=MAX_CANDIDATES_PER_PIECE.get(self.level, 4),
            level=self.level,
            arrival_data=arrival_data,
        )

        if not candidates:
            return None

        # Score and select
        scored = Eval.score_candidates(
            candidates, ai_state, noise=self.noise,
            level=self.level, arrival_data=arrival_data,
        )

        if not scored:
            return None

        best_move, best_score = scored[0]

        # Skip if all options are clearly negative (better to wait)
        if best_score < -1:
            return None

        # Record move timing
        self.last_move_tick = state.current_tick
        self._roll_think_delay()

        return (best_move.piece_id, best_move.to_row, best_move.to_col)

    def _roll_think_delay(self) -> None:
        """Roll a new random think delay."""
        delays = THINK_DELAYS.get(self.level, {})
        min_s, max_s = delays.get(self.speed, (0.0, 4.0))
        delay_seconds = random.uniform(min_s, max_s)
        self.think_delay_ticks = int(delay_seconds * TICK_RATE_HZ)

"""Dummy AI that makes random valid moves.

This is used for testing gameplay mechanics with a simple opponent.
"""

import random

from kfchess.ai.base import AIPlayer
from kfchess.game.engine import GameEngine
from kfchess.game.state import TICK_RATE_HZ, GameState, Speed

# Move intervals in seconds for each speed
MOVE_INTERVAL_SECONDS = {
    Speed.STANDARD: 4.0,  # 1 move every 4 seconds
    Speed.LIGHTNING: 2.0,  # 1 move every 2 seconds
}


class DummyAI(AIPlayer):
    """AI that makes random valid moves at random intervals."""

    def __init__(self, speed: Speed = Speed.STANDARD):
        """Initialize the dummy AI.

        Args:
            speed: Game speed, used to determine move frequency.
                   Standard: ~1 move every 4 seconds
                   Lightning: ~1 move every 2 seconds
        """
        interval = MOVE_INTERVAL_SECONDS.get(speed, 4.0)
        ticks_between_moves = interval * TICK_RATE_HZ
        self.move_probability = 1.0 / ticks_between_moves

    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        """Randomly decide whether to move this tick."""
        return random.random() < self.move_probability

    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        """Return a random legal move."""
        legal_moves = GameEngine.get_legal_moves(state, player)
        if not legal_moves:
            return None

        # Pick a random move
        piece_id, to_row, to_col = random.choice(legal_moves)
        return (piece_id, to_row, to_col)

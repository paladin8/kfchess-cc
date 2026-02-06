"""KungFuAI — heuristic-based AI implementing the AIPlayer interface."""

from kfchess.ai.base import AIPlayer
from kfchess.ai.controller import AIController
from kfchess.game.state import GameState, Speed


class KungFuAI(AIPlayer):
    """Heuristic-based AI for Kung Fu Chess.

    Supports difficulty levels 1-3:
    - Level 1 (Novice): Positional heuristics, basic captures, high noise
    - Level 2 (Intermediate): Arrival fields, commitment penalty (future)
    - Level 3 (Advanced): Dodgeability, recapture positioning
    """

    def __init__(self, level: int = 1, speed: Speed = Speed.STANDARD, noise: bool = True):
        self.level = level
        self.speed = speed
        self.controller = AIController(level=level, speed=speed, noise=noise)

    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        """Check if AI should attempt a move this tick."""
        return self.controller.should_move(state, player, current_tick)

    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        """Return the best move found by the AI pipeline."""
        return self.controller.get_move(state, player)

"""Dummy AI that never moves.

This is used for testing basic gameplay mechanics without AI interference.
"""

from kfchess.ai.base import AIPlayer
from kfchess.game.state import GameState


class DummyAI(AIPlayer):
    """AI that never moves. For testing basic gameplay."""

    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        """Never wants to move."""
        return False

    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        """Returns no move."""
        return None

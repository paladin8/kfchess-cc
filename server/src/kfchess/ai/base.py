"""Base class for AI implementations."""

from abc import ABC, abstractmethod

from kfchess.game.state import GameState


class AIPlayer(ABC):
    """Base class for AI implementations.

    AI players decide when and what moves to make for their player.
    """

    @abstractmethod
    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        """Return True if AI wants to make a move this tick.

        Args:
            state: Current game state
            player: Player number the AI is playing as
            current_tick: Current game tick

        Returns:
            True if the AI wants to make a move
        """

    @abstractmethod
    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        """Return the move the AI wants to make.

        Args:
            state: Current game state
            player: Player number the AI is playing as

        Returns:
            (piece_id, to_row, to_col) or None if no move
        """

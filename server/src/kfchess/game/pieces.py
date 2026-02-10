"""Piece definitions for Kung Fu Chess."""

from dataclasses import dataclass, field
from enum import Enum


class PieceType(Enum):
    """Chess piece types."""

    PAWN = "P"
    KNIGHT = "N"
    BISHOP = "B"
    ROOK = "R"
    QUEEN = "Q"
    KING = "K"

    def __str__(self) -> str:
        return self.value


@dataclass
class Piece:
    """A chess piece on the board.

    Attributes:
        id: Unique identifier in format "TYPE:PLAYER:START_ROW:START_COL"
        type: The piece type (pawn, knight, etc.)
        player: Player number (1 or 2 for standard, 1-4 for 4-player)
        row: Current row position (can be float during movement interpolation)
        col: Current column position (can be float during movement interpolation)
        captured: Whether the piece has been captured
        moved: Whether the piece has moved (for castling eligibility)
    """

    id: str
    type: PieceType
    player: int
    row: float
    col: float
    captured: bool = False
    moved: bool = False
    cooldown_end_tick: int = 0

    # Cache for grid_position to avoid repeated round() calls
    _grid_cache: tuple[int, int] | None = field(default=None, repr=False, compare=False)
    _grid_cache_row: float = field(default=float("nan"), repr=False, compare=False)
    _grid_cache_col: float = field(default=float("nan"), repr=False, compare=False)

    @classmethod
    def create(cls, piece_type: PieceType, player: int, row: int, col: int) -> "Piece":
        """Create a new piece with auto-generated ID."""
        piece_id = f"{piece_type.value}:{player}:{row}:{col}"
        return cls(
            id=piece_id,
            type=piece_type,
            player=player,
            row=float(row),
            col=float(col),
        )

    def copy(self) -> "Piece":
        """Create a copy of this piece."""
        return Piece(
            id=self.id,
            type=self.type,
            player=self.player,
            row=self.row,
            col=self.col,
            captured=self.captured,
            moved=self.moved,
            cooldown_end_tick=self.cooldown_end_tick,
        )

    def to_dict(self) -> dict:
        """Serialize piece to a dictionary for snapshot persistence."""
        return {
            "id": self.id,
            "type": self.type.value,
            "player": self.player,
            "row": self.row,
            "col": self.col,
            "captured": self.captured,
            "moved": self.moved,
            "cooldown_end_tick": self.cooldown_end_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Piece":
        """Deserialize piece from a dictionary."""
        return cls(
            id=data["id"],
            type=PieceType(data["type"]),
            player=data["player"],
            row=float(data["row"]),
            col=float(data["col"]),
            captured=data.get("captured", False),
            moved=data.get("moved", False),
            cooldown_end_tick=data.get("cooldown_end_tick", 0),
        )

    @property
    def position(self) -> tuple[float, float]:
        """Get the current position as (row, col) tuple."""
        return (self.row, self.col)

    @property
    def grid_position(self) -> tuple[int, int]:
        """Get the current position snapped to grid as (row, col) tuple.

        Cached to avoid repeated round() calls (profiling showed 1.6M calls).
        """
        # Check if cache is valid (row/col unchanged)
        if self._grid_cache is not None and self._grid_cache_row == self.row and self._grid_cache_col == self.col:
            return self._grid_cache
        # Compute and cache
        result = (int(round(self.row)), int(round(self.col)))
        self._grid_cache = result
        self._grid_cache_row = self.row
        self._grid_cache_col = self.col
        return result

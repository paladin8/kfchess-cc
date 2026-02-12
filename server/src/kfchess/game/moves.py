"""Move definitions and validation for Kung Fu Chess."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from kfchess.game.board import Board, BoardType
from kfchess.game.pieces import Piece, PieceType

logger = logging.getLogger(__name__)

# Slider piece types (move along lines/diagonals, can be blocked by same-line enemies)
_SLIDER_TYPES = frozenset({PieceType.BISHOP, PieceType.ROOK, PieceType.QUEEN})

# Path type: can be int or float (floats used for knight midpoint)
PathPoint = tuple[float, float]


@dataclass
class _EnemyMoveInfo:
    """Pre-extracted data about an enemy's active move for same-line blocking."""

    dr: int
    dc: int
    start_r: int
    start_c: int
    forward_squares: list[tuple[int, int]]


@dataclass
class PathClearContext:
    """Precomputed blocking data reusable across all candidates for one player.

    Built once per player per ``get_legal_moves_fast`` call, eliminating
    repeated iteration over ``active_moves`` inside ``_is_path_clear``.
    """

    own_forward_path: set[tuple[int, int]] = field(default_factory=set)
    moving_piece_ids: set[str] = field(default_factory=set)
    enemy_moves: list[_EnemyMoveInfo] = field(default_factory=list)


def build_path_clear_context(
    player: int,
    board: Board,
    active_moves: list[Move],
    current_tick: int,
    ticks_per_square: int,
) -> PathClearContext:
    """Build a PathClearContext for *player* given the current game state."""
    own_forward: set[tuple[int, int]] = set()
    moving_ids: set[str] = set()
    enemy_moves: list[_EnemyMoveInfo] = []

    for move in active_moves:
        moving_ids.add(move.piece_id)
        moving_piece = board.get_piece_by_id(move.piece_id)
        if moving_piece is None:
            continue

        if moving_piece.player == player:
            forward_squares = _get_forward_path(move, current_tick, ticks_per_square)
            own_forward.update(forward_squares)
        else:
            # Enemy move – extract info for same-line blocking
            if len(move.path) >= 2:
                e_dr = int(move.path[1][0] - move.path[0][0])
                e_dc = int(move.path[1][1] - move.path[0][1])
                e_start_r = int(move.path[0][0])
                e_start_c = int(move.path[0][1])
                fwd = _get_forward_path(move, current_tick, ticks_per_square)
                enemy_moves.append(
                    _EnemyMoveInfo(
                        dr=e_dr, dc=e_dc,
                        start_r=e_start_r, start_c=e_start_c,
                        forward_squares=fwd,
                    )
                )

    return PathClearContext(
        own_forward_path=own_forward,
        moving_piece_ids=moving_ids,
        enemy_moves=enemy_moves,
    )


@dataclass(frozen=True)
class PlayerOrientation:
    """Defines movement directions for a player position in 4-player mode.

    Attributes:
        forward: (row_delta, col_delta) for "forward" pawn movement
        pawn_home_axis: The row or column index where pawns start (second row from edge)
        back_row_axis: The row or column index for back row pieces
        promotion_axis: The row or column index that triggers pawn promotion
        axis: "row" or "col" - which axis pawns move along
    """

    forward: tuple[int, int]
    pawn_home_axis: int
    back_row_axis: int
    promotion_axis: int
    axis: str  # "row" or "col"


# Player orientations for 4-player mode (12x12 board)
# Player 1 (East): pieces on cols 10-11, moves left (toward col 0)
# Player 2 (South): pieces on rows 10-11, moves up (toward row 0)
# Player 3 (West): pieces on cols 0-1, moves right (toward col 11)
# Player 4 (North): pieces on rows 0-1, moves down (toward row 11)
FOUR_PLAYER_ORIENTATIONS: dict[int, PlayerOrientation] = {
    1: PlayerOrientation(
        forward=(0, -1), pawn_home_axis=10, back_row_axis=11, promotion_axis=0, axis="col"
    ),
    2: PlayerOrientation(
        forward=(-1, 0), pawn_home_axis=10, back_row_axis=11, promotion_axis=0, axis="row"
    ),
    3: PlayerOrientation(
        forward=(0, 1), pawn_home_axis=1, back_row_axis=0, promotion_axis=11, axis="col"
    ),
    4: PlayerOrientation(
        forward=(1, 0), pawn_home_axis=1, back_row_axis=0, promotion_axis=11, axis="row"
    ),
}


@dataclass
class Move:
    """Represents an active piece movement.

    Attributes:
        piece_id: ID of the moving piece
        path: List of (row, col) positions the piece travels through.
              Usually integers, but knights use float midpoints.
        start_tick: Game tick when the move started
        extra_move: Optional secondary move (e.g., rook in castling)
    """

    piece_id: str
    path: list[PathPoint]
    start_tick: int
    extra_move: Move | None = None

    def to_dict(self) -> dict:
        """Serialize move to a dictionary for snapshot persistence."""
        return {
            "piece_id": self.piece_id,
            "path": [list(p) for p in self.path],
            "start_tick": self.start_tick,
            "extra_move": self.extra_move.to_dict() if self.extra_move else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Move:
        """Deserialize move from a dictionary."""
        return cls(
            piece_id=data["piece_id"],
            path=[tuple(p) for p in data["path"]],
            start_tick=data["start_tick"],
            extra_move=cls.from_dict(data["extra_move"]) if data.get("extra_move") else None,
        )

    @property
    def start_position(self) -> PathPoint:
        """Get the starting position of the move."""
        return self.path[0]

    @property
    def end_position(self) -> PathPoint:
        """Get the ending position of the move."""
        return self.path[-1]

    @property
    def num_squares(self) -> int:
        """Get the number of squares the piece moves through (path length - 1)."""
        return len(self.path) - 1


@dataclass
class Cooldown:
    """Represents a piece cooldown period.

    Attributes:
        piece_id: ID of the piece on cooldown
        start_tick: Game tick when cooldown started
        duration: Number of ticks the cooldown lasts
    """

    piece_id: str
    start_tick: int
    duration: int

    def to_dict(self) -> dict:
        """Serialize cooldown to a dictionary for snapshot persistence."""
        return {
            "piece_id": self.piece_id,
            "start_tick": self.start_tick,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Cooldown:
        """Deserialize cooldown from a dictionary."""
        return cls(
            piece_id=data["piece_id"],
            start_tick=data["start_tick"],
            duration=data["duration"],
        )

    def is_active(self, current_tick: int) -> bool:
        """Check if cooldown is still active at the given tick."""
        return current_tick < self.start_tick + self.duration


def compute_move_path(
    piece: Piece,
    board: Board,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
    current_tick: int = 0,
    ticks_per_square: int = 30,
    path_context: PathClearContext | None = None,
) -> list[PathPoint] | None:
    """Compute the path for a piece to move to a destination.

    Returns the path as a list of (row, col) tuples, or None if the move is invalid.
    The path includes the starting position as the first element.
    Most pieces use integer coordinates, but knights use float midpoints.

    Args:
        piece: The piece to move
        board: Current board state
        to_row: Destination row
        to_col: Destination column
        active_moves: Currently active moves (to check for path conflicts)
        current_tick: Current game tick (for forward path blocking)
        ticks_per_square: Ticks to move one square (for forward path blocking)
        path_context: Optional precomputed blocking context (avoids repeated
            iteration over active_moves when validating many candidates)

    Returns:
        List of (row, col) positions forming the path, or None if invalid
    """
    from_row, from_col = piece.grid_position

    # Can't move to same position
    if from_row == to_row and from_col == to_col:
        return None

    # Check if destination is valid
    if not board.is_valid_square(to_row, to_col):
        return None

    # Get the appropriate path computation based on piece type
    path = _compute_piece_path(piece, board, from_row, from_col, to_row, to_col, active_moves)
    if path is None:
        return None

    # Check for blocking pieces along the path (except knights which jump)
    if piece.type != PieceType.KNIGHT:
        if not _is_path_clear(
            path, board, piece.player, active_moves,
            current_tick, ticks_per_square, piece.type,
            path_context=path_context,
        ):
            return None
    else:
        # Knights jump over pieces but still can't land on own pieces
        if not _is_knight_destination_valid(
            path, board, piece.player, active_moves,
            current_tick, ticks_per_square,
            path_context=path_context,
        ):
            return None

    return path


def _compute_piece_path(
    piece: Piece,
    board: Board,
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
) -> list[PathPoint] | None:
    """Compute path based on piece type."""
    match piece.type:
        case PieceType.PAWN:
            return _compute_pawn_path(
                piece, board, from_row, from_col, to_row, to_col, active_moves
            )
        case PieceType.KNIGHT:
            return _compute_knight_path(from_row, from_col, to_row, to_col)
        case PieceType.BISHOP:
            return _compute_bishop_path(from_row, from_col, to_row, to_col)
        case PieceType.ROOK:
            return _compute_rook_path(from_row, from_col, to_row, to_col)
        case PieceType.QUEEN:
            return _compute_queen_path(from_row, from_col, to_row, to_col)
        case PieceType.KING:
            return _compute_king_path(from_row, from_col, to_row, to_col)
        case _:
            return None


def _compute_pawn_path(
    piece: Piece,
    board: Board,
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
) -> list[PathPoint] | None:
    """Compute pawn movement path.

    Pawns can:
    - Move forward 1 square (or 2 from starting position)
    - Capture diagonally (only if stationary opponent piece at destination)

    In 4-player mode, "forward" depends on the player's orientation.
    """
    if board.board_type == BoardType.STANDARD:
        return _compute_pawn_path_standard(
            piece, board, from_row, from_col, to_row, to_col, active_moves
        )
    else:
        return _compute_pawn_path_4player(
            piece, board, from_row, from_col, to_row, to_col, active_moves
        )


def _compute_pawn_path_standard(
    piece: Piece,
    board: Board,
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
) -> list[PathPoint] | None:
    """Compute pawn path for standard 2-player board."""
    direction = -1 if piece.player == 1 else 1  # Player 1 moves up (decreasing row)
    start_row = 6 if piece.player == 1 else 1  # Starting row for each player

    row_diff = to_row - from_row
    col_diff = to_col - from_col

    # Forward movement
    if col_diff == 0:
        # Single square forward
        if row_diff == direction:
            # Can't capture when moving straight - destination must be empty
            # (moving pieces have vacated their origin square)
            target = board.get_piece_at(to_row, to_col)
            if target is not None and not _is_piece_moving(target.id, active_moves):
                return None
            return [(float(from_row), float(from_col)), (float(to_row), float(to_col))]

        # Double square forward from starting position
        if row_diff == 2 * direction and from_row == start_row:
            # Check both squares are empty (moving pieces count as vacated)
            mid_row = from_row + direction
            mid_piece = board.get_piece_at(mid_row, from_col)
            if mid_piece is not None and not _is_piece_moving(mid_piece.id, active_moves):
                return None
            dest_piece = board.get_piece_at(to_row, to_col)
            if dest_piece is not None and not _is_piece_moving(dest_piece.id, active_moves):
                return None
            return [
                (float(from_row), float(from_col)),
                (float(mid_row), float(from_col)),
                (float(to_row), float(to_col)),
            ]

    # Diagonal capture - requires stationary opponent piece at destination
    if abs(col_diff) == 1 and row_diff == direction:
        target = board.get_piece_at(to_row, to_col)
        # Must have an opponent piece that is NOT currently moving
        if target is None or target.player == piece.player:
            return None
        # Check if target is already moving
        if _is_piece_moving(target.id, active_moves):
            return None
        return [(float(from_row), float(from_col)), (float(to_row), float(to_col))]

    return None


def _compute_pawn_path_4player(
    piece: Piece,
    board: Board,
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
) -> list[PathPoint] | None:
    """Compute pawn path for 4-player board.

    In 4-player mode, pawns move along different axes depending on player position:
    - Player 1 (East): moves along columns (left, toward col 2)
    - Player 2 (South): moves along rows (up, toward row 2)
    - Player 3 (West): moves along columns (right, toward col 9)
    - Player 4 (North): moves along rows (down, toward row 9)
    """
    orient = FOUR_PLAYER_ORIENTATIONS.get(piece.player)
    if orient is None:
        return None

    row_diff = to_row - from_row
    col_diff = to_col - from_col
    fwd_row, fwd_col = orient.forward

    # Determine if pawn is at its starting position
    if orient.axis == "col":
        # Pawn moves horizontally (players 1 and 3)
        is_at_start = from_col == orient.pawn_home_axis
        forward_diff = col_diff
        lateral_diff = row_diff
        forward_dir = fwd_col
    else:
        # Pawn moves vertically (players 2 and 4)
        is_at_start = from_row == orient.pawn_home_axis
        forward_diff = row_diff
        lateral_diff = col_diff
        forward_dir = fwd_row

    # Forward movement (no lateral movement)
    if lateral_diff == 0:
        # Single square forward
        if forward_diff == forward_dir:
            # Destination must be empty (moving pieces count as vacated)
            target = board.get_piece_at(to_row, to_col)
            if target is not None and not _is_piece_moving(target.id, active_moves):
                return None
            return [(float(from_row), float(from_col)), (float(to_row), float(to_col))]

        # Double square forward from starting position
        if forward_diff == 2 * forward_dir and is_at_start:
            # Check both squares are empty (moving pieces count as vacated)
            mid_row = from_row + fwd_row
            mid_col = from_col + fwd_col
            mid_piece = board.get_piece_at(mid_row, mid_col)
            if mid_piece is not None and not _is_piece_moving(mid_piece.id, active_moves):
                return None
            dest_piece = board.get_piece_at(to_row, to_col)
            if dest_piece is not None and not _is_piece_moving(dest_piece.id, active_moves):
                return None
            return [
                (float(from_row), float(from_col)),
                (float(mid_row), float(mid_col)),
                (float(to_row), float(to_col)),
            ]

    # Diagonal capture - one forward, one lateral
    if forward_diff == forward_dir and abs(lateral_diff) == 1:
        target = board.get_piece_at(to_row, to_col)
        if target is None or target.player == piece.player:
            return None
        if _is_piece_moving(target.id, active_moves):
            return None
        return [(float(from_row), float(from_col)), (float(to_row), float(to_col))]

    return None


def _is_piece_moving(piece_id: str, active_moves: list[Move]) -> bool:
    """Check if a piece is currently moving."""
    return any(m.piece_id == piece_id for m in active_moves)


def should_promote_pawn(piece: Piece, board: Board, end_row: int, end_col: int) -> bool:
    """Check if a pawn should be promoted after reaching a position.

    Args:
        piece: The pawn piece
        board: The board
        end_row: Row the pawn ended at
        end_col: Column the pawn ended at

    Returns:
        True if the pawn should be promoted
    """
    if piece.type != PieceType.PAWN:
        return False

    if board.board_type == BoardType.STANDARD:
        # Standard 2-player: promote at opposite back row
        promotion_row = 0 if piece.player == 1 else 7
        return end_row == promotion_row
    else:
        # 4-player: check against player's promotion axis
        orient = FOUR_PLAYER_ORIENTATIONS.get(piece.player)
        if orient is None:
            return False

        if orient.axis == "col":
            # Horizontal movement (players 1 and 3) - check column
            return end_col == orient.promotion_axis
        else:
            # Vertical movement (players 2 and 4) - check row
            return end_row == orient.promotion_axis


def _compute_knight_path(
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> list[PathPoint] | None:
    """Compute knight movement path.

    Knights move in an L-shape: 2 squares in one direction, 1 in perpendicular.
    Knights jump over pieces and travel through a midpoint between start and end.
    The path has 3 points: start, midpoint (float), end.
    This takes 2 * move_ticks to complete (2 segments).
    """
    row_diff = abs(to_row - from_row)
    col_diff = abs(to_col - from_col)

    # Valid knight moves: 2+1 or 1+2
    if (row_diff == 2 and col_diff == 1) or (row_diff == 1 and col_diff == 2):
        # Midpoint is average of start and end (can be float like 3.5)
        mid_row = (from_row + to_row) / 2.0
        mid_col = (from_col + to_col) / 2.0
        return [
            (float(from_row), float(from_col)),
            (mid_row, mid_col),
            (float(to_row), float(to_col)),
        ]

    return None


def _compute_bishop_path(
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> list[PathPoint] | None:
    """Compute bishop movement path (diagonal only)."""
    row_diff = to_row - from_row
    col_diff = to_col - from_col

    # Must be diagonal (equal absolute differences)
    if abs(row_diff) != abs(col_diff) or row_diff == 0:
        return None

    return _build_linear_path(from_row, from_col, to_row, to_col)


def _compute_rook_path(
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> list[PathPoint] | None:
    """Compute rook movement path (horizontal or vertical only)."""
    row_diff = to_row - from_row
    col_diff = to_col - from_col

    # Must be horizontal or vertical (one diff must be 0)
    if row_diff != 0 and col_diff != 0:
        return None

    if row_diff == 0 and col_diff == 0:
        return None

    return _build_linear_path(from_row, from_col, to_row, to_col)


def _compute_queen_path(
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> list[PathPoint] | None:
    """Compute queen movement path (diagonal, horizontal, or vertical)."""
    row_diff = to_row - from_row
    col_diff = to_col - from_col

    # Diagonal
    if abs(row_diff) == abs(col_diff) and row_diff != 0:
        return _build_linear_path(from_row, from_col, to_row, to_col)

    # Horizontal or vertical
    if (row_diff == 0) != (col_diff == 0):  # XOR - exactly one must be 0
        return _build_linear_path(from_row, from_col, to_row, to_col)

    return None


def _compute_king_path(
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> list[PathPoint] | None:
    """Compute king movement path (one square in any direction)."""
    row_diff = abs(to_row - from_row)
    col_diff = abs(to_col - from_col)

    # King can move one square in any direction
    if row_diff <= 1 and col_diff <= 1 and (row_diff > 0 or col_diff > 0):
        return [(float(from_row), float(from_col)), (float(to_row), float(to_col))]

    return None


def _build_linear_path(
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
) -> list[PathPoint]:
    """Build a linear path from start to end, including all intermediate squares."""
    path: list[PathPoint] = [(float(from_row), float(from_col))]

    row_dir = 0 if to_row == from_row else (1 if to_row > from_row else -1)
    col_dir = 0 if to_col == from_col else (1 if to_col > from_col else -1)

    current_row, current_col = from_row, from_col

    while (current_row, current_col) != (to_row, to_col):
        current_row += row_dir
        current_col += col_dir
        path.append((float(current_row), float(current_col)))

    return path


def _is_path_clear(
    path: list[PathPoint],
    board: Board,
    player: int,
    active_moves: list[Move],
    current_tick: int = 0,
    ticks_per_square: int = 30,
    piece_type: PieceType | None = None,
    *,
    path_context: PathClearContext | None = None,
) -> bool:
    """Check if a path is clear of blocking pieces.

    Rules:
    - Stationary pieces block (both own and enemy)
    - Own moving pieces' forward path (not yet traversed) blocks own pieces
    - Own moving pieces' already-traversed path does NOT block
    - Enemy moving pieces do NOT block (neither their start nor path)
    - Exception: any enemy piece moving on the same line blocks slider pieces
    - Exception: pawn moving straight is blocked by any oncoming enemy on the same line
      (pawns can't capture straight, so head-on collision is a guaranteed loss)
    - Cannot capture moving enemies (destination with moving enemy = blocked)

    If *path_context* is provided, uses precomputed blocking data instead of
    iterating over *active_moves* each call.
    """
    # ---------- Resolve blocking data (precomputed or on-the-fly) ----------
    if path_context is not None:
        own_forward_path = path_context.own_forward_path
        moving_piece_ids = path_context.moving_piece_ids
        enemy_moves = path_context.enemy_moves
    else:
        # Fallback: compute inline (original behaviour)
        own_forward_path = set()
        moving_piece_ids = set()
        enemy_moves: list[_EnemyMoveInfo] = []
        for move in active_moves:
            moving_piece_ids.add(move.piece_id)
            moving_piece = board.get_piece_by_id(move.piece_id)
            if moving_piece is None:
                continue
            if moving_piece.player == player:
                forward_squares = _get_forward_path(move, current_tick, ticks_per_square)
                own_forward_path.update(forward_squares)
            elif len(move.path) >= 2:
                e_dr = int(move.path[1][0] - move.path[0][0])
                e_dc = int(move.path[1][1] - move.path[0][1])
                fwd = _get_forward_path(move, current_tick, ticks_per_square)
                enemy_moves.append(
                    _EnemyMoveInfo(
                        dr=e_dr, dc=e_dc,
                        start_r=int(move.path[0][0]),
                        start_c=int(move.path[0][1]),
                        forward_squares=fwd,
                    )
                )

    # ---------- Same-line blocking from enemy moves ----------
    enemy_same_line_path: set[tuple[int, int]] = set()

    # Detect if pawn is moving straight (exactly one axis changes)
    is_pawn_straight = False
    if piece_type == PieceType.PAWN and len(path) >= 2:
        _dr = int(path[1][0] - path[0][0])
        _dc = int(path[1][1] - path[0][1])
        is_pawn_straight = (_dr != 0) != (_dc != 0)  # exactly one axis

    check_same_line = piece_type is not None and len(path) >= 2 and (
        piece_type in _SLIDER_TYPES or is_pawn_straight
    )

    if check_same_line:
        # Compute direction of the proposed move
        my_dr = int(path[1][0] - path[0][0])
        my_dc = int(path[1][1] - path[0][1])
        my_start_r, my_start_c = int(path[0][0]), int(path[0][1])

        for em in enemy_moves:
            # Check if directions are parallel (cross product == 0)
            if my_dr * em.dc != my_dc * em.dr:
                continue

            # Check if on the same geometric line
            diff_r = em.start_r - my_start_r
            diff_c = em.start_c - my_start_c
            if diff_r * my_dc != diff_c * my_dr:
                continue

            # Slider: enemy's forward path blocks us
            if piece_type in _SLIDER_TYPES:
                enemy_same_line_path.update(em.forward_squares)

            # Pawn straight: opposite direction + ahead = guaranteed loss
            if is_pawn_straight:
                if my_dr * em.dr + my_dc * em.dc < 0:  # opposite direction
                    if diff_r * my_dr + diff_c * my_dc > 0:  # enemy is ahead
                        return False

    # ---------- Check intermediate squares (excluding start and destination) ----------
    for row, col in path[1:-1]:
        int_row, int_col = int(row), int(col)

        piece_at = board.get_piece_at(int_row, int_col)
        if piece_at is not None:
            # Check if this piece is currently moving
            if piece_at.id not in moving_piece_ids:
                # Stationary piece blocks
                return False
            # Moving piece: only blocks if it's enemy (can't capture on intermediate)
            # Own moving piece's START position doesn't block (vacated)
            if piece_at.player != player:
                # Enemy moving piece's start position doesn't block us
                pass

        # Check for own moving piece's forward path
        if (int_row, int_col) in own_forward_path:
            return False  # Can't move through own piece's forward path

        # Check for enemy same-line slider blocking
        if (int_row, int_col) in enemy_same_line_path:
            return False

    # ---------- Check destination square ----------
    if len(path) >= 2:
        dest_row, dest_col = path[-1]
        int_row, int_col = int(dest_row), int(dest_col)

        piece_at = board.get_piece_at(int_row, int_col)
        if piece_at is not None:
            if piece_at.id in moving_piece_ids:
                # Moving piece has vacated - square is effectively empty
                # (collision detection handles any mid-path interactions)
                pass
            elif piece_at.player == player:
                # Own stationary piece at destination - blocked
                return False
            # else: enemy stationary piece at destination - capture allowed

        # Check for own moving piece's forward path at destination
        if (int_row, int_col) in own_forward_path:
            return False  # Can't move to own piece's forward path

        # Check for enemy same-line slider blocking at destination
        if (int_row, int_col) in enemy_same_line_path:
            return False

    return True


def _get_forward_path(
    move: Move,
    current_tick: int,
    ticks_per_square: int,
) -> list[tuple[int, int]]:
    """Get the forward path squares for a moving piece (squares not yet reached).

    Returns squares the piece will traverse but hasn't reached yet.
    """
    path = move.path
    if len(path) < 2:
        return []

    elapsed = current_tick - move.start_tick
    if elapsed < 0:
        # Move hasn't started yet - entire path (except start) is forward
        # Skip non-integer coordinates (knight midpoints don't block - knights jump)
        return [
            (int(r), int(c)) for r, c in path[1:]
            if r == int(r) and c == int(c)
        ]

    # Number of segments = len(path) - 1
    num_segments = len(path) - 1
    total_ticks = num_segments * ticks_per_square

    if elapsed >= total_ticks:
        # Move completed - no forward path
        return []

    # Current segment index (which segment we're currently traversing)
    current_segment = elapsed // ticks_per_square

    # Forward path = all squares from current_segment + 1 onwards
    # (the square we're moving toward and all subsequent squares)
    # Skip non-integer coordinates (knight midpoints don't block - knights jump)
    forward_squares = []
    for i in range(current_segment + 1, len(path)):
        r, c = path[i]
        if r == int(r) and c == int(c):
            forward_squares.append((int(r), int(c)))

    return forward_squares


def _is_knight_destination_valid(
    path: list[PathPoint],
    board: Board,
    player: int,
    active_moves: list[Move],
    current_tick: int = 0,
    ticks_per_square: int = 30,
    *,
    path_context: PathClearContext | None = None,
) -> bool:
    """Check if a knight's destination is valid.

    Knights can jump over pieces but cannot land on their own pieces
    (stationary or in forward path).
    """
    # Get destination (last point in path)
    end_row, end_col = path[-1]
    int_row, int_col = int(end_row), int(end_col)

    if path_context is not None:
        moving_piece_ids = path_context.moving_piece_ids
        own_forward_path = path_context.own_forward_path
    else:
        moving_piece_ids = {m.piece_id for m in active_moves}
        own_forward_path = None  # computed lazily below

    # Check piece at destination
    piece_at = board.get_piece_at(int_row, int_col)
    if piece_at is not None:
        if piece_at.id in moving_piece_ids:
            # Moving piece has vacated - square is effectively empty
            pass
        elif piece_at.player == player:
            # Own stationary piece at destination - blocked
            return False
        # else: enemy stationary piece at destination - capture allowed

    # Check for own moving piece's forward path at destination
    if own_forward_path is not None:
        if (int_row, int_col) in own_forward_path:
            return False
    else:
        for move in active_moves:
            moving_piece = board.get_piece_by_id(move.piece_id)
            if moving_piece is not None and moving_piece.player == player:
                forward_squares = _get_forward_path(move, current_tick, ticks_per_square)
                if (int_row, int_col) in forward_squares:
                    return False  # Can't land on own piece's forward path

    return True


def _enemy_slider_blocks_castling_path(
    board: Board,
    player: int,
    active_moves: list[Move],
    current_tick: int,
    ticks_per_square: int,
    fixed_row: int | None,
    fixed_col: int | None,
    range_min: int,
    range_max: int,
) -> bool:
    """Check if an enemy piece moving along the same rank/file blocks the castling path.

    For horizontal castling: fixed_row is set, fixed_col is None.
    For vertical castling: fixed_col is set, fixed_row is None.
    range_min..range_max (exclusive) defines the castling path range.
    """
    for move in active_moves:
        moving_piece = board.get_piece_by_id(move.piece_id)
        if moving_piece is None or moving_piece.player == player:
            continue
        if len(move.path) < 2:
            continue

        e_dr = int(move.path[1][0] - move.path[0][0])
        e_dc = int(move.path[1][1] - move.path[0][1])

        if fixed_row is not None:
            # Horizontal castling path on this row
            # Enemy must be moving horizontally (e_dr == 0) on the same row
            if e_dr != 0:
                continue
            if int(move.path[0][0]) != fixed_row:
                continue
            for r, c in _get_forward_path(move, current_tick, ticks_per_square):
                if r == fixed_row and range_min <= c < range_max:
                    return True
        else:
            # Vertical castling path on this column
            # Enemy must be moving vertically (e_dc == 0) on the same column
            if e_dc != 0:
                continue
            if int(move.path[0][1]) != fixed_col:
                continue
            for r, c in _get_forward_path(move, current_tick, ticks_per_square):
                if c == fixed_col and range_min <= r < range_max:
                    return True

    return False


def check_castling(
    piece: Piece,
    board: Board,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
    cooldowns: list[Cooldown] | None = None,
    current_tick: int = 0,
    ticks_per_square: int = 30,
) -> tuple[Move, Move] | None:
    """Check if this is a valid castling move.

    Returns (king_move, rook_move) if valid castling, None otherwise.

    Castling requirements:
    - King has not moved
    - Rook has not moved
    - Rook is not currently moving
    - Rook is not on cooldown
    - No pieces between king and rook
    - King moves 2 squares toward rook
    """
    if piece.type != PieceType.KING:
        return None

    if piece.moved:
        return None

    if board.board_type == BoardType.STANDARD:
        return _check_castling_standard(
            piece, board, to_row, to_col, active_moves, cooldowns, current_tick, ticks_per_square
        )
    else:
        return _check_castling_4player(
            piece, board, to_row, to_col, active_moves, cooldowns, current_tick, ticks_per_square
        )


def _check_castling_standard(
    piece: Piece,
    board: Board,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
    cooldowns: list[Cooldown] | None,
    current_tick: int,
    ticks_per_square: int = 30,
) -> tuple[Move, Move] | None:
    """Check castling for standard 2-player board (horizontal castling)."""
    from_row, from_col = piece.grid_position

    # King must stay on same row
    if to_row != from_row:
        return None

    # King must move exactly 2 squares
    col_diff = to_col - from_col
    if abs(col_diff) != 2:
        return None

    # Determine rook position based on direction
    if col_diff == 2:  # Kingside castling
        rook_col = 7
        new_rook_col = 5
    else:  # Queenside castling (col_diff == -2)
        rook_col = 0
        new_rook_col = 3

    # Find the rook
    rook = board.get_piece_at(from_row, rook_col)
    if rook is None or rook.type != PieceType.ROOK or rook.player != piece.player:
        logger.debug(f"Castling rejected: rook not found at ({from_row}, {rook_col}) or wrong type/player. rook={rook}")
        return None

    if rook.moved:
        logger.debug(f"Castling rejected: rook {rook.id} has moved={rook.moved}")
        return None

    # Check rook is not currently moving
    if _is_piece_moving(rook.id, active_moves):
        logger.debug(f"Castling rejected: rook {rook.id} is currently moving")
        return None

    # Check rook is not on cooldown
    if cooldowns is not None:
        for cd in cooldowns:
            if cd.piece_id == rook.id and cd.is_active(current_tick):
                logger.debug(f"Castling rejected: rook {rook.id} is on cooldown")
                return None

    # Check path is clear between king and rook
    # A piece that is currently moving has vacated its starting square
    moving_piece_ids = {move.piece_id for move in active_moves}
    start_col = min(from_col, rook_col) + 1
    end_col = max(from_col, rook_col)
    for col in range(start_col, end_col):
        blocking_piece = board.get_piece_at(from_row, col)
        if blocking_piece is not None and blocking_piece.id not in moving_piece_ids:
            logger.debug(f"Castling rejected: path blocked by piece at ({from_row}, {col})")
            return None

    # Check no pieces currently moving INTO the castling path
    for move in active_moves:
        move_end_row, move_end_col = move.end_position
        # Cast to int for proper comparison
        if int(move_end_row) == from_row and start_col <= int(move_end_col) < end_col:
            logger.debug(f"Castling rejected: piece {move.piece_id} moving into castling path")
            return None

    # Check for enemy sliders moving along the same rank (same-line blocking)
    if _enemy_slider_blocks_castling_path(
        board, piece.player, active_moves, current_tick, ticks_per_square,
        fixed_row=from_row, fixed_col=None, range_min=start_col, range_max=end_col,
    ):
        return None

    # Create the moves
    king_path: list[PathPoint] = [(float(from_row), float(from_col))]
    king_step = 1 if col_diff > 0 else -1
    for _ in range(2):
        king_path.append((float(from_row), king_path[-1][1] + king_step))

    # Build rook path with intermediate squares (queenside rook travels 3 squares
    # vs king's 2, so rook takes longer to arrive and enter cooldown)
    rook_path: list[PathPoint] = [(float(from_row), float(rook_col))]
    rook_step = 1 if new_rook_col > rook_col else -1
    rook_distance = abs(new_rook_col - rook_col)
    for _ in range(rook_distance):
        rook_path.append((float(from_row), rook_path[-1][1] + rook_step))

    # Both moves start at tick 0 - the actual start tick will be set by the engine
    king_move = Move(piece_id=piece.id, path=king_path, start_tick=0)
    rook_move = Move(piece_id=rook.id, path=rook_path, start_tick=0)
    king_move.extra_move = rook_move

    return (king_move, rook_move)


def _check_castling_4player(
    piece: Piece,
    board: Board,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
    cooldowns: list[Cooldown] | None,
    current_tick: int,
    ticks_per_square: int = 30,
) -> tuple[Move, Move] | None:
    """Check castling for 4-player board.

    For horizontal players (2, 4): castling is horizontal (same as standard)
    For vertical players (1, 3): castling is vertical
    """
    from_row, from_col = piece.grid_position
    orient = FOUR_PLAYER_ORIENTATIONS.get(piece.player)
    if orient is None:
        return None

    if orient.axis == "row":
        # Horizontal players (2, 4) - castling is horizontal
        return _check_castling_horizontal(
            piece, board, from_row, from_col, to_row, to_col, active_moves, cooldowns, current_tick, ticks_per_square
        )
    else:
        # Vertical players (1, 3) - castling is vertical
        return _check_castling_vertical(
            piece, board, from_row, from_col, to_row, to_col, active_moves, cooldowns, current_tick, ticks_per_square
        )


def _check_castling_horizontal(
    piece: Piece,
    board: Board,
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
    cooldowns: list[Cooldown] | None,
    current_tick: int,
    ticks_per_square: int = 30,
) -> tuple[Move, Move] | None:
    """Check horizontal castling (for players 2 and 4 in 4-player mode)."""
    # King must stay on same row
    if to_row != from_row:
        return None

    col_diff = to_col - from_col
    if abs(col_diff) != 2:
        return None

    # Determine rook column based on player and direction
    # Player 2 (South, row 11): rooks at cols 2 and 9
    # Player 4 (North, row 0): rooks at cols 2 and 9
    if col_diff > 0:  # Moving right
        rook_col = 9
        new_rook_col = to_col - 1
    else:  # Moving left
        rook_col = 2
        new_rook_col = to_col + 1

    rook = board.get_piece_at(from_row, rook_col)
    if rook is None or rook.type != PieceType.ROOK or rook.player != piece.player:
        return None

    if rook.moved:
        return None

    if _is_piece_moving(rook.id, active_moves):
        return None

    if cooldowns is not None:
        for cd in cooldowns:
            if cd.piece_id == rook.id and cd.is_active(current_tick):
                return None

    # Check path is clear (ignore pieces that are currently moving - they've vacated)
    moving_piece_ids = {move.piece_id for move in active_moves}
    start_col = min(from_col, rook_col) + 1
    end_col = max(from_col, rook_col)
    for col in range(start_col, end_col):
        blocking_piece = board.get_piece_at(from_row, col)
        if blocking_piece is not None and blocking_piece.id not in moving_piece_ids:
            return None

    for move in active_moves:
        move_end_row, move_end_col = move.end_position
        if int(move_end_row) == from_row and start_col <= int(move_end_col) < end_col:
            return None

    # Check for enemy sliders moving along the same rank (same-line blocking)
    if _enemy_slider_blocks_castling_path(
        board, piece.player, active_moves, current_tick, ticks_per_square,
        fixed_row=from_row, fixed_col=None, range_min=start_col, range_max=end_col,
    ):
        return None

    # Create moves
    king_path: list[PathPoint] = [(float(from_row), float(from_col))]
    king_step = 1 if col_diff > 0 else -1
    for _ in range(2):
        king_path.append((float(from_row), king_path[-1][1] + king_step))

    # Build rook path with intermediate squares (queenside rook travels 3 squares
    # vs king's 2, so rook takes longer to arrive and enter cooldown)
    rook_path: list[PathPoint] = [(float(from_row), float(rook_col))]
    rook_step = 1 if new_rook_col > rook_col else -1
    rook_distance = abs(new_rook_col - rook_col)
    for _ in range(rook_distance):
        rook_path.append((float(from_row), rook_path[-1][1] + rook_step))

    king_move = Move(piece_id=piece.id, path=king_path, start_tick=0)
    rook_move = Move(piece_id=rook.id, path=rook_path, start_tick=0)
    king_move.extra_move = rook_move

    return (king_move, rook_move)


def _check_castling_vertical(
    piece: Piece,
    board: Board,
    from_row: int,
    from_col: int,
    to_row: int,
    to_col: int,
    active_moves: list[Move],
    cooldowns: list[Cooldown] | None,
    current_tick: int,
    ticks_per_square: int = 30,
) -> tuple[Move, Move] | None:
    """Check vertical castling (for players 1 and 3 in 4-player mode)."""
    # King must stay on same column
    if to_col != from_col:
        return None

    row_diff = to_row - from_row
    if abs(row_diff) != 2:
        return None

    # Determine rook row based on player and direction
    # Player 1 (East, col 11): rooks at rows 2 and 9
    # Player 3 (West, col 0): rooks at rows 2 and 9
    if row_diff > 0:  # Moving down
        rook_row = 9
        new_rook_row = to_row - 1
    else:  # Moving up
        rook_row = 2
        new_rook_row = to_row + 1

    rook = board.get_piece_at(rook_row, from_col)
    if rook is None or rook.type != PieceType.ROOK or rook.player != piece.player:
        return None

    if rook.moved:
        return None

    if _is_piece_moving(rook.id, active_moves):
        return None

    if cooldowns is not None:
        for cd in cooldowns:
            if cd.piece_id == rook.id and cd.is_active(current_tick):
                return None

    # Check path is clear (ignore pieces that are currently moving - they've vacated)
    moving_piece_ids = {move.piece_id for move in active_moves}
    start_row = min(from_row, rook_row) + 1
    end_row = max(from_row, rook_row)
    for row in range(start_row, end_row):
        blocking_piece = board.get_piece_at(row, from_col)
        if blocking_piece is not None and blocking_piece.id not in moving_piece_ids:
            return None

    for move in active_moves:
        move_end_row, move_end_col = move.end_position
        if int(move_end_col) == from_col and start_row <= int(move_end_row) < end_row:
            return None

    # Check for enemy sliders moving along the same file (same-line blocking)
    if _enemy_slider_blocks_castling_path(
        board, piece.player, active_moves, current_tick, ticks_per_square,
        fixed_row=None, fixed_col=from_col, range_min=start_row, range_max=end_row,
    ):
        return None

    # Create moves
    king_path: list[PathPoint] = [(float(from_row), float(from_col))]
    king_step = 1 if row_diff > 0 else -1
    for _ in range(2):
        king_path.append((king_path[-1][0] + king_step, float(from_col)))

    # Build rook path with intermediate squares (long-side rook travels 3 squares
    # vs king's 2, so rook takes longer to arrive and enter cooldown)
    rook_path: list[PathPoint] = [(float(rook_row), float(from_col))]
    rook_step = 1 if new_rook_row > rook_row else -1
    rook_distance = abs(new_rook_row - rook_row)
    for _ in range(rook_distance):
        rook_path.append((rook_path[-1][0] + rook_step, float(from_col)))

    king_move = Move(piece_id=piece.id, path=king_path, start_tick=0)
    rook_move = Move(piece_id=rook.id, path=rook_path, start_tick=0)
    king_move.extra_move = rook_move

    return (king_move, rook_move)

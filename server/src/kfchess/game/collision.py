"""Collision detection for Kung Fu Chess.

Pieces capture each other when they get within a certain distance (0.4 squares)
during movement. The piece that started moving earlier wins the capture.

Special rules:
- Knights only capture at their destination (they jump over pieces)
- Pawns moving straight cannot capture (only diagonal moves can capture)
- In head-on collisions, the piece that started earlier wins
"""

import math
from dataclasses import dataclass

from kfchess.game.moves import Cooldown, Move
from kfchess.game.pieces import Piece, PieceType

# Capture distance threshold (in board squares)
# Two pieces within this distance will result in a capture
CAPTURE_DISTANCE = 0.4


@dataclass
class Capture:
    """Represents a capture event.

    Attributes:
        capturing_piece_id: ID of the piece that made the capture
        captured_piece_id: ID of the piece that was captured
        position: (row, col) where the capture occurred
    """

    capturing_piece_id: str
    captured_piece_id: str
    position: tuple[float, float]


def get_interpolated_position(
    piece: Piece,
    active_moves: list[Move],
    current_tick: int,
    ticks_per_square: int,
) -> tuple[float, float]:
    """Get a piece's interpolated position during movement.

    If the piece is not actively moving, returns its current position.

    Args:
        piece: The piece to get position for
        active_moves: List of currently active moves
        current_tick: Current game tick
        ticks_per_square: Number of ticks to move one square

    Returns:
        (row, col) tuple with interpolated position
    """
    # Find if this piece has an active move
    active_move = None
    for move in active_moves:
        if move.piece_id == piece.id:
            active_move = move
            break

    if active_move is None:
        return (piece.row, piece.col)

    # Calculate position along the path
    ticks_elapsed = current_tick - active_move.start_tick
    if ticks_elapsed < 0:
        return (piece.row, piece.col)

    path = active_move.path
    total_squares = len(path) - 1

    if total_squares == 0:
        return (float(path[0][0]), float(path[0][1]))

    total_ticks = total_squares * ticks_per_square
    if ticks_elapsed >= total_ticks:
        return (float(path[-1][0]), float(path[-1][1]))

    # Calculate which segment of the path we're on
    progress = ticks_elapsed / ticks_per_square
    segment_index = int(progress)
    segment_progress = progress - segment_index

    if segment_index >= total_squares:
        return (float(path[-1][0]), float(path[-1][1]))

    # Interpolate between path points
    start_row, start_col = path[segment_index]
    end_row, end_col = path[segment_index + 1]

    interp_row = start_row + (end_row - start_row) * segment_progress
    interp_col = start_col + (end_col - start_col) * segment_progress

    return (interp_row, interp_col)


def get_knight_position(
    piece: Piece,
    active_moves: list[Move],
    current_tick: int,
    ticks_per_square: int,
) -> tuple[float, float] | None:
    """Get knight's position for collision detection.

    Knights are special: they "jump" and are invisible for the first 85% of
    their move. During the jump, they return None to indicate they're airborne.
    When they become visible at 85%, they can also capture (symmetric behavior).

    Knight move takes 2 * ticks_per_square (path has 3 points: start, mid, end).

    Returns:
        (row, col) if the knight can collide, None if airborne
    """
    # Find if this piece has an active move
    active_move = None
    for move in active_moves:
        if move.piece_id == piece.id:
            active_move = move
            break

    if active_move is None:
        return (piece.row, piece.col)

    ticks_elapsed = current_tick - active_move.start_tick
    if ticks_elapsed < 0:
        return (piece.row, piece.col)

    # Knight move takes 2 segments * ticks_per_square
    total_ticks = 2 * ticks_per_square

    # Knights are airborne (invisible) for first 85% of move
    # This matches the capture threshold so visibility and capture ability are symmetric
    if ticks_elapsed < total_ticks * 0.85:
        return None

    # Last 15%: visible, interpolating toward destination
    if ticks_elapsed >= total_ticks:
        return (float(active_move.path[-1][0]), float(active_move.path[-1][1]))

    # Simple linear interpolation from start to end based on overall progress
    progress = ticks_elapsed / total_ticks
    start_row, start_col = active_move.path[0]
    end_row, end_col = active_move.path[-1]

    interp_row = start_row + (end_row - start_row) * progress
    interp_col = start_col + (end_col - start_col) * progress

    return (interp_row, interp_col)


def can_knight_capture(
    move: Move,
    current_tick: int,
    ticks_per_square: int,
) -> bool:
    """Check if a knight can capture at the current tick.

    Knights can only capture when 85%+ through their move.
    """
    ticks_elapsed = current_tick - move.start_tick
    total_ticks = 2 * ticks_per_square
    progress = ticks_elapsed / total_ticks
    return progress >= 0.85


def detect_collisions(
    pieces: list[Piece],
    active_moves: list[Move],
    current_tick: int,
    ticks_per_square: int,
) -> list[Capture]:
    """Detect all collisions/captures at the current tick.

    Args:
        pieces: All pieces on the board (including captured)
        active_moves: Currently active moves
        current_tick: Current game tick
        ticks_per_square: Ticks to move one square

    Returns:
        List of Capture events that occurred
    """
    captures: list[Capture] = []

    # Get positions for all pieces
    piece_positions: dict[str, tuple[float, float] | None] = {}

    for piece in pieces:
        if piece.captured:
            continue

        if piece.type == PieceType.KNIGHT:
            pos = get_knight_position(piece, active_moves, current_tick, ticks_per_square)
        else:
            pos = get_interpolated_position(piece, active_moves, current_tick, ticks_per_square)

        piece_positions[piece.id] = pos

    # Build lookup for active moves by piece ID
    move_by_piece: dict[str, Move] = {m.piece_id: m for m in active_moves}

    # Check all pairs for collisions
    piece_list = [p for p in pieces if not p.captured]

    for i, piece_a in enumerate(piece_list):
        pos_a = piece_positions.get(piece_a.id)
        if pos_a is None:  # Airborne knight
            continue

        for piece_b in piece_list[i + 1 :]:
            # Same player pieces don't capture each other
            if piece_a.player == piece_b.player:
                continue

            pos_b = piece_positions.get(piece_b.id)
            if pos_b is None:  # Airborne knight
                continue

            # Check distance
            dist = math.sqrt((pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2)
            if dist >= CAPTURE_DISTANCE:
                continue

            # Check if knights can capture (must be 85%+ through their move)
            move_a = move_by_piece.get(piece_a.id)
            move_b = move_by_piece.get(piece_b.id)

            if piece_a.type == PieceType.KNIGHT and move_a is not None:
                if not can_knight_capture(move_a, current_tick, ticks_per_square):
                    continue  # Knight can't capture yet

            if piece_b.type == PieceType.KNIGHT and move_b is not None:
                if not can_knight_capture(move_b, current_tick, ticks_per_square):
                    continue  # Knight can't capture yet

            # Collision detected! Determine winner
            winner, loser = _determine_capture_winner(piece_a, piece_b, move_by_piece)

            collision_pos = ((pos_a[0] + pos_b[0]) / 2, (pos_a[1] + pos_b[1]) / 2)

            if winner and loser:
                captures.append(
                    Capture(
                        capturing_piece_id=winner.id,
                        captured_piece_id=loser.id,
                        position=collision_pos,
                    )
                )
            elif winner is None and loser is None:
                # Mutual destruction - both pieces are captured
                # We create two capture events with no capturing piece
                captures.append(
                    Capture(
                        capturing_piece_id="",  # No winner
                        captured_piece_id=piece_a.id,
                        position=collision_pos,
                    )
                )
                captures.append(
                    Capture(
                        capturing_piece_id="",  # No winner
                        captured_piece_id=piece_b.id,
                        position=collision_pos,
                    )
                )

    return captures


def _determine_capture_winner(
    piece_a: Piece,
    piece_b: Piece,
    move_by_piece: dict[str, Move],
) -> tuple[Piece | None, Piece | None]:
    """Determine which piece wins a collision.

    Rules (from original Kung Fu Chess):
    1. Pawns moving straight cannot capture, but can be captured
    2. Moving pieces capture stationary pieces they run into
    3. If both moving, earlier move start tick wins
    4. If same tick, it's a mutual destruction (both captured)
    5. Special: two pawns moving straight - earlier one survives

    Returns:
        (winner, loser) tuple, or (None, None) for mutual destruction/no capture
    """
    move_a = move_by_piece.get(piece_a.id)
    move_b = move_by_piece.get(piece_b.id)

    # Check pawn moving straight (can't capture)
    a_can_capture = _can_piece_capture(piece_a, move_a)
    b_can_capture = _can_piece_capture(piece_b, move_b)

    # Special case: two pawns moving straight - earlier one survives
    # (neither "captures", but the later one dies from the collision)
    if not a_can_capture and not b_can_capture:
        # Both are pawns moving straight - use timing
        if move_a is not None and move_b is not None:
            if move_a.start_tick < move_b.start_tick:
                return (piece_a, piece_b)  # A survives, B dies
            if move_b.start_tick < move_a.start_tick:
                return (piece_b, piece_a)  # B survives, A dies
            # Same tick - both die
            return (None, None)
        return (None, None)

    # If only one can capture, they win
    if a_can_capture and not b_can_capture:
        return (piece_a, piece_b)
    if b_can_capture and not a_can_capture:
        return (piece_b, piece_a)

    # Both can capture - use timing rules
    a_moving = move_a is not None
    b_moving = move_b is not None

    # Moving piece captures stationary piece
    if a_moving and not b_moving:
        return (piece_a, piece_b)
    if b_moving and not a_moving:
        return (piece_b, piece_a)

    # Both stationary shouldn't happen, but handle it
    if not a_moving and not b_moving:
        return (None, None)

    # Both moving - earlier move wins
    assert move_a is not None and move_b is not None
    if move_a.start_tick < move_b.start_tick:
        return (piece_a, piece_b)
    if move_b.start_tick < move_a.start_tick:
        return (piece_b, piece_a)

    # Same start tick - mutual destruction
    return (None, None)


def _is_pawn_moving_straight(piece: Piece, move: Move | None) -> bool:
    """Check if a pawn is moving straight (forward, not diagonally).

    Returns True only for pawns that are actively moving in a straight line.
    Returns False for:
    - Non-pawn pieces
    - Stationary pawns
    - Pawns moving diagonally
    """
    if piece.type != PieceType.PAWN:
        return False

    if move is None:
        return False

    if len(move.path) < 2:
        return False

    start_col = move.path[0][1]
    end_col = move.path[-1][1]

    # Straight move = same column
    return start_col == end_col


def _can_piece_capture(piece: Piece, move: Move | None) -> bool:
    """Check if a piece can make a capture given its current movement.

    Most pieces can always capture. The exception is pawns moving straight
    (forward) - they cannot capture, only pawns moving diagonally can capture.
    Stationary pieces can capture if an opponent runs into them.
    """
    # Pawns moving straight cannot capture
    if _is_pawn_moving_straight(piece, move):
        return False

    return True


def is_piece_moving(piece_id: str, active_moves: list[Move]) -> bool:
    """Check if a piece is currently moving."""
    return any(m.piece_id == piece_id for m in active_moves)


def is_piece_on_cooldown(
    piece_id: str,
    cooldowns: list[Cooldown],
    current_tick: int,
) -> bool:
    """Check if a piece is on cooldown."""

    for cd in cooldowns:
        if cd.piece_id == piece_id and cd.is_active(current_tick):
            return True
    return False

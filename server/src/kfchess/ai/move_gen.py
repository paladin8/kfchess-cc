"""Candidate move generation for AI."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from kfchess.ai.state_extractor import AIPiece, AIState, PieceStatus
from kfchess.game.engine import GameEngine
from kfchess.game.pieces import PieceType
from kfchess.game.state import GameState

if TYPE_CHECKING:
    from kfchess.ai.arrival_field import ArrivalData


_INF_TRAVEL = 999_999


def compute_travel_ticks(
    from_row: int, from_col: int,
    to_row: int, to_col: int,
    piece_type: PieceType,
    tps: int,
) -> int:
    """Estimate travel time in ticks for a move.

    Returns _INF_TRAVEL if the piece can't reach the target in a single
    move (e.g. rook off-axis, bishop off-diagonal).
    """
    if piece_type == PieceType.KNIGHT:
        # Knights must reach target via L-shape (2+1 or 1+2)
        dr = abs(to_row - from_row)
        dc = abs(to_col - from_col)
        if not ((dr == 2 and dc == 1) or (dr == 1 and dc == 2)):
            return _INF_TRAVEL
        return 2 * tps  # Knights always move 2 segments
    dr = abs(to_row - from_row)
    dc = abs(to_col - from_col)
    if piece_type == PieceType.ROOK:
        if dr != 0 and dc != 0:
            return _INF_TRAVEL  # Rook requires same rank or file
    elif piece_type == PieceType.BISHOP:
        if dr != dc:
            return _INF_TRAVEL  # Bishop requires same diagonal
    elif piece_type == PieceType.KING:
        if dr > 1 or dc > 1:
            return _INF_TRAVEL  # King moves 1 square at a time
    dist = max(dr, dc)
    return dist * tps


class CandidateMove:
    """A candidate move with metadata for scoring."""

    __slots__ = ("piece_id", "to_row", "to_col", "capture_type", "is_evasion", "ai_piece")

    def __init__(
        self,
        piece_id: str,
        to_row: int,
        to_col: int,
        capture_type: PieceType | None = None,
        is_evasion: bool = False,
        ai_piece: AIPiece | None = None,
    ):
        self.piece_id = piece_id
        self.to_row = to_row
        self.to_col = to_col
        self.capture_type = capture_type
        self.is_evasion = is_evasion
        self.ai_piece = ai_piece


class MoveGen:
    """Generates candidate moves for AI evaluation."""

    @staticmethod
    def generate_candidates(
        state: GameState,
        ai_state: AIState,
        ai_player: int,
        max_pieces: int = 2,
        max_candidates_per_piece: int = 4,
        level: int = 1,
        arrival_data: ArrivalData | None = None,
    ) -> list[CandidateMove]:
        """Generate candidate moves for AI.

        Picks up to max_pieces random movable pieces and generates
        up to max_candidates_per_piece for each.

        Args:
            state: Game state for move validation
            ai_state: AI-friendly state
            ai_player: Player number
            max_pieces: Max pieces to consider
            max_candidates_per_piece: Max candidates per piece
            level: AI difficulty level (affects pruning/evasion)
            arrival_data: Arrival fields for margin-based decisions (L2+)

        Returns:
            List of candidate moves
        """
        movable = ai_state.get_movable_pieces()
        if not movable:
            return []

        # Build occupancy map for enemy pieces (for capture detection)
        enemy_positions: dict[tuple[int, int], tuple[PieceType, str]] = {}
        for ep in ai_state.get_enemy_pieces():
            if ep.status != PieceStatus.TRAVELING:
                enemy_positions[ep.piece.grid_position] = (ep.piece.type, ep.piece.id)

        # Get all legal moves once (avoid per-piece brute-force scan)
        all_legal = GameEngine.get_legal_moves_fast(state, ai_player)

        # Group by piece_id
        moves_by_piece: dict[str, list[tuple[int, int]]] = {}
        for piece_id, to_row, to_col in all_legal:
            moves_by_piece.setdefault(piece_id, []).append((to_row, to_col))

        # Prioritize threatened pieces for evasion
        shuffled = list(movable)
        if arrival_data is not None:
            # Sort: threatened pieces first, then shuffle within groups
            threatened = []
            safe = []
            for p in shuffled:
                pos = p.piece.grid_position
                if arrival_data.is_piece_at_risk(
                    pos[0], pos[1], p.cooldown_remaining,
                    is_king=p.piece.type == PieceType.KING,
                ):
                    threatened.append(p)
                else:
                    safe.append(p)
            random.shuffle(threatened)
            random.shuffle(safe)
            shuffled = threatened + safe
        else:
            random.shuffle(shuffled)

        candidates: list[CandidateMove] = []
        pieces_used = 0

        # Always consider the king (king safety) — doesn't count toward budget
        own_king = ai_state.get_own_king()
        king_id: str | None = None
        if own_king is not None and own_king.status == PieceStatus.IDLE:
            king_id = own_king.piece.id
            king_moves = moves_by_piece.get(king_id)
            if king_moves:
                king_candidates = _build_candidates(
                    own_king, king_moves, enemy_positions,
                    level=level, arrival_data=arrival_data,
                )
                king_candidates.sort(key=_move_priority)
                candidates.extend(king_candidates[:max_candidates_per_piece])

        for ai_piece in shuffled:
            if pieces_used >= max_pieces and candidates:
                break

            # Skip king — already handled above
            if ai_piece.piece.id == king_id:
                continue

            piece_moves = moves_by_piece.get(ai_piece.piece.id)
            if not piece_moves:
                continue

            pieces_used += 1
            piece_candidates = _build_candidates(
                ai_piece, piece_moves, enemy_positions,
                level=level, arrival_data=arrival_data,
            )
            # Prioritize: captures, evasions, positional
            piece_candidates.sort(key=_move_priority)
            candidates.extend(piece_candidates[:max_candidates_per_piece])

        return candidates


def _move_priority(c: CandidateMove) -> int:
    """Lower = higher priority for candidate selection."""
    if c.capture_type is not None:
        return 0
    if c.is_evasion:
        return 1
    return 2


def _build_candidates(
    ai_piece: AIPiece,
    moves: list[tuple[int, int]],
    enemy_positions: dict[tuple[int, int], tuple[PieceType, str]],
    level: int = 1,
    arrival_data: ArrivalData | None = None,
) -> list[CandidateMove]:
    """Build candidate moves for a piece with capture/evasion metadata."""
    piece_id = ai_piece.piece.id
    candidates: list[CandidateMove] = []

    # Check if this piece is threatened
    piece_threatened = False
    if arrival_data is not None:
        pos = ai_piece.piece.grid_position
        piece_threatened = arrival_data.is_piece_at_risk(
            pos[0], pos[1], ai_piece.cooldown_remaining,
            is_king=ai_piece.piece.type == PieceType.KING,
        )

    for to_row, to_col in moves:
        dest = (to_row, to_col)

        # Compute travel time and safety for pruning/evasion
        travel = 0
        safety = 0
        if arrival_data is not None:
            travel = compute_travel_ticks(
                ai_piece.piece.grid_position[0],
                ai_piece.piece.grid_position[1],
                to_row, to_col,
                ai_piece.piece.type,
                arrival_data.tps,
            )
            from_pos = ai_piece.piece.grid_position
            safety = arrival_data.post_arrival_safety(
                to_row, to_col, travel, moving_from=from_pos,
            )
            # Prune very unsafe non-capture moves (pawns exempt — eval
            # handles their safety with a discount and support check)
            if (
                dest not in enemy_positions
                and safety < -(arrival_data.cd_ticks // 2)
                and ai_piece.piece.type != PieceType.PAWN
            ):
                continue

        is_capture = dest in enemy_positions
        cap_type: PieceType | None = None
        is_evasion = False

        if is_capture:
            cap_type, _ = enemy_positions[dest]

        if piece_threatened:
            # For captures, recompute safety excluding the captured piece
            effective_safety = safety
            if is_capture and arrival_data is not None:
                _, cap_id = enemy_positions[dest]
                effective_safety = arrival_data.post_arrival_safety(
                    to_row, to_col, travel,
                    exclude_piece_id=cap_id,
                    moving_from=ai_piece.piece.grid_position,
                )
            if effective_safety >= 0:
                is_evasion = True

        candidates.append(
            CandidateMove(
                piece_id=piece_id,
                to_row=to_row,
                to_col=to_col,
                capture_type=cap_type,
                is_evasion=is_evasion,
                ai_piece=ai_piece,
            )
        )

    return candidates

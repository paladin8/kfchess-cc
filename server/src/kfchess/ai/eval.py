"""Evaluation function for scoring candidate moves."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from kfchess.ai.move_gen import CandidateMove
from kfchess.ai.state_extractor import AIState
from kfchess.ai.tactics import (
    PIECE_VALUES,
    capture_value,
    dodge_probability,
    king_blocking_bonus,
    king_exposure_penalty,
    king_threat_capture_bonus,
    move_safety,
    recapture_bonus,
    threaten_score,
)
from kfchess.game.pieces import PieceType

if TYPE_CHECKING:
    from kfchess.ai.arrival_field import ArrivalData

# Scoring weights for Level 1
MATERIAL_WEIGHT = 10.0
CENTER_CONTROL_WEIGHT = 1.0
DEVELOPMENT_WEIGHT = 0.8
PAWN_ADVANCE_WEIGHT = 1.0

# Level 2 weights
SAFETY_WEIGHT = MATERIAL_WEIGHT
COMMITMENT_WEIGHT = 0.15
EVASION_WEIGHT = MATERIAL_WEIGHT  # Saving a piece ≈ capturing one of equal value
THREATEN_WEIGHT = 0.1 * MATERIAL_WEIGHT

# Level 3 weights
DODGE_FAILURE_COST = 0.9  # Fraction of our piece value lost if target dodges
RECAPTURE_WEIGHT = 0.4 * MATERIAL_WEIGHT
KING_THREAT_CAPTURE_WEIGHT = 0.5 * MATERIAL_WEIGHT

# Development urgency (opening phase)
DEVELOPMENT_URGENCY_SCALE = 3.0  # At full urgency, dev weight: 0.8 * (1+3) = 3.2
PAWN_ADVANCE_URGENCY_DAMPEN = 0.5  # At full urgency, pawn advance weight: 1.5 * 0.5
FIRST_MOVE_BONUS = 1.0  # Bonus for moving an undeveloped minor piece for the first time

# Pawn structure
PAWN_CHAIN_BONUS = 0.8  # Per supporting pawn diagonal adjacency
ISOLATED_PAWN_PENALTY = 0.5  # Penalty for pawn with no friendly pawns on adjacent files

# Selection weights by rank position per level.
# The AI picks a move from the sorted list using these as relative weights.
# Weights are extended geometrically for candidates beyond the list length.
SELECTION_WEIGHTS_BY_LEVEL: dict[int, list[float]] = {
    1: [30, 25, 20, 15, 5, 5],
    2: [50, 20, 15, 5, 5, 5],
    3: [75, 15, 5, 3, 2],
}


class Eval:
    """Scores candidate moves for AI selection."""

    @staticmethod
    def score_candidates(
        candidates: list[CandidateMove],
        ai_state: AIState,
        noise: bool = True,
        level: int = 1,
        arrival_data: ArrivalData | None = None,
    ) -> list[tuple[CandidateMove, float]]:
        """Score all candidate moves and return sorted (best first).

        When noise is enabled, the list is reordered by weighted random
        selection: higher-ranked moves are more likely to be picked first,
        with the distribution controlled by SELECTION_WEIGHTS_BY_LEVEL.

        Args:
            candidates: Moves to score
            ai_state: AI state snapshot
            noise: Whether to apply weighted selection (imperfection)
            level: AI difficulty level (affects scoring terms)
            arrival_data: Arrival fields for margin-based scoring (L2+)

        Returns:
            List of (move, score) sorted by selection order (best first)
        """
        if not candidates:
            return []

        center_r = ai_state.board_height / 2.0
        center_c = ai_state.board_width / 2.0
        max_dist = _euclidean_distance((0, 0), (center_r, center_c))
        tps = ai_state.speed_config.ticks_per_square if ai_state.speed_config else 30

        # Pre-compute development urgency and pawn structure data
        dev_urgency = _compute_development_urgency(ai_state)
        pawn_positions, pawn_files = _compute_pawn_data(ai_state)

        scored: list[tuple[CandidateMove, float]] = []
        for candidate in candidates:
            score = _score_move(
                candidate, ai_state,
                center_r, center_c, max_dist,
                level=level, arrival_data=arrival_data, tps=tps,
                development_urgency=dev_urgency,
                friendly_pawn_positions=pawn_positions,
                friendly_pawn_files=pawn_files,
            )
            scored.append((candidate, score))

        # Sort deterministically by score (best first)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Apply weighted selection to reorder
        if noise and len(scored) > 1:
            scored = _weighted_select(scored, level)

        return scored


def _weighted_select(
    scored: list[tuple[CandidateMove, float]],
    level: int,
) -> list[tuple[CandidateMove, float]]:
    """Select a move from the top candidates using rank-based weights.

    Only considers the top N candidates where N is the length of the
    weight list for this level. Picks one move using weighted random
    selection, then returns the full list reordered with the pick first.
    """
    weights = SELECTION_WEIGHTS_BY_LEVEL.get(level, [50, 20, 15, 5, 5, 5])
    max_choices = len(weights)
    top = scored[:max_choices]

    w = weights[:len(top)]
    chosen = random.choices(top, weights=w, k=1)[0]

    # Put chosen first, then the rest in original score order
    result = [chosen]
    for item in scored:
        if item is not chosen:
            result.append(item)
    return result


def _score_move(
    candidate: CandidateMove,
    ai_state: AIState,
    center_r: float,
    center_c: float,
    max_dist: float,
    level: int = 1,
    arrival_data: ArrivalData | None = None,
    tps: int = 30,
    development_urgency: float = 0.0,
    friendly_pawn_positions: set[tuple[int, int]] | None = None,
    friendly_pawn_files: set[int] | None = None,
) -> float:
    """Compute deterministic score for a move."""
    score = 0.0
    dest = (candidate.to_row, candidate.to_col)

    # Material: value of captured piece
    if candidate.capture_type:
        net_capture = capture_value(candidate, ai_state)

        if level >= 3 and arrival_data is not None:
            # EV framework: account for dodge probability
            p = dodge_probability(candidate, ai_state, arrival_data)
            our_value = PIECE_VALUES.get(
                candidate.ai_piece.piece.type, 1.0,
            ) if candidate.ai_piece else 1.0
            # If dodged: we land on empty square on cooldown, likely lose our piece
            fail_value = -our_value * DODGE_FAILURE_COST
            ev = (1.0 - p) * net_capture + p * fail_value
            score += ev * MATERIAL_WEIGHT
        else:
            score += net_capture * MATERIAL_WEIGHT

    # Evasion bonus: scale by piece value (saving a queen >> saving a pawn)
    if candidate.is_evasion and candidate.ai_piece is not None:
        evading_value = PIECE_VALUES.get(candidate.ai_piece.piece.type, 1.0)
        score += evading_value * EVASION_WEIGHT

    ai_piece = candidate.ai_piece
    if ai_piece is not None:
        piece = ai_piece.piece

        # Development: bonus for moving pieces off back rank
        # Scaled by urgency — much stronger when pieces are undeveloped
        if piece.type in (PieceType.KNIGHT, PieceType.BISHOP, PieceType.QUEEN):
            if _is_on_back_ranks(piece.grid_position, ai_state):
                urgency_multiplier = 1.0 + DEVELOPMENT_URGENCY_SCALE * development_urgency
                score += DEVELOPMENT_WEIGHT * urgency_multiplier
            # First-move bonus: prefer developing a new piece over shuffling
            if not piece.moved:
                score += FIRST_MOVE_BONUS

        # Pawn advancement: reward pawns moving toward promotion
        # Dampened during opening to prioritize piece development
        if piece.type == PieceType.PAWN:
            advancement = _pawn_advancement(
                candidate.to_row, candidate.to_col, ai_state,
            )
            dampen = 1.0 - PAWN_ADVANCE_URGENCY_DAMPEN * development_urgency
            score += advancement * PAWN_ADVANCE_WEIGHT * dampen

            # Pawn structure: chain bonus and isolated penalty
            if friendly_pawn_positions is not None and friendly_pawn_files is not None:
                # Exclude mover's origin to avoid self-support on diagonal moves
                origin = piece.grid_position
                pawn_pos = friendly_pawn_positions - {origin} if origin in friendly_pawn_positions else friendly_pawn_positions
                support = _count_pawn_support(
                    candidate.to_row, candidate.to_col, ai_state, pawn_pos,
                )
                score += support * PAWN_CHAIN_BONUS
                pawn_file = _get_pawn_file(candidate.to_row, candidate.to_col, ai_state)
                if _is_isolated_pawn(pawn_file, friendly_pawn_files):
                    score -= ISOLATED_PAWN_PENALTY

        # King safety applies at ALL levels — never walk into danger
        if arrival_data is not None and piece.type == PieceType.KING and level < 2:
            king_safety = move_safety(candidate, ai_state, arrival_data)
            score += king_safety * SAFETY_WEIGHT

        # Safety: expected material loss from recapture (L2+)
        if arrival_data is not None and level >= 2:
            safety_cost = move_safety(candidate, ai_state, arrival_data)

            # Pawns: discount safety to 25%, skip entirely if supported.
            # Exception: if a traveling enemy is committed to passing through
            # this square, the capture is guaranteed — no discount.
            if piece.type == PieceType.PAWN and safety_cost < 0:
                if not arrival_data.has_traveling_threat(
                    candidate.to_row, candidate.to_col,
                ):
                    recapture_time = arrival_data.get_our_time_excluding(
                        candidate.to_row, candidate.to_col, piece.id,
                    )
                    if recapture_time <= arrival_data.cd_ticks + arrival_data.reaction_ticks:
                        safety_cost = 0.0  # Supported — friendly piece can recapture
                    else:
                        safety_cost *= 0.25

            score += safety_cost * SAFETY_WEIGHT

            # King exposure: penalize moving pieces that shield the king
            score += king_exposure_penalty(candidate, ai_state, arrival_data)

            # King blocking: bonus for interposing a piece to block a slider threat
            score += king_blocking_bonus(candidate, ai_state, arrival_data)

            # King threat capture: bonus for capturing pieces threatening our king
            if candidate.capture_type is not None:
                score += king_threat_capture_bonus(candidate, ai_state, arrival_data) * KING_THREAT_CAPTURE_WEIGHT

            # Commitment penalty: penalize long-distance moves (non-captures)
            if candidate.capture_type is None:
                from_pos = piece.grid_position
                travel_dist = _chebyshev_distance(from_pos, dest)
                commitment = travel_dist * COMMITMENT_WEIGHT
                score -= commitment

        # Level 3: threat bonus + recapture positioning
        if arrival_data is not None and level >= 3:
            # Threat bonus: value of best enemy piece we safely threaten
            score += threaten_score(candidate, ai_state, arrival_data) * THREATEN_WEIGHT
            score += recapture_bonus(candidate, ai_state, arrival_data) * RECAPTURE_WEIGHT

    # Center control
    dist_to_center = _euclidean_distance(dest, (center_r, center_c))
    center_bonus = (1.0 - dist_to_center / max_dist) * CENTER_CONTROL_WEIGHT
    score += center_bonus

    return score


def _chebyshev_distance(
    a: tuple[int, int] | tuple[float, float],
    b: tuple[int, int] | tuple[float, float],
) -> float:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _euclidean_distance(
    a: tuple[int, int] | tuple[float, float],
    b: tuple[int, int] | tuple[float, float],
) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


# Back rank positions per player. 2-player: row-based. 4-player: mixed.
_BACK_RANKS: dict[int, tuple[str, int]] = {
    1: ("row", 7),   # 2P: bottom row; 4P: uses col 11, handled by board_width check
    2: ("row", 0),   # 2P: top row; 4P: uses row 11
    3: ("col", 0),   # 4P only: left col
    4: ("row", 0),   # 4P only: top row
}


def _is_on_back_ranks(
    pos: tuple[int, int], ai_state: AIState,
) -> bool:
    """Check if a piece is on its player's back two ranks."""
    player = ai_state.ai_player
    is_4p = ai_state.board_width > 8
    if is_4p:
        if player == 1:
            return pos[1] >= 10  # East: col 10-11
        elif player == 2:
            return pos[0] >= 10  # South: row 10-11
        elif player == 3:
            return pos[1] <= 1   # West: col 0-1
        elif player == 4:
            return pos[0] <= 1   # North: row 0-1
    else:
        if player == 1:
            return pos[0] >= 6   # rows 6-7
        elif player == 2:
            return pos[0] <= 1   # rows 0-1
    return False


def _pawn_advancement(
    to_row: int, to_col: int, ai_state: AIState,
) -> float:
    """Compute how advanced a pawn destination is (0 = home, higher = closer to promotion)."""
    player = ai_state.ai_player
    is_4p = ai_state.board_width > 8
    if is_4p:
        if player == 1:
            return 11 - to_col  # East→left: higher col = less advanced
        elif player == 2:
            return 11 - to_row  # South→up
        elif player == 3:
            return to_col        # West→right
        elif player == 4:
            return to_row        # North→down
    else:
        if player == 1:
            return 7 - to_row   # Bottom→up
        elif player == 2:
            return to_row        # Top→down
    return 0.0


def _compute_development_urgency(ai_state: AIState) -> float:
    """Compute how urgently pieces need development (0.0-1.0).

    Returns ratio of undeveloped (on back rank) pieces to total developable pieces.
    """
    total_minor = 0
    undeveloped = 0
    for ap in ai_state.get_own_pieces():
        if ap.piece.type in (PieceType.KNIGHT, PieceType.BISHOP, PieceType.QUEEN):
            total_minor += 1
            if _is_on_back_ranks(ap.piece.grid_position, ai_state):
                undeveloped += 1
    if total_minor == 0:
        return 0.0
    return undeveloped / total_minor


def _compute_pawn_data(
    ai_state: AIState,
) -> tuple[set[tuple[int, int]], set[int]]:
    """Compute friendly pawn positions and file set.

    Returns:
        (pawn_positions, pawn_files) where pawn_files uses the axis
        perpendicular to the pawn's advance direction.
    """
    positions: set[tuple[int, int]] = set()
    files: set[int] = set()
    for ap in ai_state.get_own_pieces():
        if ap.piece.type == PieceType.PAWN:
            pos = ap.piece.grid_position
            positions.add(pos)
            files.add(_get_pawn_file(pos[0], pos[1], ai_state))
    return positions, files


def _get_pawn_file(row: int, col: int, ai_state: AIState) -> int:
    """Get the 'file' for a pawn — the axis perpendicular to advance direction."""
    player = ai_state.ai_player
    is_4p = ai_state.board_width > 8
    if is_4p:
        if player in (1, 3):
            return row  # E/W advance along columns, file = row
        return col  # N/S advance along rows, file = col
    return col  # 2P: file = column


def _count_pawn_support(
    to_row: int, to_col: int, ai_state: AIState,
    friendly_pawn_positions: set[tuple[int, int]],
) -> int:
    """Count friendly pawns diagonally supporting a destination square.

    Checks the two diagonal-backward squares (where supporting pawns sit
    in a pawn chain).
    """
    player = ai_state.ai_player
    is_4p = ai_state.board_width > 8
    # Determine backward direction (opposite of advance)
    if is_4p:
        if player == 1:
            deltas = [(1, 1), (-1, 1)]   # East advances left (col-), backward = col+
        elif player == 2:
            deltas = [(1, 1), (1, -1)]   # South advances up (row-), backward = row+
        elif player == 3:
            deltas = [(1, -1), (-1, -1)]  # West advances right (col+), backward = col-
        else:
            deltas = [(-1, 1), (-1, -1)]  # North advances down (row+), backward = row-
    else:
        if player == 1:
            deltas = [(1, -1), (1, 1)]  # Bottom→up, backward = row+1
        else:
            deltas = [(-1, -1), (-1, 1)]  # Top→down, backward = row-1

    count = 0
    for dr, dc in deltas:
        if (to_row + dr, to_col + dc) in friendly_pawn_positions:
            count += 1
    return count


def _is_isolated_pawn(pawn_file: int, friendly_pawn_files: set[int]) -> bool:
    """Check if a pawn is isolated (no friendly pawns on adjacent files)."""
    return (pawn_file - 1) not in friendly_pawn_files and (pawn_file + 1) not in friendly_pawn_files

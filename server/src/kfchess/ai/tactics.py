"""Tactical filters for AI move validation.

Validates captures and positional moves using post-arrival safety
analysis, ensuring the AI accounts for cooldown vulnerability.
"""

from kfchess.ai.arrival_field import ArrivalData, _piece_arrival_time
from kfchess.ai.move_gen import CandidateMove, compute_travel_ticks
from kfchess.ai.state_extractor import AIPiece, AIState, PieceStatus
from kfchess.game.pieces import PieceType
from kfchess.game.state import TICK_RATE_HZ

# Piece values for exchange evaluation
PIECE_VALUES: dict[PieceType, float] = {
    PieceType.PAWN: 1.0,
    PieceType.KNIGHT: 3.0,
    PieceType.BISHOP: 3.0,
    PieceType.ROOK: 5.0,
    PieceType.QUEEN: 9.0,
    PieceType.KING: 20.0,  # Base value; game-ending bonus applied separately
}

# Bonus for capturing the last enemy king (wins the game)
GAME_ENDING_KING_BONUS = 80.0  # Total effective = (20 + 80) * 10 = 1000


def capture_value(
    candidate: CandidateMove,
    ai_state: AIState | None = None,
) -> float:
    """Evaluate the raw material value of a capture.

    Returns the captured piece value. Post-arrival safety (recapture
    risk) is handled separately by move_safety in the eval layer.

    For king captures, adds GAME_ENDING_KING_BONUS if this is the last
    enemy king (capturing it wins the game).

    Non-capture moves return 0.0.
    """
    if candidate.capture_type is None:
        return 0.0

    base_value = PIECE_VALUES.get(candidate.capture_type, 0)

    # Check for game-ending king capture
    if candidate.capture_type == PieceType.KING and ai_state is not None:
        # Count enemy kings that are not captured
        enemy_kings = sum(
            1 for ep in ai_state.get_enemy_pieces()
            if ep.piece.type == PieceType.KING and not ep.piece.captured
        )
        # If only 1 enemy king left, capturing it wins
        if enemy_kings == 1:
            base_value += GAME_ENDING_KING_BONUS

    return base_value


def king_threat_capture_bonus(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Bonus for capturing an enemy piece that threatens our king.

    Returns the king's base piece value (20.0) if the captured piece can
    reach our king. Applied with KING_THREAT_CAPTURE_WEIGHT in eval.

    Returns 0.0 for non-captures or if the captured piece can't reach
    the king.
    """
    if candidate.capture_type is None:
        return 0.0

    own_king = ai_state.get_own_king()
    if own_king is None:
        return 0.0

    king_pos = own_king.piece.grid_position

    # Find the captured piece's ID
    dest = (candidate.to_row, candidate.to_col)
    captured_id: str | None = None
    for ep in ai_state.get_enemy_pieces():
        if ep.piece.grid_position == dest:
            captured_id = ep.piece.id
            break
    if captured_id is None:
        return 0.0

    # Check if this piece can reach our king at all
    piece_times = arrival_data.enemy_time_by_piece.get(captured_id, {})
    enemy_t = piece_times.get(king_pos, 999_999)

    if enemy_t >= 999_999:
        return 0.0  # Can't reach king — no threat

    return PIECE_VALUES[PieceType.KING]


def _king_threat_severity(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
    enemy_t: int,
) -> float | None:
    """Compute threat severity for a given enemy arrival time at the king.

    Shared helper for king_exposure_penalty and king_blocking_bonus.
    Returns 0.0–1.0 indicating how imminent the threat is, or None
    if the candidate should be skipped (king move, no ai_piece, etc.).
    """
    if candidate.ai_piece is None:
        return None

    if candidate.ai_piece.piece.type == PieceType.KING:
        return None

    own_king = ai_state.get_own_king()
    if own_king is None:
        return None

    king_cd = own_king.cooldown_remaining
    escape_time = king_cd + arrival_data.reaction_ticks + arrival_data.tps
    margin = enemy_t - escape_time

    if margin >= TICK_RATE_HZ:
        return 0.0  # King has plenty of time

    return max(0.0, min(1.0, 1.0 - margin / TICK_RATE_HZ))


def king_exposure_penalty(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Penalty for exposing the king by moving a defending piece.

    Checks whether vacating this piece's square unblocks an enemy attack
    line to our king. Returns a negative value scaled by threat imminence.
    """
    own_king = ai_state.get_own_king()
    if own_king is None:
        return 0.0

    king_pos = own_king.piece.grid_position
    from_pos = candidate.ai_piece.piece.grid_position if candidate.ai_piece else None
    if from_pos is None:
        return 0.0

    enemy_t_after = arrival_data._recompute_enemy_time(
        king_pos[0], king_pos[1], from_pos,
    )

    severity = _king_threat_severity(
        candidate, ai_state, arrival_data, enemy_t_after,
    )
    if not severity:
        return 0.0

    king_value = PIECE_VALUES[PieceType.KING] + GAME_ENDING_KING_BONUS
    return -severity * king_value


def king_blocking_bonus(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Bonus for interposing a piece to block a slider's attack on our king.

    Evaluates the post-vacate state (after the piece leaves its origin)
    to detect threats, then checks if landing at the destination blocks
    them. This correctly handles re-blocking (moving from one blocking
    position to another on the same attack line).
    """
    if candidate.ai_piece is None or candidate.ai_piece.piece.type == PieceType.KING:
        return 0.0

    # Skip captures — they remove the threat, handled by king_threat_capture_bonus
    if candidate.capture_type is not None:
        return 0.0

    own_king = ai_state.get_own_king()
    if own_king is None:
        return 0.0

    king_pos = own_king.piece.grid_position
    from_pos = candidate.ai_piece.piece.grid_position
    dest = (candidate.to_row, candidate.to_col)

    # Evaluate the post-vacate state: what's the threat after this piece
    # leaves its current square? This catches re-blocking scenarios where
    # the piece is currently shielding the king.
    enemy_t_vacated = arrival_data._recompute_enemy_time(
        king_pos[0], king_pos[1], from_pos,
    )

    severity = _king_threat_severity(
        candidate, ai_state, arrival_data, enemy_t_vacated,
    )
    if not severity:
        return 0.0

    # Check if landing at the destination blocks the threat
    enemy_t_moved = arrival_data._recompute_enemy_time(
        king_pos[0], king_pos[1], from_pos, blocked_pos=dest,
    )
    if enemy_t_moved <= enemy_t_vacated:
        return 0.0  # No improvement from this block

    king_value = PIECE_VALUES[PieceType.KING] + GAME_ENDING_KING_BONUS
    return severity * king_value


def dodge_probability(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Estimate probability (0.0–1.0) that the target dodges this capture.

    Factors:
    - Dodge window: how many ticks the target has to react and move
    - Escape squares: whether the target has legal moves
    - Knight stealth: knights are invisible for 85% of travel

    Returns 0.0 if target can't dodge, up to 1.0 if easily dodged.
    Only meaningful for CAPTURE moves.
    """
    if candidate.capture_type is None:
        return 0.0

    if candidate.ai_piece is None:
        return 0.0

    dest = (candidate.to_row, candidate.to_col)
    tps = arrival_data.tps

    # Find the target piece
    target: AIPiece | None = None
    for ep in ai_state.get_enemy_pieces():
        if ep.piece.grid_position == dest:
            target = ep
            break

    if target is None:
        return 0.0

    # Traveling targets aren't at their grid position — skip
    if target.status == PieceStatus.TRAVELING:
        return 0.0

    # Our travel time to the target
    from_pos = candidate.ai_piece.piece.grid_position
    our_arrival_ticks = compute_travel_ticks(
        from_pos[0], from_pos[1],
        dest[0], dest[1],
        candidate.ai_piece.piece.type,
        tps,
    )

    # Target can dodge if cooldown expires + reaction before we arrive
    dodge_start = target.cooldown_remaining + arrival_data.reaction_ticks
    if dodge_start >= our_arrival_ticks:
        # Target can't move before we arrive — no dodge possible
        return 0.0

    # Count escape moves that actually dodge the attack.
    # Moving along the attack ray doesn't dodge — the attacker will
    # still collide with the target on its path.
    all_escapes = ai_state.enemy_escape_moves.get(target.piece.id, [])
    if not all_escapes:
        return 0.0

    from_pos = candidate.ai_piece.piece.grid_position
    attack_dr = dest[0] - from_pos[0]
    attack_dc = dest[1] - from_pos[1]

    dodge_count = 0
    for er, ec in all_escapes:
        escape_dr = er - dest[0]
        escape_dc = ec - dest[1]
        if _is_along_attack_ray(escape_dr, escape_dc, attack_dr, attack_dc):
            continue  # Moving along attack path — still gets captured
        dodge_count += 1

    if dodge_count == 0:
        return 0.0

    # Dodge window: how many ticks the target has to escape
    # Normalize by 2*tps (time to traverse 2 squares) so the factor
    # scales with game speed rather than using a fixed constant.
    dodge_window = our_arrival_ticks - dodge_start
    time_factor = min(1.0, dodge_window / (2 * tps))

    # More dodge squares = easier to dodge (maxes at 2)
    escape_factor = min(1.0, dodge_count / 2.0)

    return time_factor * escape_factor


def _is_along_attack_ray(
    escape_dr: int, escape_dc: int,
    attack_dr: int, attack_dc: int,
) -> bool:
    """Check if an escape direction is along the attack ray.

    An escape move is "along the ray" if it moves in the same direction
    as the attack (i.e., the target runs away but stays on the attack
    line, so the attacker still collides on the way through).
    """
    if escape_dr == 0 and escape_dc == 0:
        return True  # Staying put (shouldn't happen, but safe)

    # Normalize attack direction to unit steps
    if attack_dr != 0 or attack_dc != 0:
        # For sliders: attack is along a line (dr/dc are proportional)
        # Normalize to sign only
        a_r = (1 if attack_dr > 0 else -1) if attack_dr != 0 else 0
        a_c = (1 if attack_dc > 0 else -1) if attack_dc != 0 else 0

        e_r = (1 if escape_dr > 0 else -1) if escape_dr != 0 else 0
        e_c = (1 if escape_dc > 0 else -1) if escape_dc != 0 else 0

        # Escape is along the ray if it's in the same direction as the attack
        # (target moves away from attacker but stays on the line)
        return e_r == a_r and e_c == a_c

    return False


def recapture_bonus(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Compute bonus for setting up recapture against incoming enemy attacks.

    When an enemy piece is traveling toward one of our pieces (likely
    capture), rewards moves that position us to recapture the attacker
    after it lands and enters cooldown.

    Returns the max enemy attacker value we can recapture, or 0.0.
    """
    if candidate.ai_piece is None:
        return 0.0

    dest = (candidate.to_row, candidate.to_col)
    tps = arrival_data.tps
    cd_ticks = arrival_data.cd_ticks
    board_w = ai_state.board_width
    board_h = ai_state.board_height

    # Build set of own piece positions for quick lookup
    own_positions: dict[tuple[int, int], AIPiece] = {}
    for op in ai_state.get_own_pieces():
        if op.status != PieceStatus.TRAVELING and not op.piece.captured:
            own_positions[op.piece.grid_position] = op

    # Find traveling enemy pieces heading toward our pieces
    best_recapture = 0.0

    for ep in ai_state.get_enemy_pieces():
        if ep.status != PieceStatus.TRAVELING or ep.travel_direction is None:
            continue

        dr, dc = ep.travel_direction
        pr, pc = ep.current_position

        # Project along travel ray to find which of our pieces they target
        target_pos: tuple[int, int] | None = None
        travel_dist = 0
        for dist in range(1, max(board_w, board_h)):
            sr = int(round(pr + dr * dist))
            sc = int(round(pc + dc * dist))
            if sr < 0 or sr >= board_h or sc < 0 or sc >= board_w:
                break
            sq = (sr, sc)
            if sq in own_positions:
                target_pos = sq
                travel_dist = dist
                break

        if target_pos is None:
            continue  # Not heading toward any of our pieces

        # Enemy will land at target_pos after travel_dist squares,
        # then be on cooldown for cd_ticks
        enemy_remaining_travel = travel_dist * tps
        # Enemy is vulnerable from landing until cooldown + reaction expires
        enemy_vulnerable_until = enemy_remaining_travel + cd_ticks + arrival_data.reaction_ticks

        # Can we recapture? Move to dest, cooldown, then travel to target_pos
        from_pos = candidate.ai_piece.piece.grid_position
        our_travel_to_dest = compute_travel_ticks(
            from_pos[0], from_pos[1],
            dest[0], dest[1],
            candidate.ai_piece.piece.type,
            tps,
        )
        recapture_travel = compute_travel_ticks(
            dest[0], dest[1],
            target_pos[0], target_pos[1],
            candidate.ai_piece.piece.type,
            tps,
        )
        # Total time: travel to dest + our cooldown + reaction + travel to target
        our_recapture_arrival = (
            our_travel_to_dest + cd_ticks + arrival_data.reaction_ticks
            + recapture_travel
        )

        if our_recapture_arrival < enemy_vulnerable_until:
            attacker_value = PIECE_VALUES.get(ep.piece.type, 0)
            if attacker_value > best_recapture:
                best_recapture = attacker_value

    return best_recapture


def move_safety(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Compute expected safety cost for landing on a square.

    Returns a value <= 0 representing the expected material loss from
    recapture. Uses the post-arrival safety margin to estimate recapture
    probability: negative margin → 100%, scaling to 0% at TICK_RATE_HZ.

    For captures, the captured piece is excluded from enemy arrival times.
    """
    if candidate.ai_piece is None:
        return 0.0

    dest = (candidate.to_row, candidate.to_col)
    piece_type = candidate.ai_piece.piece.type
    our_value = PIECE_VALUES.get(piece_type, 0)

    # King moves to threatened squares lose the game — use full game-ending value
    if piece_type == PieceType.KING:
        our_value += GAME_ENDING_KING_BONUS

    # Find captured piece ID for exclusion
    exclude_id: str | None = None
    if candidate.capture_type is not None:
        for ep in ai_state.get_enemy_pieces():
            if ep.piece.grid_position == dest:
                exclude_id = ep.piece.id
                break

    from_pos = candidate.ai_piece.piece.grid_position
    travel_ticks = compute_travel_ticks(
        from_pos[0], from_pos[1],
        dest[0], dest[1],
        candidate.ai_piece.piece.type,
        arrival_data.tps,
    )

    margin = arrival_data.post_arrival_safety(
        dest[0], dest[1], travel_ticks,
        exclude_piece_id=exclude_id,
        moving_from=from_pos,
    )

    if margin >= TICK_RATE_HZ:
        return 0.0  # Safe — no recapture risk

    # Linear interpolation: margin <= 0 → p=1.0, margin = TICK_RATE_HZ → p=0.0
    recapture_prob = max(0.0, min(1.0, 1.0 - margin / TICK_RATE_HZ))
    return -recapture_prob * our_value


def threaten_score(
    candidate: CandidateMove,
    ai_state: AIState,
    arrival_data: ArrivalData,
) -> float:
    """Compute the value of the best enemy piece we safely threaten post-move.

    After arriving at dest and completing cooldown, check which enemy
    pieces we can attack. A threat is "safe" if the enemy piece can't
    reach our destination before our attack would land.

    Returns the max piece value among safely threatened enemies, or 0.0.
    """
    if candidate.ai_piece is None:
        return 0.0

    dest = (candidate.to_row, candidate.to_col)
    our_type = candidate.ai_piece.piece.type
    tps = arrival_data.tps
    cd_ticks = arrival_data.cd_ticks

    # Time for us to arrive at dest
    from_pos = candidate.ai_piece.piece.grid_position
    our_travel = compute_travel_ticks(
        from_pos[0], from_pos[1],
        dest[0], dest[1],
        our_type, tps,
    )

    # Pre-compute modified occupancy (our origin vacated)
    modified_occ = (arrival_data._occupied - {from_pos}) if arrival_data._occupied else None

    best_threat = 0.0

    for ep in ai_state.get_enemy_pieces():
        if ep.status == PieceStatus.TRAVELING or ep.piece.captured:
            continue
        ep_pos = ep.piece.grid_position
        if ep_pos == dest:
            continue  # That's a capture, not a threat

        # Time for us to attack this enemy from dest (after arriving + cooldown + reaction)
        attack_travel = compute_travel_ticks(
            dest[0], dest[1],
            ep_pos[0], ep_pos[1],
            our_type, tps,
        )
        our_attack_time = our_travel + cd_ticks + arrival_data.reaction_ticks + attack_travel

        # Can the enemy reach our dest before our attack lands?
        # If so, it can counter-capture us — not a safe threat.
        # Recompute with our origin vacated to avoid self-blocking.
        if modified_occ is not None:
            enemy_to_dest = _piece_arrival_time(
                ep, dest, tps, modified_occ, arrival_data._is_4p,
                threat_only=True,
            )
        else:
            enemy_to_dest = arrival_data.enemy_time_by_piece.get(
                ep.piece.id, {},
            ).get(dest, 999_999)

        if enemy_to_dest <= our_attack_time:
            continue  # Enemy can capture us back

        value = PIECE_VALUES.get(ep.piece.type, 0)
        if value > best_threat:
            best_threat = value

    return best_threat

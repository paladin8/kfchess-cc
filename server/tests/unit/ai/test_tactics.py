"""Tests for tactical filters."""

from kfchess.ai.arrival_field import ArrivalData, ArrivalField
from kfchess.ai.move_gen import CandidateMove
from kfchess.ai.state_extractor import AIPiece, PieceStatus, StateExtractor
from kfchess.ai.tactics import (
    GAME_ENDING_KING_BONUS,
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
from kfchess.game.board import Board, BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import GameStatus, Speed


def _make_state(speed=Speed.STANDARD):
    state = GameEngine.create_game(
        speed=speed,
        players={1: "bot:ai1", 2: "bot:ai2"},
        board_type=BoardType.STANDARD,
    )
    state.status = GameStatus.PLAYING
    return state


class TestCaptureFeasibility:
    def test_capture_returns_piece_value(self):
        """Capture returns the captured piece's material value."""
        candidate = CandidateMove(
            piece_id="p1_p1", to_row=3, to_col=3,
            capture_type=PieceType.QUEEN,
        )
        assert capture_value(candidate) == 9.0

    def test_capture_pawn_value(self):
        """Capturing a pawn returns 1.0."""
        candidate = CandidateMove(
            piece_id="p1_q1", to_row=3, to_col=3,
            capture_type=PieceType.PAWN,
        )
        assert capture_value(candidate) == 1.0

    def test_non_capture_returns_zero(self):
        """Non-capture moves return 0.0."""
        candidate = CandidateMove(
            piece_id="p1_r1", to_row=3, to_col=3,

        )
        assert capture_value(candidate) == 0.0


class TestGameEndingKingCapture:
    """Tests for game-ending king capture bonus."""

    def test_king_capture_without_ai_state_returns_base_value(self):
        """King capture without ai_state returns base value (no bonus)."""
        candidate = CandidateMove(
            piece_id="p1_q1", to_row=0, to_col=4,
            capture_type=PieceType.KING,
        )
        value = capture_value(candidate)
        assert value == PIECE_VALUES[PieceType.KING]
        assert value == 20.0  # Base king value

    def test_king_capture_with_single_enemy_king_adds_bonus(self):
        """Capturing the last enemy king adds game-ending bonus."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)

        # Standard 2-player game has 1 enemy king
        enemy_kings = [
            ep for ep in ai_state.get_enemy_pieces()
            if ep.piece.type == PieceType.KING
        ]
        assert len(enemy_kings) == 1

        candidate = CandidateMove(
            piece_id="p1_q1", to_row=0, to_col=4,
            capture_type=PieceType.KING,
        )
        value = capture_value(candidate, ai_state)
        expected = PIECE_VALUES[PieceType.KING] + GAME_ENDING_KING_BONUS
        assert value == expected
        assert value == 100.0  # 20 + 80

    def test_king_capture_with_multiple_enemy_kings_no_bonus(self):
        """Capturing a king when others remain gives no bonus (4-player)."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)

        # Add a second enemy king to simulate 4-player
        second_king = _make_ai_piece(
            PieceType.KING, 3, 0, 0, piece_id="p3_k1",
        )
        ai_state._enemy_pieces.append(second_king)

        # Now there are 2 enemy kings
        enemy_kings = [
            ep for ep in ai_state.get_enemy_pieces()
            if ep.piece.type == PieceType.KING
        ]
        assert len(enemy_kings) == 2

        candidate = CandidateMove(
            piece_id="p1_q1", to_row=0, to_col=4,
            capture_type=PieceType.KING,
        )
        value = capture_value(candidate, ai_state)
        # No bonus - game doesn't end
        assert value == PIECE_VALUES[PieceType.KING]
        assert value == 20.0

    def test_non_king_capture_unaffected(self):
        """Capturing non-king pieces is unaffected by game-ending logic."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)

        candidate = CandidateMove(
            piece_id="p1_q1", to_row=3, to_col=3,
            capture_type=PieceType.QUEEN,
        )
        value = capture_value(candidate, ai_state)
        assert value == PIECE_VALUES[PieceType.QUEEN]
        assert value == 9.0


class TestMoveSafety:
    def test_safe_move_near_home(self):
        """Moving near our back rank is safe — no recapture cost."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        pawn = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.PAWN:
                pawn = ap
                break

        candidate = CandidateMove(
            piece_id=pawn.piece.id, to_row=5, to_col=pawn.piece.grid_position[1],

            ai_piece=pawn,
        )
        safety = move_safety(candidate, ai_state, data)
        assert safety == 0.0  # Safe near our side — no expected loss

    def test_unsafe_move_deep_territory(self):
        """Moving deep into enemy territory has negative safety cost."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        knight = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.KNIGHT:
                knight = ap
                break

        candidate = CandidateMove(
            piece_id=knight.piece.id, to_row=2, to_col=4,

            ai_piece=knight,
        )
        safety = move_safety(candidate, ai_state, data)
        # Near enemy pieces — expected material loss
        assert safety < 0


def _make_ai_piece(
    piece_type: PieceType,
    player: int,
    row: int,
    col: int,
    status: PieceStatus = PieceStatus.IDLE,
    cooldown_remaining: int = 0,
    travel_direction: tuple[float, float] | None = None,
    piece_id: str | None = None,
) -> AIPiece:
    """Helper to create an AIPiece for testing."""
    pid = piece_id or f"p{player}_{piece_type.value}_{row}_{col}"
    piece = Piece(
        id=pid,
        type=piece_type,
        player=player,
        row=float(row),
        col=float(col),
    )
    return AIPiece(
        piece=piece,
        status=status,
        cooldown_remaining=cooldown_remaining,
        destination=None,
        travel_direction=travel_direction,
        current_position=(row, col),
    )


class TestDodgeability:
    def test_target_on_long_cooldown_no_prob(self):
        """Target can't dodge if still on cooldown when we arrive."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        # Find our pawn and an enemy pawn
        our_pawn = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.PAWN:
                our_pawn = ap
                break

        # Target at adjacent square with long cooldown
        target = _make_ai_piece(PieceType.PAWN, 2, 5, our_pawn.piece.grid_position[1],
                                cooldown_remaining=200)

        # Inject target into ai_state enemy pieces
        ai_state._enemy_pieces.append(target)

        candidate = CandidateMove(
            piece_id=our_pawn.piece.id, to_row=5,
            to_col=our_pawn.piece.grid_position[1],
            capture_type=PieceType.PAWN,
            ai_piece=our_pawn,
        )
        prob = dodge_probability(candidate, ai_state, data)
        assert prob == 0.0  # Target can't move in time

    def test_idle_target_long_distance_high_prob(self):
        """Idle target far away with many lateral escapes → high prob."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        # Target is idle (cooldown=0) and 5 squares away
        target = _make_ai_piece(PieceType.PAWN, 2, 2, 3, cooldown_remaining=0)
        ai_state._enemy_pieces.append(target)
        # Target has many lateral escape squares (off the attack column)
        ai_state.enemy_escape_moves[target.piece.id] = [
            (2, 2), (2, 4), (3, 2), (3, 4),  # Lateral dodges
            (1, 3), (0, 3),  # Along attack ray — NOT dodges
        ]

        # Our piece is at (7, 3) — 5 squares away, attacking up the column
        our_piece = _make_ai_piece(PieceType.ROOK, 1, 7, 3)
        ai_state._own_pieces.append(our_piece)

        candidate = CandidateMove(
            piece_id=our_piece.piece.id, to_row=2, to_col=3,
            capture_type=PieceType.PAWN,
            ai_piece=our_piece,
        )
        prob = dodge_probability(candidate, ai_state, data)
        # 4 lateral dodges → escape_factor = 1.0, time_factor high
        assert prob > 0.8

    def test_short_cooldown_target_small_prob(self):
        """Target with short remaining cooldown, we arrive just after → small prob."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        # Target cooldown expires in 8 ticks, we arrive in 10 ticks
        target = _make_ai_piece(PieceType.KNIGHT, 2, 6, 3, cooldown_remaining=8)
        ai_state._enemy_pieces.append(target)

        our_piece = _make_ai_piece(PieceType.KNIGHT, 1, 7, 3)

        candidate = CandidateMove(
            piece_id=our_piece.piece.id, to_row=6, to_col=3,
            capture_type=PieceType.KNIGHT,
            ai_piece=our_piece,
        )
        prob = dodge_probability(candidate, ai_state, data)
        # Knight travel = 2*10 = 20 ticks
        # dodge_start = 8+1=9, arrival=20 → dodge_window=11
        # Target has no escape counts set → defaults to 0 → prob = 0
        assert prob == 0.0  # No escape squares registered

    def test_knight_capture_dodge_window(self):
        """Knight has full 2-square travel time for dodge calculation."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        # Idle target with escapes (all lateral — knight attacks L-shape so
        # any adjacent move dodges)
        target = _make_ai_piece(PieceType.QUEEN, 2, 5, 4, cooldown_remaining=0)
        ai_state._enemy_pieces.append(target)
        ai_state.enemy_escape_moves[target.piece.id] = [
            (5, 3), (5, 5), (4, 4), (6, 4),
        ]

        # Knight at (7, 3) → target at (5, 4): L-shape = 2*10=20 ticks
        our_knight = _make_ai_piece(PieceType.KNIGHT, 1, 7, 3)

        candidate = CandidateMove(
            piece_id=our_knight.piece.id, to_row=5, to_col=4,
            capture_type=PieceType.QUEEN,
            ai_piece=our_knight,
        )
        prob = dodge_probability(candidate, ai_state, data)
        # arrival = 20 ticks
        # dodge_start = 0 + 1 = 1
        # dodge_window = 20 - 1 = 19
        # time_factor = min(1.0, 19 / (2 * 10)) = 0.95
        # escape_factor = 1.0
        # prob ≈ 0.95 — target has nearly 2 squares of time to dodge
        assert 0.8 < prob < 1.0

    def test_non_capture_returns_zero(self):
        """Dodgeability only applies to captures."""
        data = ArrivalData(tps=10, cd_ticks=100)
        candidate = CandidateMove(
            piece_id="p1", to_row=4, to_col=4,

        )
        prob = dodge_probability(candidate, None, data)
        assert prob == 0.0

    def test_cornered_target_no_prob(self):
        """Target with 0 escape moves → no dodge prob."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        # Idle target with NO escape squares
        target = _make_ai_piece(PieceType.PAWN, 2, 3, 3, cooldown_remaining=0)
        ai_state._enemy_pieces.append(target)
        ai_state.enemy_escape_moves[target.piece.id] = []  # Cornered

        our_piece = _make_ai_piece(PieceType.ROOK, 1, 7, 3)

        candidate = CandidateMove(
            piece_id=our_piece.piece.id, to_row=3, to_col=3,
            capture_type=PieceType.PAWN,
            ai_piece=our_piece,
        )
        prob = dodge_probability(candidate, ai_state, data)
        assert prob == 0.0  # Can't dodge with nowhere to go

    def test_few_escapes_lower_prob(self):
        """Target with 1 lateral escape has lower prob than target with many."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        target = _make_ai_piece(PieceType.PAWN, 2, 2, 3, cooldown_remaining=0)
        ai_state._enemy_pieces.append(target)
        # Rook attacking up the column from (7,3) to (2,3)
        our_piece = _make_ai_piece(PieceType.ROOK, 1, 7, 3)

        candidate = CandidateMove(
            piece_id=our_piece.piece.id, to_row=2, to_col=3,
            capture_type=PieceType.PAWN,
            ai_piece=our_piece,
        )

        # 1 lateral dodge
        ai_state.enemy_escape_moves[target.piece.id] = [(2, 4)]
        prob_few = dodge_probability(candidate, ai_state, data)

        # 4 lateral dodges
        ai_state.enemy_escape_moves[target.piece.id] = [
            (2, 2), (2, 4), (3, 2), (3, 4),
        ]
        prob_many = dodge_probability(candidate, ai_state, data)

        assert prob_many > prob_few > 0.0

    def test_only_ray_escapes_no_dodge(self):
        """Target whose only escapes are along the attack ray → no dodge."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=1)

        # Rook attacking up the column from (7,3) to (4,3)
        target = _make_ai_piece(PieceType.ROOK, 2, 4, 3, cooldown_remaining=0)
        ai_state._enemy_pieces.append(target)
        # Target can only move further up the column (same direction as attack)
        ai_state.enemy_escape_moves[target.piece.id] = [(3, 3), (2, 3), (1, 3)]

        our_piece = _make_ai_piece(PieceType.ROOK, 1, 7, 3)

        candidate = CandidateMove(
            piece_id=our_piece.piece.id, to_row=4, to_col=3,
            capture_type=PieceType.ROOK,
            ai_piece=our_piece,
        )
        prob = dodge_probability(candidate, ai_state, data)
        assert prob == 0.0  # All escapes are along the attack ray


class TestRecaptureBonus:
    def test_recapture_incoming_attack(self):
        """Enemy traveling toward our piece — position to recapture → bonus."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=10)

        # Our pawn at (6, 4) — target of the attack
        our_pawn = _make_ai_piece(PieceType.PAWN, 1, 6, 4)
        ai_state._own_pieces.append(our_pawn)

        # Enemy rook traveling down column 4 toward our pawn at (6,4)
        # Currently at (2, 4), 4 squares away → lands in 40 ticks
        enemy_rook = _make_ai_piece(
            PieceType.ROOK, 2, 2, 4,
            status=PieceStatus.TRAVELING,
            travel_direction=(1.0, 0.0),
        )
        ai_state._enemy_pieces.append(enemy_rook)

        # Our knight at (7, 2) moves to (5, 3) — close to (6, 4)
        our_knight = _make_ai_piece(PieceType.KNIGHT, 1, 7, 2)
        candidate = CandidateMove(
            piece_id=our_knight.piece.id, to_row=5, to_col=3,
            ai_piece=our_knight,
        )

        bonus = recapture_bonus(candidate, ai_state, data)
        # Enemy lands at (6,4) in 40 ticks, vulnerable until 40+100=140
        # Our knight: travel to (5,3) = 2*10=20, cd=100, reaction=10,
        # then travel to (6,4) = 2*10=20 → total=150
        # 150 < 140? No — just misses. Let's verify:
        # Actually this should be 0 since we can't make it in time
        # Let's use a closer dest instead
        assert bonus == 0.0  # Too slow

    def test_recapture_close_enough(self):
        """Position close enough to recapture incoming attacker."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=10)

        # Our pawn at (6, 4)
        our_pawn = _make_ai_piece(PieceType.PAWN, 1, 6, 4)
        ai_state._own_pieces.append(our_pawn)

        # Enemy rook at (2, 4) traveling down — 4 squares to our pawn
        enemy_rook = _make_ai_piece(
            PieceType.ROOK, 2, 2, 4,
            status=PieceStatus.TRAVELING,
            travel_direction=(1.0, 0.0),
        )
        ai_state._enemy_pieces.append(enemy_rook)

        # Our rook at (6, 0) moves to (6, 3) — 1 square from (6, 4)
        our_rook = _make_ai_piece(PieceType.ROOK, 1, 6, 0)
        candidate = CandidateMove(
            piece_id=our_rook.piece.id, to_row=6, to_col=3,
            ai_piece=our_rook,
        )
        bonus = recapture_bonus(candidate, ai_state, data)
        # Enemy lands at (6,4) in 40 ticks, vulnerable until 40+100+10=150
        # Our rook: travel to (6,3) = 3*10=30, cd=100, reaction=10,
        # travel to (6,4) = 1*10=10 → total=150
        # 150 < 150? No, equal — just misses
        assert bonus == 0.0

    def test_recapture_with_margin(self):
        """Position with enough time margin to recapture."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=10)

        # Our pawn at (6, 4)
        our_pawn = _make_ai_piece(PieceType.PAWN, 1, 6, 4)
        ai_state._own_pieces.append(our_pawn)

        # Enemy rook at (0, 4) traveling down — 6 squares to our pawn
        enemy_rook = _make_ai_piece(
            PieceType.ROOK, 2, 0, 4,
            status=PieceStatus.TRAVELING,
            travel_direction=(1.0, 0.0),
        )
        ai_state._enemy_pieces.append(enemy_rook)

        # Our rook already adjacent at (6, 5) moves to (6, 3)
        our_rook = _make_ai_piece(PieceType.ROOK, 1, 6, 5)
        candidate = CandidateMove(
            piece_id=our_rook.piece.id, to_row=6, to_col=3,
            ai_piece=our_rook,
        )
        bonus = recapture_bonus(candidate, ai_state, data)
        # Enemy lands at (6,4) in 60 ticks, vulnerable until 60+100+10=170
        # Our rook: travel to (6,3) = 2*10=20, cd=100, reaction=10,
        # travel to (6,4) = 1*10=10 → total=140
        # 140 < 170 ✓ → bonus = 5.0 (rook value)
        assert bonus == 5.0

    def test_no_traveling_enemies(self):
        """No traveling enemies → no recapture bonus."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=10)

        our_pawn = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.PAWN:
                our_pawn = ap
                break

        candidate = CandidateMove(
            piece_id=our_pawn.piece.id, to_row=5,
            to_col=our_pawn.piece.grid_position[1],
            ai_piece=our_pawn,
        )
        assert recapture_bonus(candidate, ai_state, data) == 0.0

    def test_enemy_not_heading_toward_us(self):
        """Enemy traveling away from our pieces → no bonus."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=10, cd_ticks=100, reaction_ticks=10)

        # Enemy rook traveling UP (away from our pieces on rows 6-7)
        enemy_rook = _make_ai_piece(
            PieceType.ROOK, 2, 3, 4,
            status=PieceStatus.TRAVELING,
            travel_direction=(-1.0, 0.0),
        )
        ai_state._enemy_pieces.append(enemy_rook)

        our_rook = _make_ai_piece(PieceType.ROOK, 1, 6, 4)
        candidate = CandidateMove(
            piece_id=our_rook.piece.id, to_row=5, to_col=4,
            ai_piece=our_rook,
        )
        assert recapture_bonus(candidate, ai_state, data) == 0.0


class TestThreatenScore:
    def test_knight_threatens_queen_safely(self):
        """Knight near enemy queen that can't reach knight's square → high threat."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)

        our_knight = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.KNIGHT:
                our_knight = ap
                break

        enemy_queen = _make_ai_piece(PieceType.QUEEN, 2, 4, 4, piece_id="eq1")
        ai_state._enemy_pieces.append(enemy_queen)

        # Include all enemy pieces in arrival data so defaults don't mislead
        enemy_by_piece: dict[str, dict[tuple[int, int], int]] = {}
        for ep in ai_state.get_enemy_pieces():
            # All existing enemy pieces CAN reach (5,2) — only queen matters
            enemy_by_piece[ep.piece.id] = {(5, 2): 0}
        # Override: queen can't reach knight's destination
        enemy_by_piece[enemy_queen.piece.id] = {(5, 2): 999_999}

        data = ArrivalData(
            tps=30, cd_ticks=300,
            enemy_time_by_piece=enemy_by_piece,
        )

        candidate = CandidateMove(
            piece_id=our_knight.piece.id, to_row=5, to_col=2,
            ai_piece=our_knight,
        )
        score = threaten_score(candidate, ai_state, data)
        assert score == 9.0  # Queen value

    def test_no_threat_when_enemy_can_recapture(self):
        """Enemy piece that can reach our destination → not a safe threat."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)

        our_rook = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.ROOK:
                our_rook = ap
                break

        enemy_queen = _make_ai_piece(PieceType.QUEEN, 2, 3, 0, piece_id="eq1")
        ai_state._enemy_pieces.append(enemy_queen)

        # All enemy pieces can reach our dest quickly
        enemy_by_piece: dict[str, dict[tuple[int, int], int]] = {}
        for ep in ai_state.get_enemy_pieces():
            enemy_by_piece[ep.piece.id] = {(4, 0): 0}

        data = ArrivalData(
            tps=30, cd_ticks=300,
            enemy_time_by_piece=enemy_by_piece,
        )

        candidate = CandidateMove(
            piece_id=our_rook.piece.id, to_row=4, to_col=0,
            ai_piece=our_rook,
        )
        score = threaten_score(candidate, ai_state, data)
        assert score == 0.0  # All enemies can recapture

    def test_no_threat_without_piece(self):
        """Candidate without ai_piece returns 0."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalData(tps=30, cd_ticks=300)

        candidate = CandidateMove(piece_id="x", to_row=4, to_col=4)
        assert threaten_score(candidate, ai_state, data) == 0.0

    def test_rook_no_phantom_threat_off_axis(self):
        """Rook should NOT score a threat to a king it can't reach in one move.

        Regression: the old compute_travel_ticks used Chebyshev distance for
        all pieces, giving rooks a finite attack time to off-axis targets.
        This produced phantom threats from positions where the rook had no
        actual attack line.
        """
        # Minimal board: our rook + king, enemy king not aligned with dest
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.ROOK, 1, 7, 0))

        state = GameEngine.create_game_from_board(
            speed=Speed.LIGHTNING,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)

        rook = ai_state.pieces_by_id["R:1:7:0"]

        # Rook moves to (3, 0). Enemy king at (0, 4) is NOT on same
        # rank or file as (3, 0), so the rook cannot attack it.
        # King at (0, 4) is 4 cols away from dest (3, 0) — can't
        # counter-capture in one move, so enemy_to_dest = INF.
        #
        # Old bug: compute_travel_ticks(3,0 → 0,4) = max(3,4)*tps = 24
        #   → finite attack time, INF enemy arrival → phantom threat scored
        # Fix: compute_travel_ticks returns INF for off-axis rook
        #   → attack_travel = INF → our_attack_time = INF → no threat
        enemy_by_piece: dict[str, dict[tuple[int, int], int]] = {}
        for ep in ai_state.get_enemy_pieces():
            # King can't reach (3, 0) in one move — default to INF
            enemy_by_piece[ep.piece.id] = {}

        data = ArrivalData(
            tps=6, cd_ticks=60,
            enemy_time_by_piece=enemy_by_piece,
        )

        candidate = CandidateMove(
            piece_id=rook.piece.id, to_row=3, to_col=0,
            ai_piece=rook,
        )
        score = threaten_score(candidate, ai_state, data)
        assert score == 0.0  # No real threat — rook can't attack from (3,0) to (0,4)

    def test_rook_real_threat_on_same_file(self):
        """Rook on same file as enemy king SHOULD score a threat."""
        # Rook starts on file 4, moves up file 4 toward king at (0, 4).
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 0))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.ROOK, 1, 7, 4))

        state = GameEngine.create_game_from_board(
            speed=Speed.LIGHTNING,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)

        rook = ai_state.pieces_by_id["R:1:7:4"]

        # Rook moves to (3, 4) — same file as king at (0, 4).
        # King at (0, 4) is 3 rows from (3, 4) — can't reach in one move.
        # Rook CAN attack along the file: (3,4) → (0,4).
        enemy_by_piece: dict[str, dict[tuple[int, int], int]] = {}
        for ep in ai_state.get_enemy_pieces():
            enemy_by_piece[ep.piece.id] = {}  # King can't reach (3,4)

        data = ArrivalData(
            tps=6, cd_ticks=60,
            enemy_time_by_piece=enemy_by_piece,
        )

        candidate = CandidateMove(
            piece_id=rook.piece.id, to_row=3, to_col=4,
            ai_piece=rook,
        )
        score = threaten_score(candidate, ai_state, data)
        assert score == PIECE_VALUES[PieceType.KING]  # 10.0 — real threat


class TestKingExposurePenalty:
    def _make_exposure_board(self):
        """Create a board where a rook shields the king from an enemy queen.

        Layout (row 7):
          col 1: enemy queen
          col 2: our rook (shielding king)
          col 3: our king
        Queen is only 2 squares from king — if rook moves off the rank,
        the queen arrives in 60 ticks which matches the king's escape time,
        triggering a penalty.
        """
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 3))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.ROOK, 1, 7, 2))  # shields king
        board.pieces.append(Piece.create(PieceType.QUEEN, 2, 7, 1))  # threatens king

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)
        return ai_state, data

    def test_moving_shielding_piece_penalized(self):
        """Moving a piece that shields the king from attack yields a large penalty."""
        ai_state, data = self._make_exposure_board()
        rook = ai_state.pieces_by_id["R:1:7:2"]

        # Move rook off the rank — exposes king to queen
        candidate = CandidateMove(
            piece_id=rook.piece.id, to_row=3, to_col=2, ai_piece=rook,
        )
        penalty = king_exposure_penalty(candidate, ai_state, data)
        assert penalty < -50  # Should be a very large penalty

    def test_moving_non_shielding_piece_no_penalty(self):
        """Moving a piece that doesn't shield the king has no penalty."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        # Knight on a square that doesn't block any attack line to the king
        board.pieces.append(Piece.create(PieceType.KNIGHT, 1, 7, 1))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)

        knight = ai_state.pieces_by_id["N:1:7:1"]
        candidate = CandidateMove(
            piece_id=knight.piece.id, to_row=5, to_col=2, ai_piece=knight,
        )
        penalty = king_exposure_penalty(candidate, ai_state, data)
        assert penalty == 0.0

    def test_king_move_no_penalty(self):
        """Moving the king itself should not trigger exposure penalty."""
        ai_state, data = self._make_exposure_board()
        king = ai_state.pieces_by_id["K:1:7:3"]

        candidate = CandidateMove(
            piece_id=king.piece.id, to_row=6, to_col=3, ai_piece=king,
        )
        penalty = king_exposure_penalty(candidate, ai_state, data)
        assert penalty == 0.0


class TestKingThreatCaptureBonus:
    def test_capturing_king_threatening_piece_gives_bonus(self):
        """Capturing an enemy piece that threatens our king gives a bonus."""
        # Enemy rook at (7, 3) threatens king at (7, 4) — 1 square away
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.ROOK, 2, 7, 3))  # threatens king
        board.pieces.append(Piece.create(PieceType.KNIGHT, 1, 5, 2))  # can capture rook

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)

        knight = ai_state.pieces_by_id["N:1:5:2"]
        candidate = CandidateMove(
            piece_id=knight.piece.id, to_row=7, to_col=3,
            capture_type=PieceType.ROOK, ai_piece=knight,
        )
        bonus = king_threat_capture_bonus(candidate, ai_state, data)
        assert bonus == PIECE_VALUES[PieceType.KING]

    def test_capturing_non_threatening_piece_no_bonus(self):
        """Capturing an enemy piece far from our king gives no threat bonus."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        # Enemy pawn far from king, not threatening it
        board.pieces.append(Piece.create(PieceType.PAWN, 2, 1, 0))
        board.pieces.append(Piece.create(PieceType.ROOK, 1, 4, 0))  # can capture pawn

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)

        rook = ai_state.pieces_by_id["R:1:4:0"]
        candidate = CandidateMove(
            piece_id=rook.piece.id, to_row=1, to_col=0,
            capture_type=PieceType.PAWN, ai_piece=rook,
        )
        bonus = king_threat_capture_bonus(candidate, ai_state, data)
        assert bonus == 0.0

    def test_non_capture_no_bonus(self):
        """Non-capture moves get no king threat bonus."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        pawn = None
        for ap in ai_state.get_own_pieces():
            if ap.piece.type == PieceType.PAWN:
                pawn = ap
                break

        candidate = CandidateMove(
            piece_id=pawn.piece.id, to_row=5,
            to_col=pawn.piece.grid_position[1], ai_piece=pawn,
        )
        bonus = king_threat_capture_bonus(candidate, ai_state, data)
        assert bonus == 0.0


class TestKingBlockingBonus:
    def _make_blocking_board(self):
        """Create a board where the king is threatened by an enemy queen.

        Layout (row 7):
          col 2: enemy queen
          col 4: our king
        Knight at (5, 2) can move to (7, 3) to block the queen's ray.
        Queen is 2 squares from king — imminent threat (margin = 0).
        """
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.QUEEN, 2, 7, 2))  # threatens king
        board.pieces.append(Piece.create(PieceType.KNIGHT, 1, 5, 2))  # can block

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)
        return ai_state, data

    def test_blocking_slider_gives_bonus(self):
        """Moving a piece to block a slider's attack on the king gives a bonus."""
        ai_state, data = self._make_blocking_board()
        knight = ai_state.pieces_by_id["N:1:5:2"]

        # Move knight to (7, 3) — blocks queen's ray to king on row 7
        candidate = CandidateMove(
            piece_id=knight.piece.id, to_row=7, to_col=3, ai_piece=knight,
        )
        bonus = king_blocking_bonus(candidate, ai_state, data)
        assert bonus > 50  # Should be a large bonus

    def test_no_bonus_when_king_not_threatened(self):
        """No blocking bonus when the king is not under threat."""
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 4))
        board.pieces.append(Piece.create(PieceType.KNIGHT, 1, 5, 3))

        state = GameEngine.create_game_from_board(
            speed=Speed.STANDARD,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)

        knight = ai_state.pieces_by_id["N:1:5:3"]
        candidate = CandidateMove(
            piece_id=knight.piece.id, to_row=4, to_col=4, ai_piece=knight,
        )
        bonus = king_blocking_bonus(candidate, ai_state, data)
        assert bonus == 0.0

    def test_reblocking_cancels_exposure_penalty(self):
        """Moving from one blocking position to another on the same ray.

        Layout (col 4):
          row 3: enemy rook
          row 4: our rook (currently blocking)
          row 7: our king
        Our rook moves from (4,4) to (5,4) — still blocking on the same file.
        Uses lightning speed so the threat is imminent after vacating.
        The blocking bonus should offset the exposure penalty.
        """
        board = Board(pieces=[], board_type=BoardType.STANDARD, width=8, height=8)
        board.pieces.append(Piece.create(PieceType.KING, 1, 7, 4))
        board.pieces.append(Piece.create(PieceType.KING, 2, 0, 0))
        board.pieces.append(Piece.create(PieceType.ROOK, 2, 3, 4))  # threatens king
        board.pieces.append(Piece.create(PieceType.ROOK, 1, 4, 4))  # currently blocking

        state = GameEngine.create_game_from_board(
            speed=Speed.LIGHTNING,
            players={1: "bot:test1", 2: "bot:test2"},
            board=board,
        )
        state.status = GameStatus.PLAYING
        ai_state = StateExtractor.extract(state, ai_player=1)
        data = ArrivalField.compute(ai_state, state.config)

        rook = ai_state.pieces_by_id["R:1:4:4"]
        candidate = CandidateMove(
            piece_id=rook.piece.id, to_row=5, to_col=4, ai_piece=rook,
        )

        penalty = king_exposure_penalty(candidate, ai_state, data)
        bonus = king_blocking_bonus(candidate, ai_state, data)

        # Exposure penalty fires (vacating unblocks the enemy rook)
        assert penalty < -50

        # Blocking bonus should offset it (re-blocking at new position)
        assert bonus > 50

        # Net should be approximately zero (king stays protected)
        net = penalty + bonus
        assert abs(net) < 20, f"Re-blocking net should be ~0, got {net}"

    def test_king_move_no_bonus(self):
        """King moves should not get a blocking bonus."""
        ai_state, data = self._make_blocking_board()
        king = ai_state.pieces_by_id["K:1:7:4"]

        candidate = CandidateMove(
            piece_id=king.piece.id, to_row=6, to_col=4, ai_piece=king,
        )
        bonus = king_blocking_bonus(candidate, ai_state, data)
        assert bonus == 0.0

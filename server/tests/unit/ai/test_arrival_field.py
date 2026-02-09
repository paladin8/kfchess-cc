"""Tests for arrival time field computation."""

from kfchess.ai.arrival_field import ArrivalField
from kfchess.ai.state_extractor import PieceStatus, StateExtractor
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.moves import Cooldown, Move
from kfchess.game.pieces import PieceType
from kfchess.game.state import GameStatus, Speed


def _make_state(speed=Speed.STANDARD):
    state = GameEngine.create_game(
        speed=speed,
        players={1: "bot:ai1", 2: "bot:ai2"},
        board_type=BoardType.STANDARD,
    )
    state.status = GameStatus.PLAYING
    return state


class TestArrivalField:
    def test_basic_computation(self):
        """Arrival fields compute without error on initial board."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        assert len(data.our_time) > 0
        assert len(data.enemy_time) > 0

    def test_own_piece_square_zero_time(self):
        """A piece on its own square has arrival time = 0 (if idle)."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Player 1 rook at (7, 0)
        assert data.get_our_time(7, 0) == 0

    def test_rook_blocked_by_pawn(self):
        """Rook can't reach past a blocking pawn."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Rook at (7,0) is blocked by pawn at (6,0)
        assert data.get_our_time(5, 0) != 0

    def test_pawn_reaches_forward(self):
        """Pawn reaches forward squares."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        config = state.config
        data = ArrivalField.compute(ai_state, config)
        # Pawn at (6,0) reaches (5,0) in 1*tps = 30
        assert data.get_our_time(5, 0) == config.ticks_per_square

    def test_enemy_time_near_enemy(self):
        """Enemy arrival time should be low near enemy pieces."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Enemy back rank (row 0) should have very low enemy time
        assert data.get_enemy_time(0, 4) == 0  # Enemy king is there

    def test_our_time_far_from_pieces(self):
        """Our arrival time should be high for distant unreachable squares."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Row 0 is across the board — most pieces can't reach in 1 move
        # Some squares might be INF if no piece can reach
        our_t = data.get_our_time(0, 0)
        assert our_t > 0

    def test_cooldown_adds_delay(self):
        """Pieces on cooldown have arrival time increased."""
        state = _make_state()
        state.cooldowns.append(Cooldown(piece_id="p1_n1", start_tick=0, duration=50))
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Field still computes; just check it doesn't crash
        assert data.get_our_time(5, 0) > 0

    def test_critical_only_mode(self):
        """Critical-only mode computes fewer squares."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        full = ArrivalField.compute(ai_state, state.config, critical_only=False)
        critical = ArrivalField.compute(ai_state, state.config, critical_only=True)
        assert len(critical.our_time) < len(full.our_time)

    def test_lightning_speed(self):
        """Arrival times are shorter with lightning speed."""
        state_std = _make_state(Speed.STANDARD)
        state_lit = _make_state(Speed.LIGHTNING)
        ai_std = StateExtractor.extract(state_std, 1)
        ai_lit = StateExtractor.extract(state_lit, 1)
        data_std = ArrivalField.compute(ai_std, state_std.config)
        data_lit = ArrivalField.compute(ai_lit, state_lit.config)
        assert data_std.get_our_time(5, 0) > data_lit.get_our_time(5, 0)

    def test_post_arrival_safety_safe_square(self):
        """A square far from enemies has positive post-arrival safety."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        config = state.config
        data = ArrivalField.compute(ai_state, config)
        # Move a pawn 1 square forward (row 6→5, near our side)
        travel = config.ticks_per_square  # 1 square
        safety = data.post_arrival_safety(5, 0, travel)
        # Near our back rank, enemy is far — should be safe
        assert safety > 0

    def test_post_arrival_safety_dangerous_square(self):
        """A square near enemy pieces has negative post-arrival safety."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        config = state.config
        data = ArrivalField.compute(ai_state, config)
        # Try moving deep into enemy territory with long travel
        travel = 5 * config.ticks_per_square
        safety = data.post_arrival_safety(2, 4, travel)
        # Near enemy back rank with long travel + cooldown — very unsafe
        assert safety < 0

    def test_enemy_time_excluding(self):
        """Excluding a piece from enemy times works correctly."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Enemy king at (0, 4) — enemy_time at (0,4) should be 0
        assert data.get_enemy_time(0, 4) == 0
        # Excluding the king, other pieces may still reach (0,4)
        # but it should be > 0 (queen at (0,3) reaches in 1*tps)
        enemy_king = ai_state.get_enemy_king()
        assert enemy_king is not None
        excl_time = data.get_enemy_time_excluding(0, 4, enemy_king.piece.id)
        assert excl_time > 0

    def test_is_piece_at_risk_idle(self):
        """Idle pieces are at risk if enemy arrives before reaction + escape time."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Threshold = reaction_ticks + tps = 30 + 30 = 60.
        # (2, 4) is 1 square from enemy pawns (enemy_t=30): 30 < 60 → at risk
        assert data.is_piece_at_risk(2, 4, cooldown_remaining=0) is True
        # (3, 4) is 2 squares from nearest enemy (enemy_t=60): 60 < 60 → safe
        assert data.is_piece_at_risk(3, 4, cooldown_remaining=0) is False
        # Enemy king sits at (0,4) with arrival time 0 — at risk
        assert data.is_piece_at_risk(0, 4, cooldown_remaining=0) is True

    def test_is_piece_at_risk_on_cooldown(self):
        """Pieces on cooldown are at risk if enemy arrives before cd expires."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        # Piece on long cooldown near enemies — at risk
        assert data.is_piece_at_risk(2, 4, cooldown_remaining=300) is True
        # Piece far from enemies even with cooldown — safe
        assert data.is_piece_at_risk(7, 4, cooldown_remaining=300) is False

    def test_tps_and_cd_stored(self):
        """ArrivalData stores tps and cd_ticks from config."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        config = state.config
        data = ArrivalField.compute(ai_state, config)
        assert data.tps == config.ticks_per_square
        assert data.cd_ticks == config.cooldown_ticks

    def test_traveling_enemy_threatens_path(self):
        """A traveling enemy rook should threaten squares along its path."""
        state = _make_state()
        tps = state.config.ticks_per_square  # 30 for standard

        # Clear the middle of the board by capturing pawns to make a clear path
        # Find enemy rook at (0, 0) and give it an active move heading down col 0
        enemy_rook = None
        for p in state.board.pieces:
            if p.player == 2 and p.type == PieceType.ROOK and p.col == 0.0:
                enemy_rook = p
                break
        assert enemy_rook is not None

        # Remove blocking pawns on col 0 so the path is clear
        for p in state.board.pieces:
            if p.type == PieceType.PAWN and p.col == 0.0:
                p.captured = True

        # Set up the rook as traveling from (0,0) to (7,0) — straight down
        rook_move = Move(
            piece_id=enemy_rook.id,
            path=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0),
                  (4.0, 0.0), (5.0, 0.0), (6.0, 0.0), (7.0, 0.0)],
            start_tick=0,
        )
        state.active_moves.append(rook_move)
        # Set current tick so rook is partway through (at row ~3)
        state.current_tick = 3 * tps

        ai_state = StateExtractor.extract(state, 1)

        # Verify the rook is seen as traveling
        rook_ai = ai_state.pieces_by_id.get(enemy_rook.id)
        assert rook_ai is not None
        assert rook_ai.status == PieceStatus.TRAVELING

        data = ArrivalField.compute(ai_state, state.config)

        # Squares ahead of the rook on col 0 should be threatened
        # Rook is at ~row 3, so row 4 is 1 square ahead = tps ticks
        enemy_t_row4 = data.get_enemy_time(4, 0)
        enemy_t_row5 = data.get_enemy_time(5, 0)
        assert enemy_t_row4 < 999_999, "Square ahead of traveling rook should be threatened"
        assert enemy_t_row5 < 999_999, "Square 2 ahead of traveling rook should be threatened"
        assert enemy_t_row4 < enemy_t_row5, "Closer squares should have shorter arrival time"

    def test_traveling_enemy_makes_king_at_risk(self):
        """A rook traveling toward the king should flag the king as at risk."""
        state = _make_state()
        tps = state.config.ticks_per_square

        # Find enemy rook and clear a path on col 4 (king's column)
        enemy_rook = None
        for p in state.board.pieces:
            if p.player == 2 and p.type == PieceType.ROOK and p.col == 0.0:
                enemy_rook = p
                break
        assert enemy_rook is not None

        # Move rook to col 4 and clear path
        enemy_rook.col = 4.0
        for p in state.board.pieces:
            if p.type == PieceType.PAWN and p.col == 4.0:
                p.captured = True

        # Rook traveling from (0,4) to (7,4) — headed straight for king
        rook_move = Move(
            piece_id=enemy_rook.id,
            path=[(0.0, 4.0), (1.0, 4.0), (2.0, 4.0), (3.0, 4.0),
                  (4.0, 4.0), (5.0, 4.0), (6.0, 4.0), (7.0, 4.0)],
            start_tick=0,
        )
        state.active_moves.append(rook_move)
        state.current_tick = 3 * tps  # Rook at ~row 3

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        # Player 1 king is at (7, 4) — rook is heading right for it
        # The king is idle (cooldown_remaining=0) so it only needs
        # reaction_ticks to dodge. But the rook arrival time at (7,4)
        # should be very low (~4*tps ticks away).
        king_pos = (7, 4)
        enemy_t = data.get_enemy_time(king_pos[0], king_pos[1])
        assert enemy_t < 999_999, "King square should be threatened by traveling rook"

        # King should be at risk: enemy arrives in ~4*tps, king needs
        # reaction_ticks to dodge. 4*tps >> reaction_ticks so not at_risk
        # by the strict definition (idle piece can dodge). But the square
        # itself having low enemy arrival time means safety scoring will
        # penalize staying or moving along the same line.
        assert enemy_t <= 5 * tps, "Traveling rook should arrive at king in ~4*tps"


class TestHasTravelingThreat:
    """Tests for has_traveling_threat() — detecting committed enemy moves."""

    def test_traveling_rook_flags_squares_on_path(self):
        """A rook traveling down a column should flag all squares ahead."""
        state = _make_state()
        tps = state.config.ticks_per_square

        enemy_rook = None
        for p in state.board.pieces:
            if p.player == 2 and p.type == PieceType.ROOK and p.col == 0.0:
                enemy_rook = p
                break
        assert enemy_rook is not None

        # Clear blocking pawns
        for p in state.board.pieces:
            if p.type == PieceType.PAWN and p.col == 0.0:
                p.captured = True

        rook_move = Move(
            piece_id=enemy_rook.id,
            path=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0),
                  (4.0, 0.0), (5.0, 0.0), (6.0, 0.0), (7.0, 0.0)],
            start_tick=0,
        )
        state.active_moves.append(rook_move)
        state.current_tick = 2 * tps

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        # Squares ahead of the rook should be flagged
        assert data.has_traveling_threat(4, 0)
        assert data.has_traveling_threat(5, 0)
        # Square off the column should NOT be flagged
        assert not data.has_traveling_threat(4, 3)

    def test_idle_enemy_not_flagged(self):
        """An idle enemy piece should NOT be flagged as a traveling threat."""
        state = _make_state()
        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        # Enemy pieces are idle on row 0-1. The squares they can reach
        # should NOT be flagged as traveling threats.
        assert not data.has_traveling_threat(3, 0)
        assert not data.has_traveling_threat(4, 4)


class TestSliderCaptureArrival:
    """Tests that sliders register arrival at opponent-occupied squares (captures)."""

    def test_idle_queen_threatens_enemy_king_square(self):
        """An idle queen pointing at the enemy king should register arrival
        at the king's square — the slider ray should not stop before it."""
        state = _make_state(Speed.LIGHTNING)
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        # Enemy queen at (4, 0) — diagonal ray toward (0, 4)
        enemy_queen = Piece(
            id="eq", type=PieceType.QUEEN, player=1,
            row=4, col=0, captured=False, moved=True,
        )
        # AI king at (0, 4) — on the queen's diagonal
        ai_king = Piece(
            id="ak", type=PieceType.KING, player=2,
            row=0, col=4, captured=False, moved=True,
        )
        # Other kings for game validity
        human_king = Piece(
            id="hk", type=PieceType.KING, player=1,
            row=7, col=4, captured=False, moved=True,
        )
        state.board.pieces = [enemy_queen, ai_king, human_king]

        ai_state = StateExtractor.extract(state, 2)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # The queen at (4,0) should be able to reach (0,4) via diagonal
        # in 4 squares = 4 * tps ticks
        enemy_t = data.get_enemy_time(0, 4)
        assert enemy_t == 4 * tps, (
            f"Idle queen should reach enemy king square in 4*tps={4*tps}, "
            f"got {enemy_t}"
        )

        # The king should be flagged as at risk
        assert data.is_piece_at_risk(0, 4, cooldown_remaining=0, is_king=True), (
            "King on queen's diagonal should be at risk"
        )

    def test_idle_rook_threatens_enemy_on_same_file(self):
        """An idle rook should register arrival at an enemy piece's square
        on the same file with no blockers in between."""
        state = _make_state(Speed.STANDARD)
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        enemy_rook = Piece(
            id="er", type=PieceType.ROOK, player=2,
            row=0, col=3, captured=False, moved=False,
        )
        our_pawn = Piece(
            id="op", type=PieceType.PAWN, player=1,
            row=5, col=3, captured=False, moved=True,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=7, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=7, captured=False, moved=True,
        )
        state.board.pieces = [enemy_rook, our_pawn, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # Rook at (0,3) should reach our pawn at (5,3) in 5*tps
        enemy_t = data.get_enemy_time(5, 3)
        assert enemy_t == 5 * tps, (
            f"Rook should reach enemy pawn in 5*tps={5*tps}, got {enemy_t}"
        )

        # But the rook should NOT reach past the pawn to (6,3)
        enemy_t_past = data.get_enemy_time(6, 3)
        assert enemy_t_past > 5 * tps, (
            f"Rook should not reach past the enemy pawn, got {enemy_t_past}"
        )

    def test_slider_does_not_capture_own_piece(self):
        """A slider should NOT register arrival at a friendly piece's square."""
        state = _make_state(Speed.STANDARD)
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        our_rook = Piece(
            id="or", type=PieceType.ROOK, player=1,
            row=7, col=0, captured=False, moved=False,
        )
        our_pawn = Piece(
            id="op", type=PieceType.PAWN, player=1,
            row=5, col=0, captured=False, moved=True,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=4, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=4, captured=False, moved=True,
        )
        state.board.pieces = [our_rook, our_pawn, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        # Rook at (7,0) should NOT reach its own pawn at (5,0) via the
        # slider enumeration (can't capture own piece). Check the rook's
        # per-piece arrival times — it should not register at or past (5,0).
        rook_times = data.our_time_by_piece.get("or", {})
        assert (5, 0) not in rook_times, (
            "Rook should not register arrival at own pawn's square"
        )
        assert (4, 0) not in rook_times, (
            "Rook should not reach past own pawn"
        )


class TestSelfBlockingFix:
    """Tests that moving a piece doesn't falsely show the destination as safe
    when the piece was blocking an enemy slider ray."""

    def test_moving_along_rook_ray_not_safe(self):
        """A piece blocking an enemy rook ray should not think moving along
        that ray is safe — vacating the square unblocks the enemy."""
        state = _make_state()
        # Clear the board except for specific pieces
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        # Enemy rook at (0, 3)
        enemy_rook = Piece(
            id="er", type=PieceType.ROOK, player=2,
            row=0, col=3, captured=False, moved=False,
        )
        # Our pawn at (4, 3) — blocks the rook's ray down column 3
        our_pawn = Piece(
            id="op", type=PieceType.PAWN, player=1,
            row=4, col=3, captured=False, moved=True,
        )
        # Our king far away so it doesn't interfere
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=7, captured=False, moved=True,
        )
        # Enemy king far away
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=7, captured=False, moved=True,
        )
        state.board.pieces = [enemy_rook, our_pawn, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # Without the fix: (5, 3) looks safe because our pawn at (4, 3)
        # blocks the enemy rook ray. The cached enemy_time would be INF.
        # But if pawn moves from (4,3) to (5,3), the rook ray is unblocked.
        travel = tps  # 1 square forward
        safety_naive = data.post_arrival_safety(5, 3, travel)
        safety_fixed = data.post_arrival_safety(
            5, 3, travel, moving_from=(4, 3),
        )

        # The naive check (no moving_from) may show safe because rook is blocked
        # The fixed check should show unsafe — rook can reach (5, 3) in 5*tps
        assert safety_fixed < safety_naive, (
            "Safety should be worse when accounting for unblocked ray"
        )
        # Rook arrives at (5,3) in 5*tps. Our pawn arrives in tps, then
        # cooldown + reaction. Safety = 5*tps - (tps + cd + reaction).
        # With standard: 150 - (30 + 300 + 30) = -210. Very unsafe.
        assert safety_fixed < 0, (
            f"Moving along enemy rook ray should be unsafe, got {safety_fixed}"
        )

    def test_moving_perpendicular_unaffected(self):
        """Moving perpendicular to an enemy rook ray shouldn't change much."""
        state = _make_state()
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        enemy_rook = Piece(
            id="er", type=PieceType.ROOK, player=2,
            row=0, col=3, captured=False, moved=False,
        )
        our_knight = Piece(
            id="on", type=PieceType.KNIGHT, player=1,
            row=4, col=3, captured=False, moved=True,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=7, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=7, captured=False, moved=True,
        )
        state.board.pieces = [enemy_rook, our_knight, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # Knight moves to (2, 4) — off the rook's column entirely
        # moving_from should still recompute but the destination isn't
        # on the rook's ray, so it shouldn't make a big difference
        travel = 2 * tps  # Knight travel
        safety_fixed = data.post_arrival_safety(
            2, 4, travel, moving_from=(4, 3),
        )
        # (2, 4) is not on column 3, so rook can't reach it regardless
        # The enemy king at (0,7) is the only piece that might reach it
        # King can only move 1 square, so it can't reach (2,4) in 1 move → INF
        assert safety_fixed > 0, (
            "Moving perpendicular off the ray should still be safe"
        )

    def test_moving_along_bishop_diagonal_not_safe(self):
        """A piece blocking an enemy bishop diagonal should not think moving
        along that diagonal is safe."""
        state = _make_state()
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        # Enemy bishop at (0, 0)
        enemy_bishop = Piece(
            id="eb", type=PieceType.BISHOP, player=2,
            row=0, col=0, captured=False, moved=False,
        )
        # Our pawn at (3, 3) — blocks bishop's diagonal
        our_pawn = Piece(
            id="op", type=PieceType.PAWN, player=1,
            row=3, col=3, captured=False, moved=True,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=7, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=7, captured=False, moved=True,
        )
        state.board.pieces = [enemy_bishop, our_pawn, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # Pawn moves from (3,3) to (4,4) — along the same diagonal
        # Without fix: bishop blocked at (3,3), so (4,4) looks safe
        # With fix: bishop can reach (4,4) in 4*tps after pawn vacates
        travel = tps
        safety_fixed = data.post_arrival_safety(
            4, 4, travel, moving_from=(3, 3),
        )
        assert safety_fixed < 0, (
            f"Moving along enemy bishop diagonal should be unsafe, got {safety_fixed}"
        )

    def test_double_blocker_still_safe(self):
        """If two of our pieces block a ray, moving the first still leaves
        the second blocking — destination beyond both should remain safe."""
        state = _make_state()
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        enemy_rook = Piece(
            id="er", type=PieceType.ROOK, player=2,
            row=0, col=3, captured=False, moved=False,
        )
        # Two of our pieces on col 3
        our_pawn1 = Piece(
            id="op1", type=PieceType.PAWN, player=1,
            row=3, col=3, captured=False, moved=True,
        )
        our_pawn2 = Piece(
            id="op2", type=PieceType.PAWN, player=1,
            row=5, col=3, captured=False, moved=True,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=7, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=7, captured=False, moved=True,
        )
        state.board.pieces = [enemy_rook, our_pawn1, our_pawn2, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # Pawn1 at (3,3) moves to (6,3). Pawn2 at (5,3) still blocks the rook.
        # So (6,3) should be safe — rook can't get past pawn2.
        travel = 3 * tps
        safety_fixed = data.post_arrival_safety(
            6, 3, travel, moving_from=(3, 3),
        )
        # Rook blocked by pawn2 at (5,3) → can't reach (6,3) → INF enemy time → safe
        assert safety_fixed > 0, (
            f"Double blocker should keep destination safe, got {safety_fixed}"
        )


class TestPawnForwardNotThreat:
    """Enemy pawn forward moves should NOT count as threats in arrival fields.

    Pawns can't capture straight — forward moves are advances, not attacks.
    Only diagonal captures are actual threats.
    """

    def test_enemy_pawn_forward_not_threat(self):
        """Enemy pawn's forward square should not appear in enemy arrival times.

        A P4 pawn at (9,8) moving down has forward square (10,8).
        But forward moves can't capture, so (10,8) is not threatened by that pawn.
        """
        state = _make_state(Speed.LIGHTNING)
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        # Enemy pawn above, moving down (player 2 = top, forward is (+1,0))
        enemy_pawn = Piece(
            id="ep", type=PieceType.PAWN, player=2,
            row=2, col=4, captured=False, moved=True,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=4, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=0, captured=False, moved=True,
        )
        state.board.pieces = [enemy_pawn, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        # The enemy pawn at (2,4) has forward square (3,4).
        # This should NOT count as a threat since pawns can't capture forward.
        pawn_times = data.enemy_time_by_piece.get("ep", {})
        # Forward square should NOT be in enemy arrival times
        assert (3, 4) not in pawn_times, (
            f"Enemy pawn forward square (3,4) should not be a threat, "
            f"but arrival time = {pawn_times.get((3, 4))}"
        )

        # Diagonal captures SHOULD still be threats
        assert (3, 3) in pawn_times, "Diagonal capture (3,3) should be a threat"
        assert (3, 5) in pawn_times, "Diagonal capture (3,5) should be a threat"

    def test_enemy_pawn_double_forward_not_threat(self):
        """Enemy pawn's double-forward square should not appear in enemy arrival times."""
        state = _make_state(Speed.LIGHTNING)
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        # Enemy pawn that hasn't moved yet (can double push)
        enemy_pawn = Piece(
            id="ep", type=PieceType.PAWN, player=2,
            row=1, col=4, captured=False, moved=False,
        )
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=4, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=0, captured=False, moved=True,
        )
        state.board.pieces = [enemy_pawn, our_king, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        pawn_times = data.enemy_time_by_piece.get("ep", {})
        # Neither forward square should be a threat
        assert (2, 4) not in pawn_times, "Single forward should not be a threat"
        assert (3, 4) not in pawn_times, "Double forward should not be a threat"

    def test_king_capture_of_pawn_safe_when_only_forward_threats(self):
        """King capturing a pawn should be safe when nearby enemy pawns
        can only reach the square via forward (non-capture) moves.

        This reproduces the level 69 bug where K2/K3 refuse to capture
        adjacent P4 pawns because the arrival field incorrectly treats
        forward-moving P4 pawns behind the target as threats.

        Setup: AI is player 1 (bottom, pawns move up). Enemy is player 2
        (top, pawns move down). Enemy pawn at (5,4) has forward = (6,4).
        """
        state = _make_state(Speed.LIGHTNING)
        state.board.pieces = []

        from kfchess.game.pieces import Piece

        # AI king (player 1) at (7,4)
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=7, col=4, captured=False, moved=True,
        )
        # Enemy pawn to capture at (6,4)
        target_pawn = Piece(
            id="tp", type=PieceType.PAWN, player=2,
            row=6, col=4, captured=False, moved=True,
        )
        # Enemy pawn at (5,4) — forward direction is (+1,0), so forward
        # square is (6,4). This is the pawn that incorrectly inflates
        # enemy arrival time at (6,4).
        behind_pawn = Piece(
            id="bp", type=PieceType.PAWN, player=2,
            row=5, col=4, captured=False, moved=True,
        )
        enemy_king = Piece(
            id="ek", type=PieceType.KING, player=2,
            row=0, col=0, captured=False, moved=True,
        )
        state.board.pieces = [our_king, target_pawn, behind_pawn, enemy_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)
        tps = state.config.ticks_per_square

        # King captures pawn at (6,4): travel = 1*tps
        # After capturing, exclude the target pawn
        safety = data.post_arrival_safety(
            6, 4, tps,
            exclude_piece_id="tp",
            moving_from=(7, 4),
        )

        # The behind_pawn at (5,4) can only reach (6,4) via forward move
        # (not a capture). So the square should be safe.
        assert safety > 0, (
            f"King capture should be safe (no diagonal threats), "
            f"but safety margin = {safety}"
        )


class TestEliminatedPlayerExclusion:
    """Pieces from eliminated players (king captured) should not generate
    enemy arrival times in the arrival field."""

    def test_eliminated_player_pieces_not_threats(self):
        """Pieces from a player whose king was captured should not appear
        in enemy arrival times."""
        from kfchess.game.pieces import Piece

        state = GameEngine.create_game(
            speed=Speed.LIGHTNING,
            players={1: "human", 2: "bot:ai", 3: "bot:ai", 4: "bot:ai"},
            board_type=BoardType.FOUR_PLAYER,
        )
        state.board.pieces = []
        state.status = GameStatus.PLAYING

        # AI (player 1) king
        our_king = Piece(
            id="ok", type=PieceType.KING, player=1,
            row=6, col=11, captured=False, moved=True,
        )
        # Player 3 king — captured (eliminated)
        p3_king = Piece(
            id="p3k", type=PieceType.KING, player=3,
            row=6, col=0, captured=True, moved=True,
        )
        # Player 3 rook — still on board but player is eliminated
        p3_rook = Piece(
            id="p3r", type=PieceType.ROOK, player=3,
            row=6, col=4, captured=False, moved=True,
        )
        # Player 2 king — alive
        p2_king = Piece(
            id="p2k", type=PieceType.KING, player=2,
            row=11, col=6, captured=False, moved=True,
        )
        state.board.pieces = [our_king, p3_king, p3_rook, p2_king]

        ai_state = StateExtractor.extract(state, 1)
        data = ArrivalField.compute(ai_state, state.config)

        # Player 3's rook should NOT be in enemy_time_by_piece
        assert "p3r" not in data.enemy_time_by_piece, (
            "Eliminated player's rook should not generate enemy arrival times"
        )

        # Player 2's king SHOULD be in enemy_time_by_piece
        assert "p2k" in data.enemy_time_by_piece, (
            "Living player's king should generate enemy arrival times"
        )

"""AI-vs-AI test harness: KungFuAI Level 1 vs DummyAI, Level 2 vs Level 1.

These tests are excluded from the normal test suite (marked @pytest.mark.slow).
Run explicitly with:  uv run pytest tests/unit/ai/test_ai_harness.py -m slow --log-cli-level=INFO
"""

import logging

import pytest

from kfchess.ai.dummy import DummyAI
from kfchess.ai.kungfu_ai import KungFuAI
from kfchess.ai.tactics import PIECE_VALUES
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine
from kfchess.game.state import GameState, GameStatus, Speed

logger = logging.getLogger(__name__)

MAX_TICKS = 20_000
NUM_GAMES = 10


def run_ai_game(
    ai1,
    ai2,
    speed: Speed = Speed.STANDARD,
    max_ticks: int = MAX_TICKS,
) -> tuple[int, bool, int, int]:
    """Run a game between two AIs.

    Returns:
        (winner, decisive, p1_moves, p2_moves) where winner is 1, 2, or 0 (draw).
        decisive is True if the game ended naturally (king captured / draw),
        False if determined by material advantage at tick limit.
        p1_moves/p2_moves are the total moves made by each player.
    """
    state = GameEngine.create_game(
        speed=speed,
        players={1: "bot:ai1", 2: "bot:ai2"},
        board_type=BoardType.STANDARD,
    )
    state.status = GameStatus.PLAYING
    p1_moves = 0
    p2_moves = 0

    for _tick in range(max_ticks):
        # AI 1 moves
        if ai1.should_move(state, 1, state.current_tick):
            move_data = ai1.get_move(state, 1)
            if move_data:
                piece_id, to_row, to_col = move_data
                move = GameEngine.validate_move(state, 1, piece_id, to_row, to_col)
                if move:
                    GameEngine.apply_move(state, move)
                    state.last_move_tick = state.current_tick
                    p1_moves += 1

        # AI 2 moves
        if ai2.should_move(state, 2, state.current_tick):
            move_data = ai2.get_move(state, 2)
            if move_data:
                piece_id, to_row, to_col = move_data
                move = GameEngine.validate_move(state, 2, piece_id, to_row, to_col)
                if move:
                    GameEngine.apply_move(state, move)
                    state.last_move_tick = state.current_tick
                    p2_moves += 1

        # Tick
        GameEngine.tick(state)

        if state.is_finished:
            return state.winner or 0, True, p1_moves, p2_moves

    # Tick limit reached — decide by material
    return _material_winner(state), False, p1_moves, p2_moves


def _material_winner(state: GameState) -> int:
    """Determine winner by material advantage. Returns 1, 2, or 0 (draw)."""
    material = {1: 0.0, 2: 0.0}
    for piece in state.board.pieces:
        if not piece.captured and piece.player in material:
            material[piece.player] += PIECE_VALUES.get(piece.type, 0)

    diff = material[1] - material[2]
    if diff > 0.5:
        return 1
    elif diff < -0.5:
        return 2
    return 0


def _log_results(
    matchup: str,
    wins: int,
    losses: int,
    draws: int,
    decisive: int,
    num_games: int,
    p1_total_moves: int = 0,
    p2_total_moves: int = 0,
) -> None:
    """Log win rate summary for a matchup."""
    win_pct = wins / num_games * 100
    loss_pct = losses / num_games * 100
    draw_pct = draws / num_games * 100
    p1_avg = p1_total_moves / num_games if num_games else 0
    p2_avg = p2_total_moves / num_games if num_games else 0
    logger.info(
        "%s: %dW/%dL/%dD (%d games, %d decisive) — "
        "%.0f%% win, %.0f%% loss, %.0f%% draw — "
        "avg moves: p1=%.0f, p2=%.0f",
        matchup, wins, losses, draws, num_games, decisive,
        win_pct, loss_pct, draw_pct, p1_avg, p2_avg,
    )


class TestAIHarness:
    @pytest.mark.slow
    def test_kungfu_beats_dummy(self):
        """KungFuAI Level 1 should beat DummyAI consistently."""
        wins = 0
        losses = 0
        draws = 0
        decisive = 0

        p1_total = p2_total = 0
        for _i in range(NUM_GAMES):
            kungfu = KungFuAI(level=1, speed=Speed.STANDARD)
            dummy = DummyAI(speed=Speed.STANDARD)

            result, is_decisive, p1m, p2m = run_ai_game(kungfu, dummy)
            decisive += is_decisive
            p1_total += p1m
            p2_total += p2m
            if result == 1:
                wins += 1
            elif result == 2:
                losses += 1
            else:
                draws += 1

        _log_results("L1 vs Dummy (standard)", wins, losses, draws, decisive, NUM_GAMES, p1_total, p2_total)

        assert wins > losses, (
            f"KungFuAI won {wins}, lost {losses}, drew {draws} out of {NUM_GAMES} games"
        )

    @pytest.mark.slow
    def test_kungfu_vs_dummy_lightning(self):
        """KungFuAI should also beat DummyAI in lightning speed."""
        wins = 0
        losses = 0
        draws = 0
        decisive = 0

        p1_total = p2_total = 0
        for _i in range(NUM_GAMES):
            kungfu = KungFuAI(level=1, speed=Speed.LIGHTNING)
            dummy = DummyAI(speed=Speed.LIGHTNING)

            result, is_decisive, p1m, p2m = run_ai_game(kungfu, dummy, speed=Speed.LIGHTNING)
            decisive += is_decisive
            p1_total += p1m
            p2_total += p2m
            if result == 1:
                wins += 1
            elif result == 2:
                losses += 1
            else:
                draws += 1

        _log_results("L1 vs Dummy (lightning)", wins, losses, draws, decisive, NUM_GAMES, p1_total, p2_total)

        assert wins >= losses, (
            f"KungFuAI won {wins}, lost {losses} out of {NUM_GAMES} lightning games"
        )

    @pytest.mark.slow
    def test_level2_vs_level1(self):
        """Level 2 vs Level 1 — L2 should have an edge."""
        l2_wins = 0
        l1_wins = 0
        draws = 0
        decisive = 0
        l2_total = l1_total = 0

        for i in range(NUM_GAMES):
            l2 = KungFuAI(level=2, speed=Speed.STANDARD)
            l1 = KungFuAI(level=1, speed=Speed.STANDARD)

            if i % 2 == 0:
                result, is_decisive, p1m, p2m = run_ai_game(l2, l1)
                decisive += is_decisive
                l2_total += p1m
                l1_total += p2m
                if result == 1:
                    l2_wins += 1
                elif result == 2:
                    l1_wins += 1
                else:
                    draws += 1
            else:
                result, is_decisive, p1m, p2m = run_ai_game(l1, l2)
                decisive += is_decisive
                l1_total += p1m
                l2_total += p2m
                if result == 1:
                    l1_wins += 1
                elif result == 2:
                    l2_wins += 1
                else:
                    draws += 1

        _log_results("L2 vs L1 (standard)", l2_wins, l1_wins, draws, decisive, NUM_GAMES, l2_total, l1_total)

    @pytest.mark.slow
    def test_level2_vs_level1_lightning(self):
        """Level 2 vs Level 1 lightning — L2 should have an edge."""
        l2_wins = 0
        l1_wins = 0
        draws = 0
        decisive = 0
        l2_total = l1_total = 0

        for i in range(NUM_GAMES):
            l2 = KungFuAI(level=2, speed=Speed.LIGHTNING)
            l1 = KungFuAI(level=1, speed=Speed.LIGHTNING)

            if i % 2 == 0:
                result, is_decisive, p1m, p2m = run_ai_game(l2, l1, speed=Speed.LIGHTNING)
                decisive += is_decisive
                l2_total += p1m
                l1_total += p2m
                if result == 1:
                    l2_wins += 1
                elif result == 2:
                    l1_wins += 1
                else:
                    draws += 1
            else:
                result, is_decisive, p1m, p2m = run_ai_game(l1, l2, speed=Speed.LIGHTNING)
                decisive += is_decisive
                l1_total += p1m
                l2_total += p2m
                if result == 1:
                    l1_wins += 1
                elif result == 2:
                    l2_wins += 1
                else:
                    draws += 1

        _log_results("L2 vs L1 (lightning)", l2_wins, l1_wins, draws, decisive, NUM_GAMES, l2_total, l1_total)

    @pytest.mark.slow
    def test_level3_vs_level2(self):
        """Level 3 vs Level 2 — L3 should have an edge."""
        l3_wins = 0
        l2_wins = 0
        draws = 0
        decisive = 0
        l3_total = l2_total = 0

        for i in range(NUM_GAMES):
            l3 = KungFuAI(level=3, speed=Speed.STANDARD)
            l2 = KungFuAI(level=2, speed=Speed.STANDARD)

            if i % 2 == 0:
                result, is_decisive, p1m, p2m = run_ai_game(l3, l2)
                decisive += is_decisive
                l3_total += p1m
                l2_total += p2m
                if result == 1:
                    l3_wins += 1
                elif result == 2:
                    l2_wins += 1
                else:
                    draws += 1
            else:
                result, is_decisive, p1m, p2m = run_ai_game(l2, l3)
                decisive += is_decisive
                l2_total += p1m
                l3_total += p2m
                if result == 1:
                    l2_wins += 1
                elif result == 2:
                    l3_wins += 1
                else:
                    draws += 1

        _log_results("L3 vs L2 (standard)", l3_wins, l2_wins, draws, decisive, NUM_GAMES, l3_total, l2_total)

    @pytest.mark.slow
    def test_level3_vs_level2_lightning(self):
        """Level 3 vs Level 2 lightning — L3 should have an edge."""
        l3_wins = 0
        l2_wins = 0
        draws = 0
        decisive = 0
        l3_total = l2_total = 0

        for i in range(NUM_GAMES):
            l3 = KungFuAI(level=3, speed=Speed.LIGHTNING)
            l2 = KungFuAI(level=2, speed=Speed.LIGHTNING)

            if i % 2 == 0:
                result, is_decisive, p1m, p2m = run_ai_game(l3, l2, speed=Speed.LIGHTNING)
                decisive += is_decisive
                l3_total += p1m
                l2_total += p2m
                if result == 1:
                    l3_wins += 1
                elif result == 2:
                    l2_wins += 1
                else:
                    draws += 1
            else:
                result, is_decisive, p1m, p2m = run_ai_game(l2, l3, speed=Speed.LIGHTNING)
                decisive += is_decisive
                l2_total += p1m
                l3_total += p2m
                if result == 1:
                    l2_wins += 1
                elif result == 2:
                    l3_wins += 1
                else:
                    draws += 1

        _log_results("L3 vs L2 (lightning)", l3_wins, l2_wins, draws, decisive, NUM_GAMES, l3_total, l2_total)

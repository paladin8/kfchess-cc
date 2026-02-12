#!/usr/bin/env python3
"""Benchmark and profile 4-player lightning AI games.

Modes:
  bench   - Quick wall-clock benchmark (no profiling overhead). Runs multiple
            iterations with a fixed seed for reproducible A/B comparisons.
  profile - Single run with cProfile enabled. Shows top functions by
            cumulative and total time.

Usage:
    cd server
    uv run python scripts/profile_4p_ai.py bench [--ticks 3000] [--runs 3]
    uv run python scripts/profile_4p_ai.py profile [--ticks 3000] [--top 30]

Common options:
    --level   AI level 1-3 (default: 3)
    --seed    RNG seed for reproducibility (default: 42)
    --ticks   Max ticks to simulate (default: 3000)
"""

import argparse
import cProfile
import pstats
import random
import time

from kfchess.ai.controller import AIController
from kfchess.game.board import BoardType
from kfchess.game.engine import GameEngine, GameEventType
from kfchess.game.state import Speed


def run_game(max_ticks: int, level: int, seed: int) -> dict:
    """Run a 4-player AI game and return summary stats."""
    random.seed(seed)

    # Use "perf:" prefix to avoid "bot:" early-termination in check_winner
    players = {1: "perf:ai1", 2: "perf:ai2", 3: "perf:ai3", 4: "perf:ai4"}
    state = GameEngine.create_game(
        speed=Speed.LIGHTNING,
        players=players,
        board_type=BoardType.FOUR_PLAYER,
    )

    # Start the game (ready all players)
    for p in players:
        GameEngine.set_player_ready(state, p)

    ais = {p: AIController(level=level, speed=Speed.LIGHTNING, noise=True) for p in players}

    total_moves = 0
    total_captures = 0
    finished = False

    for tick in range(max_ticks):
        # AI moves (shuffled like production)
        ai_items = list(ais.items())
        random.shuffle(ai_items)
        for player_num, ai in ai_items:
            if ai.should_move(state, player_num, state.current_tick):
                move_data = ai.get_move(state, player_num)
                if move_data is not None:
                    piece_id, to_row, to_col = move_data
                    move = GameEngine.validate_move(
                        state, player_num, piece_id, to_row, to_col,
                    )
                    if move is not None:
                        GameEngine.apply_move(state, move)
                        state.last_move_tick = state.current_tick
                        total_moves += 1

        # Tick
        _, events = GameEngine.tick(state)

        for e in events:
            if e.type == GameEventType.CAPTURE:
                total_captures += 1
            if e.type in (GameEventType.GAME_OVER, GameEventType.DRAW):
                finished = True

        if finished:
            break

    return {
        "ticks": state.current_tick,
        "moves": total_moves,
        "captures": total_captures,
        "finished": finished,
        "winner": state.winner,
    }


def format_summary(summary: dict) -> str:
    """Format game summary as a one-line string."""
    parts = [
        f"{summary['ticks']} ticks",
        f"{summary['moves']} moves",
        f"{summary['captures']} captures",
        "finished" if summary["finished"] else "still playing",
    ]
    if summary["winner"]:
        parts.append(f"winner=P{summary['winner']}")
    return ", ".join(parts)


def cmd_bench(args: argparse.Namespace) -> None:
    """Run wall-clock benchmark (no profiling overhead)."""
    print(f"Benchmark: 4P lightning, L{args.level} AI, {args.ticks} ticks, "
          f"seed={args.seed}, {args.runs} run(s)")
    print()

    times = []
    for i in range(args.runs):
        t0 = time.perf_counter()
        summary = run_game(args.ticks, args.level, args.seed)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        ms_per_tick = elapsed / summary["ticks"] * 1000
        print(f"  Run {i+1}: {elapsed:.3f}s = {ms_per_tick:.2f}ms/tick  ({format_summary(summary)})")

    if len(times) > 1:
        avg = sum(times) / len(times)
        avg_ms = avg / args.ticks * 1000
        print(f"\n  Avg: {avg:.3f}s = {avg_ms:.2f}ms/tick")


def cmd_profile(args: argparse.Namespace) -> None:
    """Run with cProfile and print stats."""
    print(f"Profile: 4P lightning, L{args.level} AI, {args.ticks} ticks, seed={args.seed}")
    print()

    profiler = cProfile.Profile()
    profiler.enable()
    summary = run_game(args.ticks, args.level, args.seed)
    profiler.disable()

    print(f"Result: {format_summary(summary)}")
    print()

    stats = pstats.Stats(profiler)
    stats.strip_dirs()

    stats.sort_stats("cumulative")
    print(f"=== Top {args.top} by cumulative time ===")
    stats.print_stats(args.top)

    stats.sort_stats("tottime")
    print(f"=== Top {args.top} by total time ===")
    stats.print_stats(args.top)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark and profile 4-player AI games",
    )
    parser.add_argument("--level", type=int, default=3, help="AI level (1-3)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--ticks", type=int, default=3000, help="Max ticks to simulate")

    sub = parser.add_subparsers(dest="command")

    bench = sub.add_parser("bench", help="Wall-clock benchmark")
    bench.add_argument("--runs", type=int, default=3, help="Number of iterations")

    prof = sub.add_parser("profile", help="cProfile run")
    prof.add_argument("--top", type=int, default=30, help="Top N functions to show")

    args = parser.parse_args()

    if args.command == "bench":
        cmd_bench(args)
    elif args.command == "profile":
        cmd_profile(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

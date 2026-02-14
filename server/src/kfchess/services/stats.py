"""Periodic server stats logging (live games, game-loop CPU usage)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

STATS_INTERVAL_SECONDS = 30

# ---------------------------------------------------------------------------
# Per-game accumulator
# ---------------------------------------------------------------------------

@dataclass
class _GameStats:
    compute_ns: int = 0
    ai_ns: int = 0
    engine_ns: int = 0
    tick_count: int = 0


# ---------------------------------------------------------------------------
# Global counters (single-threaded asyncio — no locks needed)
# ---------------------------------------------------------------------------

_total_compute_ns: int = 0
_total_ai_ns: int = 0
_total_engine_ns: int = 0
_total_tick_count: int = 0
_per_game: dict[str, _GameStats] = {}
_last_report_ns: int = 0


def record_tick(game_id: str, compute_ns: int, ai_ns: int, engine_ns: int) -> None:
    """Record timing for one game-loop tick."""
    global _total_compute_ns, _total_ai_ns, _total_engine_ns, _total_tick_count

    _total_compute_ns += compute_ns
    _total_ai_ns += ai_ns
    _total_engine_ns += engine_ns
    _total_tick_count += 1

    gs = _per_game.get(game_id)
    if gs is None:
        gs = _GameStats()
        _per_game[game_id] = gs
    gs.compute_ns += compute_ns
    gs.ai_ns += ai_ns
    gs.engine_ns += engine_ns
    gs.tick_count += 1


# ---------------------------------------------------------------------------
# Periodic logging loop
# ---------------------------------------------------------------------------

_stats_task: asyncio.Task | None = None


def _format_report() -> str:
    """Build the log line and reset counters."""
    global _total_compute_ns, _total_ai_ns, _total_engine_ns, _total_tick_count, _last_report_ns

    now_ns = time.monotonic_ns()
    wall_ns = now_ns - _last_report_ns if _last_report_ns else STATS_INTERVAL_SECONDS * 1_000_000_000

    # Snapshot and reset global counters
    compute_ns = _total_compute_ns
    ai_ns = _total_ai_ns
    engine_ns = _total_engine_ns
    tick_count = _total_tick_count
    _total_compute_ns = 0
    _total_ai_ns = 0
    _total_engine_ns = 0
    _total_tick_count = 0
    _last_report_ns = now_ns

    # Compute CPU %
    compute_pct = compute_ns / wall_ns * 100 if wall_ns else 0.0
    ai_pct = ai_ns / wall_ns * 100 if wall_ns else 0.0
    engine_pct = engine_ns / wall_ns * 100 if wall_ns else 0.0

    # Count live games
    from kfchess.game.state import GameStatus
    from kfchess.services.game_service import get_game_service

    service = get_game_service()
    live_ids: set[str] = set()
    for gid, mg in service.games.items():
        if mg.state.status in (GameStatus.PLAYING, GameStatus.WAITING):
            live_ids.add(gid)
    total_live = len(live_ids)

    # Top 3 games by compute time
    top_games = sorted(_per_game.items(), key=lambda kv: kv[1].compute_ns, reverse=True)[:3]
    if top_games:
        top_parts = []
        for gid, gs in top_games:
            pct = gs.compute_ns / wall_ns * 100 if wall_ns else 0.0
            short_id = gid[:8]
            top_parts.append(f"{short_id}({pct:.1f}%)")
        top_str = f" | top: {' '.join(top_parts)}"
    else:
        top_str = ""

    # Prune dead games from per-game stats
    dead = [gid for gid in _per_game if gid not in live_ids]
    for gid in dead:
        del _per_game[gid]
    # Reset surviving per-game counters
    for gs in _per_game.values():
        gs.compute_ns = 0
        gs.ai_ns = 0
        gs.engine_ns = 0
        gs.tick_count = 0

    return (
        f"Stats: {total_live} live games"
        f" | tick cpu: {compute_pct:.1f}% (ai: {ai_pct:.1f}%, engine: {engine_pct:.1f}%)"
        f" | {tick_count} ticks{top_str}"
    )


async def _stats_loop() -> None:
    """Background loop that periodically logs server stats."""
    global _last_report_ns
    _last_report_ns = time.monotonic_ns()
    try:
        while True:
            await asyncio.sleep(STATS_INTERVAL_SECONDS)
            try:
                msg = _format_report()
                logger.info(msg)
            except Exception:
                logger.exception("Error in stats reporting")
    except asyncio.CancelledError:
        raise


async def start_stats_loop() -> None:
    """Start the periodic stats logging task."""
    global _stats_task
    if _stats_task is not None and not _stats_task.done():
        return
    _stats_task = asyncio.create_task(_stats_loop())
    logger.info(f"Stats loop started (interval={STATS_INTERVAL_SECONDS}s)")


async def stop_stats_loop() -> None:
    """Stop the periodic stats logging task."""
    global _stats_task
    if _stats_task is not None and not _stats_task.done():
        _stats_task.cancel()
        try:
            await _stats_task
        except asyncio.CancelledError:
            pass
    _stats_task = None
    logger.info("Stats loop stopped")

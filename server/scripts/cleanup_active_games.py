#!/usr/bin/env python
"""Clean up stale active games from both PostgreSQL and Redis.

Removes active_games rows older than X minutes and their corresponding
Redis keys (snapshots + routing), preventing them from being restored
on next server startup.

Usage:
    cd server
    uv run python scripts/cleanup_active_games.py             # dry run (default: 30 min)
    uv run python scripts/cleanup_active_games.py --commit    # actually delete
    uv run python scripts/cleanup_active_games.py --minutes 5 # games older than 5 min
    uv run python scripts/cleanup_active_games.py --all       # all active games
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add the src directory to the path so we can import kfchess
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import redis.asyncio as aioredis
from sqlalchemy import delete, select

from kfchess.db.models import ActiveGame
from kfchess.db.session import async_session_factory
from kfchess.settings import get_settings


async def _scan_redis_snapshot_ids(r: aioredis.Redis) -> list[str]:
    """Scan Redis for all game IDs that have snapshot keys."""
    game_ids: list[str] = []
    prefix = "game:"
    suffix = ":snapshot"
    async for key in r.scan_iter(match="game:*:snapshot", count=100):
        game_id = key[len(prefix) : -len(suffix)]
        game_ids.append(game_id)
    return game_ids


async def _load_snapshot_time(r: aioredis.Redis, game_id: str) -> float:
    """Load a snapshot's timestamp from Redis without full deserialization.

    Returns 0.0 if snapshot doesn't exist or can't be parsed.
    """
    data = await r.get(f"game:{game_id}:snapshot")
    if data is None:
        return 0.0
    try:
        return json.loads(data).get("snapshot_time", 0.0)
    except (json.JSONDecodeError, AttributeError):
        return 0.0


async def cleanup(minutes: int | None, dry_run: bool) -> None:
    """Remove stale active games from DB and Redis.

    Uses Redis snapshot_time as the primary staleness signal (not the DB
    started_at, which can be reset by server restarts). Also cleans up
    DB rows for games whose snapshots are stale, and orphaned snapshots
    with no DB row.
    """
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        async with async_session_factory() as session:
            now = time.time()
            cutoff_seconds = minutes * 60 if minutes is not None else 0

            # Scan all Redis snapshots and check actual snapshot_time
            all_snapshot_ids = await _scan_redis_snapshot_ids(r)
            stale_snapshot_ids: list[tuple[str, float]] = []  # (game_id, age_seconds)
            for gid in all_snapshot_ids:
                snap_time = await _load_snapshot_time(r, gid)
                if minutes is None:
                    # --all: every snapshot is stale
                    stale_snapshot_ids.append((gid, now - snap_time if snap_time > 0 else 0))
                elif snap_time > 0 and (now - snap_time) > cutoff_seconds:
                    stale_snapshot_ids.append((gid, now - snap_time))
                elif snap_time == 0:
                    # Can't determine age (legacy snapshot) — treat as stale
                    stale_snapshot_ids.append((gid, 0))
            stale_game_ids = {gid for gid, _ in stale_snapshot_ids}

            # Find DB rows to clean up: rows matching the age filter OR
            # rows whose Redis snapshot is stale
            query = select(ActiveGame).order_by(ActiveGame.started_at)
            if minutes is not None:
                db_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes)
                query = query.where(
                    (ActiveGame.started_at < db_cutoff) | ActiveGame.game_id.in_(stale_game_ids)
                )

            result = await session.execute(query)
            games = list(result.scalars().all())
            db_game_ids = {g.game_id for g in games}

            # Orphaned snapshots: stale snapshots with no DB row
            orphaned_ids = [gid for gid in stale_game_ids if gid not in db_game_ids]

            # Combine everything to clean from Redis
            all_ids_to_clean = db_game_ids | stale_game_ids

            if not games and not orphaned_ids:
                print("No active games or orphaned snapshots to clean up.")
                return

            # Display DB games to remove
            if games:
                print(f"{'[DRY RUN] ' if dry_run else ''}Found {len(games)} DB game(s) to remove:\n")
                for g in games:
                    age = datetime.now(UTC).replace(tzinfo=None) - g.started_at
                    age_str = f"{int(age.total_seconds() // 60)}m{int(age.total_seconds() % 60)}s"
                    print(f"  {g.game_id}  type={g.game_type}  speed={g.speed}  "
                          f"players={g.player_count}  age={age_str}  server={g.server_id}")

            # Display orphaned snapshots
            if orphaned_ids:
                print(f"\n{'[DRY RUN] ' if dry_run else ''}Found {len(orphaned_ids)} orphaned Redis snapshot(s) (no DB row):\n")
                for gid in orphaned_ids:
                    print(f"  {gid}")

            if dry_run:
                total = len(games) + len(orphaned_ids)
                print(f"\n[DRY RUN] Would remove {total} game(s)/snapshot(s). "
                      "Run with --commit to execute.")
                return

            # Delete from database
            if games:
                ids_to_delete = [g.game_id for g in games]
                await session.execute(
                    delete(ActiveGame).where(ActiveGame.game_id.in_(ids_to_delete))
                )
                await session.commit()
                print(f"\nDeleted {len(ids_to_delete)} row(s) from active_games table.")

            # Delete Redis keys for all identified stale games
            redis_deleted = 0
            for gid in all_ids_to_clean:
                keys = [f"game:{gid}:snapshot", f"game:{gid}:server"]
                redis_deleted += await r.delete(*keys)
            print(f"Deleted {redis_deleted} Redis key(s) (snapshots + routing).")

    finally:
        await r.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean up stale active games from PostgreSQL and Redis."
    )
    parser.add_argument(
        "--minutes", type=int, default=30,
        help="Remove games older than this many minutes (default: 30)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Remove ALL active games regardless of age",
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually delete (default is dry run)",
    )
    args = parser.parse_args()

    dry_run = not args.commit
    minutes = None if args.all else args.minutes
    label = "all active games" if args.all else f"active games older than {args.minutes} minutes"
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Cleaning up {label}...\n")

    try:
        asyncio.run(cleanup(minutes, dry_run))
        print("\nDone!")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

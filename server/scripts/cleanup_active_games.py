#!/usr/bin/env python
"""Clean up stale active games from both PostgreSQL and Redis.

Removes active_games rows older than X minutes and their corresponding
Redis keys (snapshots + routing), preventing them from being restored
on next server startup.

Usage:
    cd server
    uv run python scripts/cleanup_active_games.py           # default: 30 minutes
    uv run python scripts/cleanup_active_games.py --minutes 5
    uv run python scripts/cleanup_active_games.py --all      # remove ALL active games
    uv run python scripts/cleanup_active_games.py --dry-run  # preview without deleting
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add the src directory to the path so we can import kfchess
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import redis.asyncio as aioredis
from sqlalchemy import delete, select

from kfchess.db.models import ActiveGame
from kfchess.db.session import async_session_factory
from kfchess.settings import get_settings


async def cleanup(minutes: int | None, dry_run: bool) -> None:
    """Remove stale active games from DB and Redis."""
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        async with async_session_factory() as session:
            # Find games to clean up
            query = select(ActiveGame).order_by(ActiveGame.started_at)
            if minutes is not None:
                cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes)
                query = query.where(ActiveGame.started_at < cutoff)

            result = await session.execute(query)
            games = list(result.scalars().all())

            if not games:
                print("No active games to clean up.")
                return

            # Display what will be removed
            print(f"{'[DRY RUN] ' if dry_run else ''}Found {len(games)} game(s) to remove:\n")
            for g in games:
                age = datetime.now(UTC).replace(tzinfo=None) - g.started_at
                age_str = f"{int(age.total_seconds() // 60)}m{int(age.total_seconds() % 60)}s"
                print(f"  {g.game_id}  type={g.game_type}  speed={g.speed}  "
                      f"players={g.player_count}  age={age_str}  server={g.server_id}")

            if dry_run:
                print(f"\n[DRY RUN] Would remove {len(games)} game(s). "
                      "Run without --dry-run to execute.")
                return

            # Delete from database
            game_ids = [g.game_id for g in games]
            await session.execute(
                delete(ActiveGame).where(ActiveGame.game_id.in_(game_ids))
            )
            await session.commit()
            print(f"\nDeleted {len(game_ids)} row(s) from active_games table.")

            # Delete Redis keys (snapshot + routing)
            redis_deleted = 0
            for gid in game_ids:
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
        "--dry-run", action="store_true",
        help="Show what would be removed without deleting",
    )
    args = parser.parse_args()

    minutes = None if args.all else args.minutes
    label = "all active games" if args.all else f"active games older than {args.minutes} minutes"
    print(f"Cleaning up {label}...\n")

    try:
        asyncio.run(cleanup(minutes, args.dry_run))
        print("\nDone!")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

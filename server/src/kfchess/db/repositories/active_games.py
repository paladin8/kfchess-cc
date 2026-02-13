"""Active games repository for database operations."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.db.models import ActiveGame

logger = logging.getLogger(__name__)


class ActiveGameRepository:
    """Repository for managing the active games registry."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self,
        game_id: str,
        game_type: str,
        speed: str,
        player_count: int,
        board_type: str,
        players: list[dict],
        server_id: str,
        lobby_code: str | None = None,
        campaign_level_id: int | None = None,
        started_at: datetime | None = None,
    ) -> None:
        """Register an active game (upsert).

        Uses INSERT ... ON CONFLICT UPDATE so that restored games
        overwrite stale rows left by a crashed server.
        """
        values: dict = {
            "game_id": game_id,
            "game_type": game_type,
            "speed": speed,
            "player_count": player_count,
            "board_type": board_type,
            "players": players,
            "lobby_code": lobby_code,
            "campaign_level_id": campaign_level_id,
            "server_id": server_id,
        }
        if started_at is not None:
            # DB column is TIMESTAMP WITHOUT TIME ZONE; strip tzinfo to
            # avoid asyncpg "can't subtract offset-naive and offset-aware" error
            values["started_at"] = started_at.replace(tzinfo=None)
        stmt = pg_insert(ActiveGame).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["game_id"],
            set_={
                "game_type": stmt.excluded.game_type,
                "speed": stmt.excluded.speed,
                "player_count": stmt.excluded.player_count,
                "board_type": stmt.excluded.board_type,
                "players": stmt.excluded.players,
                "lobby_code": stmt.excluded.lobby_code,
                "campaign_level_id": stmt.excluded.campaign_level_id,
                "server_id": stmt.excluded.server_id,
                # started_at intentionally omitted — preserve the original
            },
        )
        await self.session.execute(stmt)
        logger.info(f"Registered active game {game_id} (type={game_type})")

    async def deregister(self, game_id: str) -> bool:
        """Remove a game from the active registry. Returns True if removed."""
        result = await self.session.execute(
            delete(ActiveGame).where(ActiveGame.game_id == game_id)
        )
        removed = result.rowcount > 0
        if removed:
            logger.info(f"Deregistered active game {game_id}")
        return removed

    async def list_active(
        self,
        speed: str | None = None,
        player_count: int | None = None,
        game_type: str | None = None,
        limit: int = 50,
    ) -> list[ActiveGame]:
        """List active games with optional filters."""
        query = select(ActiveGame).order_by(ActiveGame.started_at.desc()).limit(limit)
        if speed:
            query = query.where(ActiveGame.speed == speed)
        if player_count:
            query = query.where(ActiveGame.player_count == player_count)
        if game_type:
            query = query.where(ActiveGame.game_type == game_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def cleanup_stale(self, max_age_hours: int = 2) -> int:
        """Remove entries older than max_age_hours (crash recovery)."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=max_age_hours)
        result = await self.session.execute(
            delete(ActiveGame).where(ActiveGame.started_at < cutoff)
        )
        count = result.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} stale active game entries")
        return count

    async def cleanup_by_server(self, server_id: str) -> int:
        """Remove all entries for a specific server (server restart cleanup)."""
        result = await self.session.execute(
            delete(ActiveGame).where(ActiveGame.server_id == server_id)
        )
        count = result.rowcount
        if count > 0:
            logger.info(
                f"Cleaned up {count} active game entries for server {server_id}"
            )
        return count

"""Replay repository for database operations."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from kfchess.db.models import GameHistory, GameReplay
from kfchess.game.board import BoardType
from kfchess.game.replay import Replay
from kfchess.game.state import ReplayMove, Speed

logger = logging.getLogger(__name__)


MAX_BROWSEABLE = 100


class ReplayRepository:
    """Repository for managing game replays in the database."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The database session to use
        """
        self.session = session

    async def save(self, game_id: str, replay: Replay) -> GameReplay:
        """Save a replay to the database.

        If a replay already exists for this game_id, it will be skipped
        (idempotent operation to handle concurrent saves).

        Args:
            game_id: The game ID (used as primary key)
            replay: The replay data to save

        Returns:
            The created or existing GameReplay record
        """
        # Check if replay already exists (idempotent - handle concurrent saves)
        existing = await self.get_by_id(game_id)
        if existing is not None:
            logger.info(f"Replay for game {game_id} already exists, skipping save")
            # Return the existing record by fetching it
            result = await self.session.execute(
                select(GameReplay).where(GameReplay.id == game_id)
            )
            return result.scalar_one()

        # Convert moves to serializable format
        moves_data = [
            {
                "tick": m.tick,
                "piece_id": m.piece_id,
                "to_row": m.to_row,
                "to_col": m.to_col,
                "player": m.player,
            }
            for m in replay.moves
        ]

        # Convert players dict keys to strings for JSON
        players_data = {str(k): v for k, v in replay.players.items()}

        # Convert timezone-aware datetime to naive UTC for database
        created_at = replay.created_at or datetime.now(UTC)
        if created_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=None)

        record = GameReplay(
            id=game_id,
            speed=replay.speed.value,
            board_type=replay.board_type.value,
            players=players_data,
            moves=moves_data,
            total_ticks=replay.total_ticks,
            winner=replay.winner,
            win_reason=replay.win_reason,
            created_at=created_at,
            is_public=True,
            tick_rate_hz=replay.tick_rate_hz,
            is_ranked=replay.is_ranked,
            campaign_level_id=replay.campaign_level_id,
            initial_board_str=replay.initial_board_str,
        )

        self.session.add(record)
        await self.session.flush()

        logger.info(f"Saved replay for game {game_id} ({len(replay.moves)} moves)")
        return record

    async def get_by_id(self, game_id: str) -> Replay | None:
        """Get a replay by game ID.

        Checks game_replays first, then falls back to legacy game_history table
        for replays imported from the original kfchess.

        Args:
            game_id: The game ID

        Returns:
            Replay data or None if not found
        """
        result = await self.session.execute(
            select(GameReplay).where(GameReplay.id == game_id)
        )
        record = result.scalar_one_or_none()

        if record is not None:
            return self._record_to_replay(record)

        # Fall back to legacy game_history table
        return await self._get_legacy_by_id(game_id)

    async def _get_legacy_by_id(self, game_id: str) -> Replay | None:
        """Get a replay from the legacy game_history table.

        Args:
            game_id: The game history ID (numeric string)

        Returns:
            Replay data converted from V1 format, or None if not found
        """
        try:
            history_id = int(game_id)
        except ValueError:
            return None

        result = await self.session.execute(
            select(GameHistory).where(GameHistory.id == history_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            return None

        logger.info(f"Loaded legacy replay from game_history: id={game_id}")
        return Replay.from_dict(record.replay)

    async def exists(self, game_id: str) -> bool:
        """Check if a replay exists.

        Args:
            game_id: The game ID

        Returns:
            True if replay exists
        """
        result = await self.session.execute(
            select(GameReplay.id).where(GameReplay.id == game_id)
        )
        return result.scalar_one_or_none() is not None

    async def list_recent(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[tuple[str, Replay]], int]:
        """List recent replays with their IDs and total count.

        Caps results at MAX_BROWSEABLE (100) total rows. Uses a subquery
        to avoid scanning the entire table for the count.

        Args:
            limit: Maximum number of replays to return
            offset: Number of replays to skip

        Returns:
            Tuple of (list of (game_id, replay) tuples, total count)
        """
        # Subquery: fetch at most MAX_BROWSEABLE recent public replays
        base = (
            select(GameReplay)
            .where(GameReplay.is_public.is_(True))
            .order_by(GameReplay.created_at.desc())
            .limit(MAX_BROWSEABLE)
            .subquery()
        )
        capped = aliased(GameReplay, base)
        total_count = func.count().over().label("total_count")

        result = await self.session.execute(
            select(capped, total_count)
            .order_by(capped.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = result.all()

        total = rows[0].total_count if rows else 0
        replays = [(row[0].id, self._record_to_replay(row[0])) for row in rows]
        return replays, total

    async def list_top(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[tuple[str, Replay, int]], int]:
        """List top replays by like count with total count.

        Only returns replays with at least one like. Caps results at
        MAX_BROWSEABLE (100) total rows.

        Args:
            limit: Maximum number of replays to return
            offset: Number of replays to skip

        Returns:
            Tuple of (list of (game_id, replay, like_count) tuples, total count)
        """
        # Subquery: fetch at most MAX_BROWSEABLE top public replays with likes
        base = (
            select(GameReplay)
            .where(GameReplay.is_public.is_(True))
            .where(GameReplay.like_count > 0)
            .order_by(GameReplay.like_count.desc(), GameReplay.created_at.desc())
            .limit(MAX_BROWSEABLE)
            .subquery()
        )
        capped = aliased(GameReplay, base)
        total_count = func.count().over().label("total_count")

        result = await self.session.execute(
            select(capped, total_count)
            .order_by(capped.like_count.desc(), capped.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = result.all()

        total = rows[0].total_count if rows else 0
        replays = [
            (row[0].id, self._record_to_replay(row[0]), row[0].like_count)
            for row in rows
        ]
        return replays, total

    async def get_like_count(self, game_id: str) -> int:
        """Get the like count for a replay.

        Args:
            game_id: The game ID

        Returns:
            The like count, or 0 if replay not found
        """
        result = await self.session.execute(
            select(GameReplay.like_count).where(GameReplay.id == game_id)
        )
        count = result.scalar_one_or_none()
        return count if count is not None else 0

    async def get_like_counts_batch(self, game_ids: list[str]) -> dict[str, int]:
        """Get like counts for multiple replays in a single query.

        Args:
            game_ids: List of game IDs to fetch

        Returns:
            Dict mapping game_id to like_count (missing IDs get 0)
        """
        if not game_ids:
            return {}

        result = await self.session.execute(
            select(GameReplay.id, GameReplay.like_count).where(
                GameReplay.id.in_(game_ids)
            )
        )
        counts = {row[0]: row[1] for row in result.fetchall()}
        # Return 0 for any missing IDs
        return {gid: counts.get(gid, 0) for gid in game_ids}

    async def delete(self, game_id: str) -> bool:
        """Delete a replay.

        Args:
            game_id: The game ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            select(GameReplay).where(GameReplay.id == game_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            return False

        await self.session.delete(record)
        await self.session.flush()

        logger.info(f"Deleted replay for game {game_id}")
        return True

    def _record_to_replay(self, record: GameReplay) -> Replay:
        """Convert a database record to a Replay object.

        Args:
            record: The database record to convert

        Returns:
            Replay object

        Raises:
            ValueError: If the record contains invalid or corrupt data
        """
        try:
            # Parse players dict (keys are strings in JSON)
            players = {int(k): v for k, v in record.players.items()}
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid players data in replay {record.id}: {e}")
            raise ValueError(f"Corrupt players data in replay {record.id}") from e

        # Parse moves with validation
        moves = []
        for i, m in enumerate(record.moves):
            try:
                moves.append(
                    ReplayMove(
                        tick=m["tick"],
                        piece_id=m["piece_id"],
                        to_row=m["to_row"],
                        to_col=m["to_col"],
                        player=m["player"],
                    )
                )
            except (KeyError, TypeError) as e:
                logger.error(
                    f"Invalid move data at index {i} in replay {record.id}: "
                    f"move={m}, error={e}"
                )
                raise ValueError(
                    f"Corrupt move data at index {i} in replay {record.id}"
                ) from e

        try:
            # Get tick_rate_hz with default of 10 for old replays without this field
            tick_rate_hz = getattr(record, "tick_rate_hz", 10) or 10
            # Get is_ranked with default of False for old replays
            is_ranked = getattr(record, "is_ranked", False) or False
            # Get campaign_level_id (None for non-campaign games)
            campaign_level_id = getattr(record, "campaign_level_id", None)
            # Get initial_board_str (None for non-campaign games)
            initial_board_str = getattr(record, "initial_board_str", None)
            return Replay(
                version=2,
                speed=Speed(record.speed),
                board_type=BoardType(record.board_type),
                players=players,
                moves=moves,
                total_ticks=record.total_ticks,
                winner=record.winner,
                win_reason=record.win_reason,
                created_at=record.created_at,
                tick_rate_hz=tick_rate_hz,
                is_ranked=is_ranked,
                campaign_level_id=campaign_level_id,
                initial_board_str=initial_board_str,
            )
        except ValueError as e:
            logger.error(f"Invalid enum value in replay {record.id}: {e}")
            raise ValueError(f"Invalid speed or board_type in replay {record.id}") from e

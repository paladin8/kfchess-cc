"""Replay repository for database operations."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.db.models import GameReplay
from kfchess.game.board import BoardType
from kfchess.game.replay import Replay
from kfchess.game.state import ReplayMove, Speed

logger = logging.getLogger(__name__)


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

        record = GameReplay(
            id=game_id,
            speed=replay.speed.value,
            board_type=replay.board_type.value,
            players=players_data,
            moves=moves_data,
            total_ticks=replay.total_ticks,
            winner=replay.winner,
            win_reason=replay.win_reason,
            created_at=replay.created_at or datetime.now(),
            is_public=True,
        )

        self.session.add(record)
        await self.session.flush()

        logger.info(f"Saved replay for game {game_id} ({len(replay.moves)} moves)")
        return record

    async def get_by_id(self, game_id: str) -> Replay | None:
        """Get a replay by game ID.

        Args:
            game_id: The game ID

        Returns:
            Replay data or None if not found
        """
        result = await self.session.execute(
            select(GameReplay).where(GameReplay.id == game_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            return None

        return self._record_to_replay(record)

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

    async def list_recent(self, limit: int = 20, offset: int = 0) -> list[Replay]:
        """List recent replays.

        Args:
            limit: Maximum number of replays to return
            offset: Number of replays to skip

        Returns:
            List of replays ordered by creation time (newest first)
        """
        result = await self.session.execute(
            select(GameReplay)
            .where(GameReplay.is_public.is_(True))
            .order_by(GameReplay.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        records = result.scalars().all()

        return [self._record_to_replay(r) for r in records]

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
            )
        except ValueError as e:
            logger.error(f"Invalid enum value in replay {record.id}: {e}")
            raise ValueError(f"Invalid speed or board_type in replay {record.id}") from e

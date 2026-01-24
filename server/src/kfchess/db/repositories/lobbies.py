"""Lobby repository for database operations."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kfchess.db.models import Lobby as LobbyModel
from kfchess.db.models import LobbyPlayer as LobbyPlayerModel
from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus

logger = logging.getLogger(__name__)


class LobbyRepository:
    """Repository for managing lobbies in the database."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The database session to use
        """
        self.session = session

    async def save(self, lobby: Lobby) -> LobbyModel:
        """Save or update a lobby in the database.

        Args:
            lobby: The lobby domain object to save

        Returns:
            The created or updated LobbyModel record
        """
        # Check if lobby already exists by code (unique identifier)
        result = await self.session.execute(
            select(LobbyModel)
            .where(LobbyModel.code == lobby.code)
            .options(selectinload(LobbyModel.players))
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            # Update existing lobby
            existing.speed = lobby.settings.speed
            existing.player_count = lobby.settings.player_count
            existing.is_public = lobby.settings.is_public
            existing.is_ranked = lobby.settings.is_ranked
            existing.status = lobby.status.value
            existing.game_id = lobby.current_game_id

            # Update players - clear existing (cascade delete handles removal)
            existing.players.clear()
            await self.session.flush()

            # Then add new players
            for _slot, player in lobby.players.items():
                player_record = self._player_to_model(existing.id, player)
                self.session.add(player_record)

            await self.session.flush()
            logger.debug(f"Updated lobby {lobby.code} in database")
            return existing

        # Create new lobby record
        # Find the host user_id
        host = lobby.host
        host_id = host.user_id if host else None

        # Let DB auto-generate the ID
        record = LobbyModel(
            code=lobby.code,
            host_id=host_id,
            speed=lobby.settings.speed,
            player_count=lobby.settings.player_count,
            is_public=lobby.settings.is_public,
            is_ranked=lobby.settings.is_ranked,
            status=lobby.status.value,
            game_id=lobby.current_game_id,
            created_at=lobby.created_at,
        )

        self.session.add(record)
        await self.session.flush()  # Flush to get the generated ID

        # Add players using the generated ID
        for _slot, player in lobby.players.items():
            player_record = self._player_to_model(record.id, player)
            self.session.add(player_record)

        await self.session.flush()

        logger.info(f"Saved lobby {lobby.code} to database")
        return record

    async def get_by_id(self, lobby_id: int) -> Lobby | None:
        """Get a lobby by ID.

        Args:
            lobby_id: The lobby ID

        Returns:
            Lobby domain object or None if not found
        """
        result = await self.session.execute(
            select(LobbyModel)
            .where(LobbyModel.id == lobby_id)
            .options(selectinload(LobbyModel.players))
        )
        record = result.scalar_one_or_none()

        if record is None:
            return None

        return self._model_to_lobby(record)

    async def get_by_code(self, code: str) -> Lobby | None:
        """Get a lobby by code.

        Args:
            code: The lobby code

        Returns:
            Lobby domain object or None if not found
        """
        result = await self.session.execute(
            select(LobbyModel)
            .where(LobbyModel.code == code)
            .options(selectinload(LobbyModel.players))
        )
        record = result.scalar_one_or_none()

        if record is None:
            return None

        return self._model_to_lobby(record)

    async def exists(self, lobby_id: int) -> bool:
        """Check if a lobby exists.

        Args:
            lobby_id: The lobby ID

        Returns:
            True if lobby exists
        """
        result = await self.session.execute(
            select(LobbyModel.id).where(LobbyModel.id == lobby_id)
        )
        return result.scalar_one_or_none() is not None

    async def delete(self, lobby_id: int) -> bool:
        """Delete a lobby.

        Args:
            lobby_id: The lobby ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            select(LobbyModel)
            .where(LobbyModel.id == lobby_id)
            .options(selectinload(LobbyModel.players))
        )
        record = result.scalar_one_or_none()

        if record is None:
            return False

        await self.session.delete(record)
        await self.session.flush()

        logger.info(f"Deleted lobby {record.code} from database")
        return True

    async def delete_by_code(self, code: str) -> bool:
        """Delete a lobby by code.

        Args:
            code: The lobby code

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            select(LobbyModel)
            .where(LobbyModel.code == code)
            .options(selectinload(LobbyModel.players))
        )
        record = result.scalar_one_or_none()

        if record is None:
            return False

        await self.session.delete(record)
        await self.session.flush()

        logger.info(f"Deleted lobby {code} from database")
        return True

    async def list_public_waiting(
        self,
        speed: str | None = None,
        player_count: int | None = None,
        limit: int = 50,
    ) -> list[Lobby]:
        """List public lobbies that are waiting for players.

        Args:
            speed: Filter by game speed
            player_count: Filter by player count
            limit: Maximum number of lobbies to return

        Returns:
            List of Lobby domain objects
        """
        query = (
            select(LobbyModel)
            .where(LobbyModel.is_public.is_(True))
            .where(LobbyModel.status == "waiting")
            .options(selectinload(LobbyModel.players))
            .order_by(LobbyModel.created_at.desc())
            .limit(limit)
        )

        if speed:
            query = query.where(LobbyModel.speed == speed)
        if player_count:
            query = query.where(LobbyModel.player_count == player_count)

        result = await self.session.execute(query)
        records = result.scalars().all()

        return [self._model_to_lobby(r) for r in records]

    async def update_status(
        self,
        lobby_id: int,
        status: LobbyStatus,
        game_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> bool:
        """Update lobby status.

        Args:
            lobby_id: The lobby ID
            status: New status
            game_id: Optional game ID (for IN_GAME status)
            started_at: Optional game start time
            finished_at: Optional game finish time

        Returns:
            True if updated, False if not found
        """
        result = await self.session.execute(
            select(LobbyModel).where(LobbyModel.id == lobby_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            return False

        record.status = status.value
        if game_id is not None:
            record.game_id = game_id
        if started_at is not None:
            record.started_at = started_at
        if finished_at is not None:
            record.finished_at = finished_at

        await self.session.flush()
        return True

    def _player_to_model(self, lobby_id: int, player: LobbyPlayer) -> LobbyPlayerModel:
        """Convert a LobbyPlayer domain object to a database model.

        Args:
            lobby_id: The lobby ID
            player: The player domain object

        Returns:
            LobbyPlayerModel database record
        """
        return LobbyPlayerModel(
            lobby_id=lobby_id,
            user_id=player.user_id,
            guest_id=None,  # TODO: Track guest IDs
            player_slot=player.slot,
            username=player.username,
            is_ready=player.is_ready,
            is_ai=player.is_ai,
            ai_type=player.ai_type,
            joined_at=player.joined_at,
        )

    def _model_to_lobby(self, record: LobbyModel) -> Lobby:
        """Convert a database record to a Lobby domain object.

        Args:
            record: The database record

        Returns:
            Lobby domain object
        """
        # Build settings
        settings = LobbySettings(
            is_public=record.is_public,
            speed=record.speed,
            player_count=record.player_count,
            is_ranked=record.is_ranked,
        )

        # Build players dict
        players: dict[int, LobbyPlayer] = {}
        host_slot = 1  # Default
        for player_record in record.players:
            player = LobbyPlayer(
                slot=player_record.player_slot,
                user_id=player_record.user_id,
                username=player_record.username,
                is_ai=player_record.is_ai,
                ai_type=player_record.ai_type,
                joined_at=player_record.joined_at,
            )
            player.is_ready = player_record.is_ready
            players[player_record.player_slot] = player

            # The host is the user that matches the lobby's host_id
            if record.host_id and player_record.user_id == record.host_id:
                host_slot = player_record.player_slot

        # If no host found by user_id, default to slot 1
        if record.host_id is None and 1 in players:
            host_slot = 1

        return Lobby(
            id=record.id,
            code=record.code,
            host_slot=host_slot,
            settings=settings,
            players=players,
            status=LobbyStatus(record.status),
            current_game_id=record.game_id,
            games_played=0,  # Not tracked in DB yet
            created_at=record.created_at,
            game_finished_at=record.finished_at,
        )

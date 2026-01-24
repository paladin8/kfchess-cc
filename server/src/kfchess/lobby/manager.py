"""Lobby manager for Kung Fu Chess.

This module provides the LobbyManager class which manages all active lobbies
in memory. Lobbies are used as waiting rooms where players gather before
starting a game.

Optionally supports database persistence when a session factory is provided.
"""

import asyncio
import logging
import random
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Characters for lobby codes (excluding ambiguous: O/0, I/1/L)
LOBBY_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LOBBY_CODE_LENGTH = 6


def _generate_lobby_code() -> str:
    """Generate a random lobby code."""
    return "".join(random.choices(LOBBY_CODE_ALPHABET, k=LOBBY_CODE_LENGTH))


def _generate_player_key(slot: int) -> str:
    """Generate a secret player key for a slot."""
    return f"s{slot}_{secrets.token_urlsafe(16)}"


@dataclass
class LobbyError:
    """Error result from a lobby operation."""

    code: str
    message: str


class LobbyManager:
    """Manages all active lobbies in memory with optional database persistence.

    This class is responsible for:
    - Creating and deleting lobbies
    - Managing player join/leave
    - Handling ready states and settings
    - Starting games from lobbies
    - Enforcing the one-lobby-per-player rule
    - Persisting lobby state to database (if session factory provided)
    """

    def __init__(
        self,
        session_factory: "async_sessionmaker[AsyncSession] | None" = None,
    ) -> None:
        """Initialize the lobby manager.

        Args:
            session_factory: Optional SQLAlchemy async session factory for persistence.
                If not provided, lobbies are stored in-memory only.
        """
        self._lobbies: dict[str, Lobby] = {}  # code -> Lobby
        self._player_keys: dict[str, dict[int, str]] = {}  # code -> {slot: key}
        self._key_to_slot: dict[str, tuple[str, int]] = {}  # key -> (code, slot)
        self._player_to_lobby: dict[str, tuple[str, int]] = {}  # player_id -> (code, slot)
        self._game_to_lobby: dict[str, str] = {}  # game_id -> lobby_code
        self._next_lobby_id: int = 1
        self._lock = asyncio.Lock()
        self._session_factory = session_factory

    async def _persist_lobby(self, lobby: Lobby) -> None:
        """Persist a lobby to the database if persistence is enabled.

        Args:
            lobby: The lobby to persist
        """
        if self._session_factory is None:
            return

        from kfchess.db.repositories.lobbies import LobbyRepository

        try:
            async with self._session_factory() as session:
                repository = LobbyRepository(session)
                await repository.save(lobby)
                await session.commit()
        except Exception as e:
            # Log but don't raise - in-memory state is source of truth
            # Persistence failures are logged for monitoring/alerting
            logger.warning(
                f"Failed to persist lobby {lobby.code} to database: {e}. "
                "In-memory state remains valid."
            )

    async def _delete_lobby_from_db(self, code: str) -> None:
        """Delete a lobby from the database if persistence is enabled.

        Args:
            code: The lobby code to delete
        """
        if self._session_factory is None:
            return

        from kfchess.db.repositories.lobbies import LobbyRepository

        try:
            async with self._session_factory() as session:
                repository = LobbyRepository(session)
                await repository.delete_by_code(code)
                await session.commit()
        except Exception as e:
            # Log but don't raise - lobby is already removed from memory
            logger.warning(
                f"Failed to delete lobby {code} from database: {e}. "
                "Lobby already removed from memory."
            )

    async def create_lobby(
        self,
        host_user_id: int | None,
        host_username: str,
        settings: LobbySettings | None = None,
        add_ai: bool = False,
        ai_type: str = "bot:dummy",
        player_id: str | None = None,
    ) -> tuple[Lobby, str] | LobbyError:
        """Create a new lobby.

        Args:
            host_user_id: User ID of the host (None for guests)
            host_username: Display name for the host
            settings: Lobby settings (defaults if None)
            add_ai: Whether to add AI player(s) to fill slots
            ai_type: Type of AI to add (e.g., "bot:dummy")
            player_id: Unique player identifier for player lock

        Returns:
            Tuple of (Lobby, player_key for host) or LobbyError
        """
        async with self._lock:
            # Handle player lock - if player is in another lobby, leave it
            if player_id and player_id in self._player_to_lobby:
                old_code, old_slot = self._player_to_lobby[player_id]
                logger.info(f"Player {player_id} leaving lobby {old_code} to create new lobby")
                await self._leave_lobby_internal(old_code, old_slot, player_id)

            # Generate unique code
            code = _generate_lobby_code()
            while code in self._lobbies:
                code = _generate_lobby_code()

            # Use default settings if not provided
            if settings is None:
                settings = LobbySettings()

            # Create lobby
            lobby_id = self._next_lobby_id
            self._next_lobby_id += 1

            lobby = Lobby(
                id=lobby_id,
                code=code,
                host_slot=1,
                settings=settings,
            )

            # Add host as player 1
            host_player = LobbyPlayer(
                slot=1,
                user_id=host_user_id,
                username=host_username,
            )
            lobby.players[1] = host_player

            # Generate player key for host
            host_key = _generate_player_key(1)
            self._player_keys[code] = {1: host_key}
            self._key_to_slot[host_key] = (code, 1)

            # Track player in lobby
            if player_id:
                self._player_to_lobby[player_id] = (code, 1)

            # Add AI players if requested
            if add_ai:
                for slot in range(2, settings.player_count + 1):
                    ai_player = LobbyPlayer(
                        slot=slot,
                        user_id=None,
                        username=f"AI ({ai_type.removeprefix('bot:')})",
                        is_ai=True,
                        ai_type=ai_type,
                    )
                    lobby.players[slot] = ai_player
                    # AI players don't need keys

            self._lobbies[code] = lobby

            logger.info(f"Lobby {code} created by {host_username} (user_id={host_user_id})")

        # Persist outside lock to avoid potential deadlocks
        await self._persist_lobby(lobby)

        return lobby, host_key

    async def join_lobby(
        self,
        code: str,
        user_id: int | None,
        username: str,
        player_id: str | None = None,
        preferred_slot: int | None = None,
    ) -> tuple[Lobby, str, int] | LobbyError:
        """Join an existing lobby.

        Args:
            code: Lobby code
            user_id: User ID (None for guests)
            username: Display name
            player_id: Unique player identifier for player lock
            preferred_slot: Preferred slot number (optional)

        Returns:
            Tuple of (Lobby, player_key, slot) or LobbyError
        """
        async with self._lock:
            # Check if lobby exists
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            # Check if game is in progress
            if lobby.status == LobbyStatus.IN_GAME:
                return LobbyError(code="game_in_progress", message="Game is already in progress")

            # Check if lobby is full
            if lobby.is_full:
                return LobbyError(code="lobby_full", message="Lobby is full")

            # Handle player lock - if player is in another lobby, leave it
            if player_id and player_id in self._player_to_lobby:
                old_code, old_slot = self._player_to_lobby[player_id]
                if old_code == code:
                    # Already in this lobby
                    key = self._player_keys[code].get(old_slot)
                    if key:
                        return lobby, key, old_slot
                    # Key missing somehow, continue with rejoin
                else:
                    logger.info(f"Player {player_id} leaving lobby {old_code} to join {code}")
                    await self._leave_lobby_internal(old_code, old_slot, player_id)

            # Find slot
            slot = preferred_slot if preferred_slot and preferred_slot not in lobby.players else None
            if slot is None:
                slot = lobby.get_next_slot()
            if slot is None:
                return LobbyError(code="lobby_full", message="Lobby is full")

            # Create player
            player = LobbyPlayer(
                slot=slot,
                user_id=user_id,
                username=username,
            )
            lobby.players[slot] = player

            # Generate player key (defensive check for key tracking)
            player_key = _generate_player_key(slot)
            if code not in self._player_keys:
                self._player_keys[code] = {}
            self._player_keys[code][slot] = player_key
            self._key_to_slot[player_key] = (code, slot)

            # Track player in lobby
            if player_id:
                self._player_to_lobby[player_id] = (code, slot)

            logger.info(f"Player {username} joined lobby {code} in slot {slot}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby, player_key, slot

    async def leave_lobby(
        self,
        code: str,
        player_key: str,
        player_id: str | None = None,
    ) -> Lobby | None:
        """Remove a player from a lobby.

        Args:
            code: Lobby code
            player_key: Player's secret key
            player_id: Player identifier for tracking (optional)

        Returns:
            Updated Lobby or None if lobby was deleted
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(player_key)
            if key_info is None or key_info[0] != code:
                return None

            slot = key_info[1]
            result = await self._leave_lobby_internal(code, slot, player_id)

        # Persist or delete outside lock
        if result is None:
            await self._delete_lobby_from_db(code)
        else:
            await self._persist_lobby(result)

        return result

    async def _leave_lobby_internal(
        self,
        code: str,
        slot: int,
        player_id: str | None = None,
    ) -> Lobby | None:
        """Internal method to remove a player from a lobby.

        Must be called with self._lock held.
        """
        lobby = self._lobbies.get(code)
        if lobby is None:
            return None

        # Get player info before removal
        player = lobby.players.get(slot)
        if player is None:
            return lobby

        was_host = lobby.host_slot == slot

        # Remove player
        del lobby.players[slot]

        # Remove key
        if code in self._player_keys and slot in self._player_keys[code]:
            key = self._player_keys[code].pop(slot)
            self._key_to_slot.pop(key, None)

        # Remove player tracking
        if player_id:
            self._player_to_lobby.pop(player_id, None)

        logger.info(f"Player {player.username} left lobby {code} (slot {slot})")

        # Check if lobby should be deleted
        human_players = lobby.human_players
        if not human_players and lobby.status != LobbyStatus.IN_GAME:
            # No human players left and not in game - delete lobby
            await self._delete_lobby_internal(code)
            return None

        # Transfer host if needed
        if was_host and human_players:
            new_host_slot = min(p.slot for p in human_players)
            lobby.host_slot = new_host_slot
            logger.info(f"Host transferred to slot {new_host_slot} in lobby {code}")

        return lobby

    async def set_ready(
        self,
        code: str,
        player_key: str,
        ready: bool,
    ) -> Lobby | LobbyError:
        """Set a player's ready state.

        Args:
            code: Lobby code
            player_key: Player's secret key
            ready: Whether player is ready

        Returns:
            Updated Lobby or LobbyError
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(player_key)
            if key_info is None or key_info[0] != code:
                return LobbyError(code="invalid_key", message="Invalid player key")

            slot = key_info[1]
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            player = lobby.players.get(slot)
            if player is None:
                return LobbyError(code="not_found", message="Player not in lobby")

            if player.is_ai:
                return LobbyError(code="invalid_action", message="Cannot change AI ready state")

            if lobby.status != LobbyStatus.WAITING:
                return LobbyError(code="invalid_state", message="Cannot change ready state while in game")

            player.is_ready = ready
            logger.debug(f"Player in slot {slot} set ready={ready} in lobby {code}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    async def update_settings(
        self,
        code: str,
        player_key: str,
        settings: LobbySettings,
    ) -> Lobby | LobbyError:
        """Update lobby settings (host only).

        All human players are unreadied when settings change.

        Args:
            code: Lobby code
            player_key: Player's secret key
            settings: New settings

        Returns:
            Updated Lobby or LobbyError
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(player_key)
            if key_info is None or key_info[0] != code:
                return LobbyError(code="invalid_key", message="Invalid player key")

            slot = key_info[1]
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            # Check if player is host
            if lobby.host_slot != slot:
                return LobbyError(code="not_host", message="Only the host can change settings")

            if lobby.status != LobbyStatus.WAITING:
                return LobbyError(code="invalid_state", message="Cannot change settings while in game")

            # Validate settings
            if settings.player_count < len(lobby.players):
                return LobbyError(
                    code="invalid_settings",
                    message="Cannot reduce player count below current players",
                )

            if settings.is_ranked and any(p.is_ai for p in lobby.players.values()):
                return LobbyError(
                    code="invalid_settings",
                    message="Cannot enable ranked with AI players",
                )

            # Check if settings actually changed
            old_settings = lobby.settings
            settings_changed = (
                settings.is_public != old_settings.is_public
                or settings.speed != old_settings.speed
                or settings.player_count != old_settings.player_count
                or settings.is_ranked != old_settings.is_ranked
            )

            lobby.settings = settings

            # Unready all human players on settings change
            if settings_changed:
                for player in lobby.players.values():
                    if not player.is_ai:
                        player.is_ready = False
                logger.info(f"Settings updated in lobby {code}, all players unreadied")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    async def kick_player(
        self,
        code: str,
        host_key: str,
        target_slot: int,
    ) -> Lobby | LobbyError:
        """Kick a player from the lobby (host only).

        Args:
            code: Lobby code
            host_key: Host's secret key
            target_slot: Slot of player to kick

        Returns:
            Updated Lobby or LobbyError
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(host_key)
            if key_info is None or key_info[0] != code:
                return LobbyError(code="invalid_key", message="Invalid player key")

            slot = key_info[1]
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            # Check if player is host
            if lobby.host_slot != slot:
                return LobbyError(code="not_host", message="Only the host can kick players")

            # Cannot kick self
            if target_slot == slot:
                return LobbyError(code="invalid_action", message="Cannot kick yourself")

            # Check if target exists
            target = lobby.players.get(target_slot)
            if target is None:
                return LobbyError(code="not_found", message="Player not found")

            # Cannot kick AI (use remove_ai instead)
            if target.is_ai:
                return LobbyError(code="invalid_action", message="Use remove_ai to remove AI players")

            if lobby.status != LobbyStatus.WAITING:
                return LobbyError(code="invalid_state", message="Cannot kick players while in game")

            # Remove player
            del lobby.players[target_slot]

            # Remove key
            if target_slot in self._player_keys.get(code, {}):
                key = self._player_keys[code].pop(target_slot)
                self._key_to_slot.pop(key, None)

            logger.info(f"Player {target.username} kicked from lobby {code}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    async def add_ai(
        self,
        code: str,
        host_key: str,
        ai_type: str = "bot:dummy",
    ) -> Lobby | LobbyError:
        """Add an AI player to the lobby (host only).

        Args:
            code: Lobby code
            host_key: Host's secret key
            ai_type: Type of AI (e.g., "bot:dummy")

        Returns:
            Updated Lobby or LobbyError
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(host_key)
            if key_info is None or key_info[0] != code:
                return LobbyError(code="invalid_key", message="Invalid player key")

            slot = key_info[1]
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            # Check if player is host
            if lobby.host_slot != slot:
                return LobbyError(code="not_host", message="Only the host can add AI players")

            if lobby.is_full:
                return LobbyError(code="lobby_full", message="Lobby is full")

            if lobby.status != LobbyStatus.WAITING:
                return LobbyError(code="invalid_state", message="Cannot add AI while in game")

            # Cannot have AI in ranked games
            if lobby.settings.is_ranked:
                return LobbyError(code="invalid_action", message="Cannot add AI to ranked games")

            # Find next slot
            ai_slot = lobby.get_next_slot()
            if ai_slot is None:
                return LobbyError(code="lobby_full", message="Lobby is full")

            # Create AI player
            ai_player = LobbyPlayer(
                slot=ai_slot,
                user_id=None,
                username=f"AI ({ai_type.removeprefix('bot:')})",
                is_ai=True,
                ai_type=ai_type,
            )
            lobby.players[ai_slot] = ai_player

            logger.info(f"AI player {ai_type} added to lobby {code} in slot {ai_slot}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    async def remove_ai(
        self,
        code: str,
        host_key: str,
        target_slot: int,
    ) -> Lobby | LobbyError:
        """Remove an AI player from the lobby (host only).

        Args:
            code: Lobby code
            host_key: Host's secret key
            target_slot: Slot of AI to remove

        Returns:
            Updated Lobby or LobbyError
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(host_key)
            if key_info is None or key_info[0] != code:
                return LobbyError(code="invalid_key", message="Invalid player key")

            slot = key_info[1]
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            # Check if player is host
            if lobby.host_slot != slot:
                return LobbyError(code="not_host", message="Only the host can remove AI players")

            # Check if target exists and is AI
            target = lobby.players.get(target_slot)
            if target is None:
                return LobbyError(code="not_found", message="Player not found")

            if not target.is_ai:
                return LobbyError(code="invalid_action", message="Player is not an AI")

            if lobby.status != LobbyStatus.WAITING:
                return LobbyError(code="invalid_state", message="Cannot remove AI while in game")

            # Remove AI player
            del lobby.players[target_slot]

            logger.info(f"AI player removed from lobby {code} slot {target_slot}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    async def start_game(
        self,
        code: str,
        host_key: str,
    ) -> tuple[str, dict[int, str]] | LobbyError:
        """Start the game (host only, requires all players ready).

        Args:
            code: Lobby code
            host_key: Host's secret key

        Returns:
            Tuple of (game_id, {slot: player_key}) or LobbyError
        """
        async with self._lock:
            # Validate player key
            key_info = self._key_to_slot.get(host_key)
            if key_info is None or key_info[0] != code:
                return LobbyError(code="invalid_key", message="Invalid player key")

            slot = key_info[1]
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            # Check if player is host
            if lobby.host_slot != slot:
                return LobbyError(code="not_host", message="Only the host can start the game")

            if lobby.status != LobbyStatus.WAITING:
                return LobbyError(code="invalid_state", message="Game already in progress or finished")

            # Auto-ready host if needed
            host = lobby.players.get(slot)
            if host and not host.is_ai and not host.is_ready:
                host.is_ready = True

            # Check if all ready
            if not lobby.is_full:
                return LobbyError(code="not_ready", message="Waiting for more players")

            if not lobby.all_ready:
                return LobbyError(code="not_ready", message="Not all players are ready")

            # Transition to IN_GAME immediately (atomic - no going back)
            lobby.status = LobbyStatus.IN_GAME
            lobby.games_played += 1

            # Generate game ID
            from kfchess.services.game_service import _generate_game_id

            game_id = _generate_game_id()
            lobby.current_game_id = game_id

            # Track game_id -> lobby_code for end_game notifications
            self._game_to_lobby[game_id] = code

            # Generate new player keys for the game
            game_player_keys: dict[int, str] = {}
            for player_slot, player in lobby.players.items():
                if not player.is_ai:
                    game_key = _generate_player_key(player_slot)
                    game_player_keys[player_slot] = game_key

            logger.info(f"Game {game_id} starting from lobby {code}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return game_id, game_player_keys

    def find_lobby_by_game(self, game_id: str) -> str | None:
        """Find the lobby code for a game.

        Args:
            game_id: The game ID

        Returns:
            Lobby code or None if not found
        """
        return self._game_to_lobby.get(game_id)

    async def end_game(
        self,
        code: str,
        winner: int | None = None,
    ) -> Lobby | None:
        """Called when a game ends to prepare lobby for rematch.

        Args:
            code: Lobby code
            winner: Winner slot (1-4) or None for draw

        Returns:
            Updated Lobby or None if not found
        """
        async with self._lock:
            lobby = self._lobbies.get(code)
            if lobby is None:
                return None

            # Clean up game_id -> lobby_code mapping
            if lobby.current_game_id:
                self._game_to_lobby.pop(lobby.current_game_id, None)

            lobby.status = LobbyStatus.FINISHED
            lobby.current_game_id = None
            lobby.game_finished_at = datetime.utcnow()

            # Reset ready states for human players
            for player in lobby.players.values():
                if not player.is_ai:
                    player.is_ready = False

            logger.info(f"Game ended in lobby {code}, winner: {winner}")

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    async def return_to_lobby(
        self,
        code: str,
    ) -> Lobby | LobbyError:
        """Return a finished lobby to waiting state.

        Args:
            code: Lobby code

        Returns:
            Updated Lobby or LobbyError
        """
        async with self._lock:
            lobby = self._lobbies.get(code)
            if lobby is None:
                return LobbyError(code="not_found", message="Lobby not found")

            if lobby.status == LobbyStatus.IN_GAME:
                return LobbyError(code="invalid_state", message="Game is still in progress")

            lobby.status = LobbyStatus.WAITING

        # Persist outside lock
        await self._persist_lobby(lobby)

        return lobby

    def get_lobby(self, code: str) -> Lobby | None:
        """Get a lobby by code.

        Args:
            code: Lobby code

        Returns:
            Lobby or None if not found
        """
        return self._lobbies.get(code)

    def get_public_lobbies(
        self,
        status: LobbyStatus | None = None,
        speed: str | None = None,
        player_count: int | None = None,
    ) -> list[Lobby]:
        """Get all public lobbies, optionally filtered.

        Args:
            status: Filter by status (defaults to WAITING)
            speed: Filter by speed setting
            player_count: Filter by player count

        Returns:
            List of matching lobbies
        """
        # Default to WAITING status for public browsing
        if status is None:
            status = LobbyStatus.WAITING

        lobbies = []
        for lobby in self._lobbies.values():
            if not lobby.settings.is_public:
                continue
            if lobby.status != status:
                continue
            if speed and lobby.settings.speed != speed:
                continue
            if player_count and lobby.settings.player_count != player_count:
                continue
            lobbies.append(lobby)

        return lobbies

    def validate_player_key(self, code: str, player_key: str) -> int | None:
        """Validate a player key and return their slot.

        Args:
            code: Lobby code
            player_key: Player's secret key

        Returns:
            Slot number if valid, None if invalid
        """
        key_info = self._key_to_slot.get(player_key)
        if key_info is None or key_info[0] != code:
            return None
        return key_info[1]

    async def delete_lobby(self, code: str) -> bool:
        """Delete a lobby.

        Args:
            code: Lobby code

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            result = await self._delete_lobby_internal(code)

        # Delete from DB outside lock
        if result:
            await self._delete_lobby_from_db(code)

        return result

    async def _delete_lobby_internal(self, code: str) -> bool:
        """Internal method to delete a lobby.

        Must be called with self._lock held.
        """
        lobby = self._lobbies.get(code)
        if lobby is None:
            return False

        # Clean up all player keys
        if code in self._player_keys:
            for key in self._player_keys[code].values():
                self._key_to_slot.pop(key, None)
            del self._player_keys[code]

        # Clean up player tracking (find all players in this lobby)
        to_remove = [pid for pid, (lcode, _) in self._player_to_lobby.items() if lcode == code]
        for pid in to_remove:
            del self._player_to_lobby[pid]

        # Delete lobby
        del self._lobbies[code]

        logger.info(f"Lobby {code} deleted")

        return True

    def find_player_lobby(self, player_id: str) -> tuple[str, int] | None:
        """Find which lobby a player is in.

        Args:
            player_id: Player identifier

        Returns:
            Tuple of (code, slot) or None if not in a lobby
        """
        return self._player_to_lobby.get(player_id)

    async def cleanup_stale_lobbies(
        self,
        waiting_max_age_seconds: int = 3600,
        finished_max_age_seconds: int = 86400,
    ) -> int:
        """Remove lobbies that are old or empty.

        Args:
            waiting_max_age_seconds: Max age for empty WAITING lobbies
            finished_max_age_seconds: Max age for FINISHED lobbies

        Returns:
            Number of lobbies cleaned up
        """
        async with self._lock:
            now = datetime.utcnow()
            stale_lobbies = []

            for code, lobby in self._lobbies.items():
                human_players = lobby.human_players

                # Never cleanup IN_GAME lobbies
                if lobby.status == LobbyStatus.IN_GAME:
                    continue

                # Cleanup empty WAITING lobbies after waiting_max_age_seconds
                if lobby.status == LobbyStatus.WAITING and not human_players:
                    age = (now - lobby.created_at).total_seconds()
                    if age > waiting_max_age_seconds:
                        stale_lobbies.append(code)
                        continue

                # Cleanup FINISHED lobbies after finished_max_age_seconds
                if lobby.status == LobbyStatus.FINISHED:
                    check_time = lobby.game_finished_at or lobby.created_at
                    age = (now - check_time).total_seconds()
                    if age > finished_max_age_seconds:
                        stale_lobbies.append(code)

            for code in stale_lobbies:
                await self._delete_lobby_internal(code)

            if stale_lobbies:
                logger.info(f"Cleaned up {len(stale_lobbies)} stale lobbies")

        # Delete from DB outside lock
        for code in stale_lobbies:
            await self._delete_lobby_from_db(code)

        return len(stale_lobbies)


# Global singleton instance
_lobby_manager: LobbyManager | None = None


def get_lobby_manager() -> LobbyManager:
    """Get the global lobby manager instance."""
    global _lobby_manager
    if _lobby_manager is None:
        _lobby_manager = LobbyManager()
    return _lobby_manager


def init_lobby_manager(
    session_factory: "async_sessionmaker[AsyncSession] | None" = None,
) -> LobbyManager:
    """Initialize the global lobby manager with optional persistence.

    Args:
        session_factory: Optional SQLAlchemy async session factory for persistence.

    Returns:
        The initialized LobbyManager instance.
    """
    global _lobby_manager
    _lobby_manager = LobbyManager(session_factory=session_factory)
    return _lobby_manager


def reset_lobby_manager() -> None:
    """Reset the global lobby manager. Used for testing."""
    global _lobby_manager
    _lobby_manager = None

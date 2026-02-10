"""Redis-backed lobby manager for multi-server lobbies.

Replaces the in-memory LobbyManager with Redis as the source of truth.
All lobby state is stored in Redis, and mutations publish events to
pub/sub channels for cross-server WebSocket broadcasting.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import WatchError

from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus
from kfchess.redis.client import get_redis
from kfchess.services.game_service import _generate_game_id

logger = logging.getLogger(__name__)

# Characters for lobby codes (excluding ambiguous: O/0, I/1/L)
LOBBY_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LOBBY_CODE_LENGTH = 6

# Grace period for disconnected players before removal
DISCONNECT_GRACE_PERIOD = timedelta(seconds=30)

# Redis key TTLs
LOBBY_TTL_SECONDS = 86400  # 24 hours
GAME_MAPPING_TTL_SECONDS = 7200  # 2 hours

# Max retries for WATCH/MULTI/EXEC conflicts
MAX_RETRIES = 3


def _generate_lobby_code() -> str:
    """Generate a random lobby code."""
    chars = [secrets.choice(LOBBY_CODE_ALPHABET) for _ in range(LOBBY_CODE_LENGTH)]
    return "".join(chars)


def _generate_player_key(slot: int) -> str:
    """Generate a secret player key for a slot."""
    return f"s{slot}_{secrets.token_urlsafe(16)}"


def _lobby_key(code: str) -> str:
    return f"lobby:{code}"


def _keys_key(code: str) -> str:
    return f"lobby:{code}:keys"


def _game_mapping_key(game_id: str) -> str:
    return f"lobby:game:{game_id}"


def _pubsub_channel(code: str) -> str:
    return f"lobby_events:{code}"


class LobbyError:
    """Error result from a lobby operation."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


class RedisLobbyManager:
    """Lobby manager backed by Redis.

    All lobby state is stored in Redis. Mutations publish events to
    pub/sub channels so that all servers with lobby WebSocket connections
    can broadcast updates to their local clients.
    """

    async def _get_redis(self) -> Redis:
        return await get_redis()

    async def _load_lobby(self, r: Redis, code: str) -> Lobby | None:
        """Load a lobby from Redis."""
        data = await r.get(_lobby_key(code))
        if data is None:
            return None
        try:
            return Lobby.from_redis_dict(json.loads(data))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning(f"Corrupted lobby data for {code}, ignoring")
            return None

    async def _save_lobby(
        self,
        pipe: Any,
        lobby: Lobby,
    ) -> None:
        """Queue lobby save in a pipeline (must be in MULTI mode)."""
        data = json.dumps(lobby.to_redis_dict())
        pipe.set(_lobby_key(lobby.code), data, ex=LOBBY_TTL_SECONDS)
        pipe.expire(_keys_key(lobby.code), LOBBY_TTL_SECONDS)

    async def publish_event(self, code: str, event: dict[str, Any]) -> None:
        """Publish an event to the lobby's pub/sub channel."""
        r = await self._get_redis()
        await r.publish(_pubsub_channel(code), json.dumps(event))

    # ── Create ────────────────────────────────────────────────────

    async def create_lobby(
        self,
        host_user_id: int | None,
        host_username: str,
        settings: LobbySettings | None = None,
        add_ai: bool = False,
        ai_type: str = "bot:novice",
        player_id: str | None = None,
        picture_url: str | None = None,
    ) -> tuple[Lobby, str] | LobbyError:
        """Create a new lobby."""
        r = await self._get_redis()

        if settings is None:
            settings = LobbySettings()

        # Generate unique code
        code = _generate_lobby_code()
        # Retry if code already exists (very unlikely)
        for _ in range(10):
            if not await r.exists(_lobby_key(code)):
                break
            code = _generate_lobby_code()

        # Get sequential ID
        lobby_id = await r.incr("lobby:next_id")

        # Create lobby object
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
            picture_url=picture_url,
            player_id=player_id,
        )
        lobby.players[1] = host_player

        # Generate host key
        host_key = _generate_player_key(1)

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

        # Write to Redis (no WATCH needed — new lobby, no contention)
        pipe = r.pipeline(transaction=True)
        pipe.multi()
        pipe.set(_lobby_key(code), json.dumps(lobby.to_redis_dict()), ex=LOBBY_TTL_SECONDS)
        pipe.hset(_keys_key(code), str(1), host_key)
        pipe.expire(_keys_key(code), LOBBY_TTL_SECONDS)
        if settings.is_public:
            pipe.zadd("lobby:public_index", {code: lobby.created_at.timestamp()})
        await pipe.execute()

        logger.info(f"Lobby {code} created by {host_username} (user_id={host_user_id})")
        return lobby, host_key

    # ── Join ──────────────────────────────────────────────────────

    async def join_lobby(
        self,
        code: str,
        user_id: int | None,
        username: str,
        player_id: str | None = None,
        preferred_slot: int | None = None,
        picture_url: str | None = None,
    ) -> tuple[Lobby, str, int] | LobbyError:
        """Join an existing lobby."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.status == LobbyStatus.IN_GAME:
                        await pipe.unwatch()
                        return LobbyError(code="game_in_progress", message="Game is already in progress")

                    if lobby.is_full:
                        await pipe.unwatch()
                        return LobbyError(code="lobby_full", message="Lobby is full")

                    # Find slot
                    slot = preferred_slot if preferred_slot and preferred_slot not in lobby.players else None
                    if slot is None:
                        slot = lobby.get_next_slot()
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="lobby_full", message="Lobby is full")

                    # Create player
                    player = LobbyPlayer(
                        slot=slot,
                        user_id=user_id,
                        username=username,
                        picture_url=picture_url,
                        player_id=player_id,
                    )
                    lobby.players[slot] = player

                    # Generate player key
                    player_key = _generate_player_key(slot)

                    # Execute atomically
                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    pipe.hset(_keys_key(code), str(slot), player_key)
                    await pipe.execute()

                logger.info(f"Player {username} joined lobby {code} in slot {slot}")
                return lobby, player_key, slot

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently, please retry")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    # ── Leave ─────────────────────────────────────────────────────

    async def leave_lobby(
        self,
        code: str,
        player_key: str,
        player_id: str | None = None,
    ) -> Lobby | None:
        """Remove a player from a lobby.

        Returns updated Lobby, or None if lobby was deleted.
        """
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code), _keys_key(code))

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return None

                    # Validate player key → slot
                    slot = await self._key_to_slot(r, code, player_key)
                    if slot is None:
                        await pipe.unwatch()
                        return None

                    player = lobby.players.get(slot)
                    if player is None:
                        await pipe.unwatch()
                        return lobby

                    was_host = lobby.host_slot == slot
                    del lobby.players[slot]

                    # Check if lobby should be deleted
                    human_players = lobby.human_players
                    if not human_players and lobby.status != LobbyStatus.IN_GAME:
                        pipe.multi()
                        pipe.delete(_lobby_key(code), _keys_key(code))
                        pipe.zrem("lobby:public_index", code)
                        await pipe.execute()
                        logger.info(f"Lobby {code} deleted after last player left")
                        return None

                    # Transfer host if needed
                    new_host_slot = lobby.host_slot
                    if was_host and human_players:
                        new_host_slot = min(p.slot for p in human_players)
                        lobby.host_slot = new_host_slot

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    pipe.hdel(_keys_key(code), str(slot))
                    await pipe.execute()

                logger.info(f"Player left lobby {code} (slot {slot})")
                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return None
                continue

        return None

    # ── Connection status ─────────────────────────────────────────

    async def set_connected(
        self,
        code: str,
        slot: int,
        connected: bool,
    ) -> Lobby | None:
        """Set a player's connection status."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return None

                    player = lobby.players.get(slot)
                    if player is None:
                        await pipe.unwatch()
                        return None

                    player.is_connected = connected
                    if connected:
                        player.disconnected_at = None
                    else:
                        player.disconnected_at = datetime.utcnow()

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    await pipe.execute()

                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return None
                continue

        return None

    async def cleanup_disconnected_players(self, code: str) -> list[int]:
        """Remove players who have been disconnected past the grace period."""
        r = await self._get_redis()
        cleaned_slots: list[int] = []

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code), _keys_key(code))

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return cleaned_slots

                    if lobby.status == LobbyStatus.IN_GAME:
                        await pipe.unwatch()
                        return cleaned_slots

                    now = datetime.utcnow()
                    cleaned_slots = []

                    for slot, player in list(lobby.players.items()):
                        if player.is_ai:
                            continue
                        if player.disconnected_at is None:
                            continue
                        if now - player.disconnected_at > DISCONNECT_GRACE_PERIOD:
                            cleaned_slots.append(slot)

                    if not cleaned_slots:
                        await pipe.unwatch()
                        return cleaned_slots

                    # Remove expired players
                    for slot in cleaned_slots:
                        del lobby.players[slot]

                    # Check if lobby should be deleted
                    human_players = lobby.human_players
                    if not human_players and lobby.status != LobbyStatus.IN_GAME:
                        pipe.multi()
                        pipe.delete(_lobby_key(code), _keys_key(code))
                        pipe.zrem("lobby:public_index", code)
                        await pipe.execute()
                        logger.info(f"Lobby {code} deleted after all disconnected players expired")
                        return cleaned_slots

                    # Transfer host if needed
                    if lobby.host_slot in cleaned_slots and human_players:
                        lobby.host_slot = min(p.slot for p in human_players)

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    for slot in cleaned_slots:
                        pipe.hdel(_keys_key(code), str(slot))
                    await pipe.execute()

                return cleaned_slots

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return []
                cleaned_slots = []
                continue

        return []

    # ── Ready ─────────────────────────────────────────────────────

    async def set_ready(
        self,
        code: str,
        player_key: str,
        ready: bool,
    ) -> Lobby | LobbyError:
        """Set a player's ready state."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    slot = await self._key_to_slot(r, code, player_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    player = lobby.players.get(slot)
                    if player is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Player not in lobby")

                    if player.is_ai:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_action", message="Cannot change AI ready state")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Cannot change ready state while in game")

                    player.is_ready = ready

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    await pipe.execute()

                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    # ── Settings ──────────────────────────────────────────────────

    async def update_settings(
        self,
        code: str,
        player_key: str,
        settings: LobbySettings,
    ) -> Lobby | LobbyError:
        """Update lobby settings (host only). Unreadies all human players."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    slot = await self._key_to_slot(r, code, player_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.host_slot != slot:
                        await pipe.unwatch()
                        return LobbyError(code="not_host", message="Only the host can change settings")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Cannot change settings while in game")

                    if settings.player_count < len(lobby.players):
                        await pipe.unwatch()
                        return LobbyError(
                            code="invalid_settings",
                            message="Cannot reduce player count below current players",
                        )

                    if settings.is_ranked:
                        for p in lobby.players.values():
                            if p.is_ai:
                                await pipe.unwatch()
                                return LobbyError(code="invalid_settings", message="Cannot enable ranked with AI players")
                            if p.user_id is None:
                                await pipe.unwatch()
                                return LobbyError(
                                    code="invalid_settings", message="Cannot enable ranked with guest players"
                                )

                    old_settings = lobby.settings
                    settings_changed = (
                        settings.is_public != old_settings.is_public
                        or settings.speed != old_settings.speed
                        or settings.player_count != old_settings.player_count
                        or settings.is_ranked != old_settings.is_ranked
                    )

                    lobby.settings = settings

                    if settings_changed:
                        for player in lobby.players.values():
                            if not player.is_ai:
                                player.is_ready = False

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    # Update public index
                    if settings.is_public:
                        pipe.zadd("lobby:public_index", {code: lobby.created_at.timestamp()})
                    else:
                        pipe.zrem("lobby:public_index", code)
                    await pipe.execute()

                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    # ── Kick ──────────────────────────────────────────────────────

    async def kick_player(
        self,
        code: str,
        host_key: str,
        target_slot: int,
    ) -> Lobby | LobbyError:
        """Kick a player from the lobby (host only)."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code), _keys_key(code))

                    slot = await self._key_to_slot(r, code, host_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.host_slot != slot:
                        await pipe.unwatch()
                        return LobbyError(code="not_host", message="Only the host can kick players")

                    if target_slot == slot:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_action", message="Cannot kick yourself")

                    target = lobby.players.get(target_slot)
                    if target is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Player not found")

                    if target.is_ai:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_action", message="Use remove_ai to remove AI players")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Cannot kick players while in game")

                    del lobby.players[target_slot]

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    pipe.hdel(_keys_key(code), str(target_slot))
                    await pipe.execute()

                logger.info(f"Player kicked from lobby {code} slot {target_slot}")
                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    # ── AI management ─────────────────────────────────────────────

    async def add_ai(
        self,
        code: str,
        host_key: str,
        ai_type: str = "bot:novice",
    ) -> Lobby | LobbyError:
        """Add an AI player to the lobby (host only)."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    slot = await self._key_to_slot(r, code, host_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.host_slot != slot:
                        await pipe.unwatch()
                        return LobbyError(code="not_host", message="Only the host can add AI players")

                    if lobby.is_full:
                        await pipe.unwatch()
                        return LobbyError(code="lobby_full", message="Lobby is full")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Cannot add AI while in game")

                    if lobby.settings.is_ranked:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_action", message="Cannot add AI to ranked games")

                    ai_slot = lobby.get_next_slot()
                    if ai_slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="lobby_full", message="Lobby is full")

                    ai_player = LobbyPlayer(
                        slot=ai_slot,
                        user_id=None,
                        username=f"AI ({ai_type.removeprefix('bot:')})",
                        is_ai=True,
                        ai_type=ai_type,
                    )
                    lobby.players[ai_slot] = ai_player

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    await pipe.execute()

                logger.info(f"AI player {ai_type} added to lobby {code} in slot {ai_slot}")
                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    async def remove_ai(
        self,
        code: str,
        host_key: str,
        target_slot: int,
    ) -> Lobby | LobbyError:
        """Remove an AI player from the lobby (host only)."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    slot = await self._key_to_slot(r, code, host_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.host_slot != slot:
                        await pipe.unwatch()
                        return LobbyError(code="not_host", message="Only the host can remove AI players")

                    target = lobby.players.get(target_slot)
                    if target is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Player not found")

                    if not target.is_ai:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_action", message="Player is not an AI")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Cannot remove AI while in game")

                    del lobby.players[target_slot]

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    await pipe.execute()

                logger.info(f"AI player removed from lobby {code} slot {target_slot}")
                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    async def change_ai_type(
        self,
        code: str,
        host_key: str,
        target_slot: int,
        ai_type: str,
    ) -> Lobby | LobbyError:
        """Change the AI type for an AI player (host only)."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    slot = await self._key_to_slot(r, code, host_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.host_slot != slot:
                        await pipe.unwatch()
                        return LobbyError(code="not_host", message="Only the host can change AI difficulty")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Cannot change AI while in game")

                    target = lobby.players.get(target_slot)
                    if target is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Player not found")

                    if not target.is_ai:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_action", message="Player is not an AI")

                    target.ai_type = ai_type
                    display_name = ai_type.removeprefix("bot:")
                    target.username = f"AI ({display_name.capitalize()})"

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    await pipe.execute()

                logger.info(f"AI type changed to {ai_type} in lobby {code} slot {target_slot}")
                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    # ── Game lifecycle ────────────────────────────────────────────

    async def start_game(
        self,
        code: str,
        host_key: str,
    ) -> tuple[str, dict[int, str]] | LobbyError:
        """Start the game (host only, requires all players ready).

        Returns (game_id, {slot: player_key}) or LobbyError.
        Does NOT publish game_starting — the WS handler does that
        after creating the game and registering routing.
        """
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    slot = await self._key_to_slot(r, code, host_key)
                    if slot is None:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_key", message="Invalid player key")

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.host_slot != slot:
                        await pipe.unwatch()
                        return LobbyError(code="not_host", message="Only the host can start the game")

                    if lobby.status != LobbyStatus.WAITING:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Game already in progress or finished")

                    # Auto-ready host
                    host = lobby.players.get(slot)
                    if host and not host.is_ai and not host.is_ready:
                        host.is_ready = True

                    if not lobby.is_full:
                        await pipe.unwatch()
                        return LobbyError(code="not_ready", message="Waiting for more players")

                    if not lobby.all_ready:
                        await pipe.unwatch()
                        return LobbyError(code="not_ready", message="Not all players are ready")

                    # Transition to IN_GAME
                    lobby.status = LobbyStatus.IN_GAME
                    lobby.games_played += 1

                    game_id = _generate_game_id()
                    lobby.current_game_id = game_id

                    # Generate game player keys for human players
                    game_player_keys: dict[int, str] = {}
                    for player_slot, player in lobby.players.items():
                        if not player.is_ai:
                            game_player_keys[player_slot] = _generate_player_key(player_slot)

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    pipe.set(_game_mapping_key(game_id), code, ex=GAME_MAPPING_TTL_SECONDS)
                    await pipe.execute()

                logger.info(f"Game {game_id} starting from lobby {code}")
                return game_id, game_player_keys

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    async def end_game(
        self,
        code: str,
        winner: int | None = None,
    ) -> Lobby | None:
        """Called when a game ends to prepare lobby for rematch."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return None

                    # Clean up game mapping
                    old_game_id = lobby.current_game_id

                    lobby.status = LobbyStatus.FINISHED
                    lobby.current_game_id = None
                    lobby.game_finished_at = datetime.utcnow()

                    # Reset ready states
                    for player in lobby.players.values():
                        if not player.is_ai:
                            player.is_ready = False

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    if old_game_id:
                        pipe.delete(_game_mapping_key(old_game_id))
                    await pipe.execute()

                logger.info(f"Game ended in lobby {code}, winner: {winner}")
                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return None
                continue

        return None

    async def return_to_lobby(self, code: str) -> Lobby | LobbyError:
        """Return a finished lobby to waiting state."""
        r = await self._get_redis()

        for attempt in range(MAX_RETRIES):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(_lobby_key(code))

                    lobby = await self._load_lobby(r, code)
                    if lobby is None:
                        await pipe.unwatch()
                        return LobbyError(code="not_found", message="Lobby not found")

                    if lobby.status == LobbyStatus.IN_GAME:
                        await pipe.unwatch()
                        return LobbyError(code="invalid_state", message="Game is still in progress")

                    lobby.status = LobbyStatus.WAITING

                    pipe.multi()
                    await self._save_lobby(pipe, lobby)
                    await pipe.execute()

                return lobby

            except WatchError:
                if attempt == MAX_RETRIES - 1:
                    return LobbyError(code="conflict", message="Lobby was modified concurrently")
                continue

        return LobbyError(code="conflict", message="Failed after retries")

    # ── Read operations ───────────────────────────────────────────

    async def get_lobby(self, code: str) -> Lobby | None:
        """Get a lobby by code."""
        r = await self._get_redis()
        return await self._load_lobby(r, code)

    async def get_public_lobbies(
        self,
        status: LobbyStatus | None = None,
        speed: str | None = None,
        player_count: int | None = None,
        is_ranked: bool | None = None,
    ) -> list[Lobby]:
        """Get all public lobbies, optionally filtered."""
        if status is None:
            status = LobbyStatus.WAITING

        r = await self._get_redis()
        codes = await r.zrange("lobby:public_index", 0, -1)

        lobbies = []
        for code in codes:
            lobby = await self._load_lobby(r, code)
            if lobby is None:
                # Stale index entry — clean up lazily
                await r.zrem("lobby:public_index", code)
                continue

            if lobby.status != status:
                continue
            if lobby.is_full:
                continue
            if speed and lobby.settings.speed != speed:
                continue
            if player_count and lobby.settings.player_count != player_count:
                continue
            if is_ranked is not None and lobby.settings.is_ranked != is_ranked:
                continue
            lobbies.append(lobby)

        return lobbies

    async def validate_player_key(self, code: str, player_key: str) -> int | None:
        """Validate a player key and return their slot."""
        r = await self._get_redis()
        return await self._key_to_slot(r, code, player_key)

    async def find_lobby_by_game(self, game_id: str) -> str | None:
        """Find the lobby code for a game."""
        r = await self._get_redis()
        return await r.get(_game_mapping_key(game_id))

    # ── Delete / cleanup ──────────────────────────────────────────

    async def delete_lobby(self, code: str) -> bool:
        """Delete a lobby."""
        r = await self._get_redis()
        result = await r.delete(_lobby_key(code), _keys_key(code))
        await r.zrem("lobby:public_index", code)
        if result:
            logger.info(f"Lobby {code} deleted")
        return result > 0

    async def cleanup_stale_lobbies(
        self,
        waiting_max_age_seconds: int = 3600,
        finished_max_age_seconds: int = 86400,
    ) -> int:
        """Remove lobbies that are old or empty."""
        r = await self._get_redis()
        codes = await r.zrange("lobby:public_index", 0, -1)

        now = datetime.utcnow()
        cleaned = 0

        for code in codes:
            lobby = await self._load_lobby(r, code)
            if lobby is None:
                await r.zrem("lobby:public_index", code)
                cleaned += 1
                continue

            if lobby.status == LobbyStatus.IN_GAME:
                continue

            human_players = lobby.human_players

            if lobby.status == LobbyStatus.WAITING and not human_players:
                age = (now - lobby.created_at).total_seconds()
                if age > waiting_max_age_seconds:
                    await self.delete_lobby(code)
                    cleaned += 1
                    continue

            if lobby.status == LobbyStatus.FINISHED:
                check_time = lobby.game_finished_at or lobby.created_at
                age = (now - check_time).total_seconds()
                if age > finished_max_age_seconds:
                    await self.delete_lobby(code)
                    cleaned += 1

        if cleaned:
            logger.info(f"Cleaned up {cleaned} stale lobbies")

        return cleaned

    # ── Internal helpers ──────────────────────────────────────────

    async def _key_to_slot(self, r: Redis, code: str, player_key: str) -> int | None:
        """Look up which slot a player key belongs to.

        Scans the keys hash (max 4 entries) for a matching value.
        """
        keys_data = await r.hgetall(_keys_key(code))
        for slot_str, key in keys_data.items():
            if key == player_key:
                return int(slot_str)
        return None

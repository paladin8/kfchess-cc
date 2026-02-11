"""Display name utilities for player identity formatting.

This module provides functions to convert internal player IDs to user-friendly
display names. Player IDs have the format:
- u:{user_id} - Registered user (resolve username from database)
- guest:{uuid} - Anonymous guest player
- bot:{type} - AI player (e.g., bot:novice)
"""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.db.models import User


class PlayerDisplay(BaseModel):
    """Resolved player display info for API responses."""

    name: str
    picture_url: str | None
    user_id: int | None
    is_bot: bool = False


def format_player_id(player_id: str, username_map: dict[int, str] | None = None) -> str:
    """Format a player ID into a display name.

    Args:
        player_id: Internal player ID (e.g., "u:123", "guest:abc", "bot:novice")
        username_map: Optional map of user_id -> username for resolving user names

    Returns:
        Human-readable display name
    """
    if player_id.startswith("u:"):
        # Registered user - look up username
        user_id_str = player_id[2:]
        try:
            user_id = int(user_id_str)
            if username_map and user_id in username_map:
                return username_map[user_id]
        except ValueError:
            pass
        # Fallback if we can't resolve
        return f"User {user_id_str}"

    if player_id.startswith("guest:"):
        return "Guest"

    if player_id.startswith("bot:"):
        bot_type = player_id[4:]  # e.g., "dummy"
        # Capitalize first letter
        bot_name = bot_type.capitalize()
        return f"AI ({bot_name})"

    # Legacy AI format from old kfchess (e.g., "b:novice")
    if player_id.startswith("b:"):
        bot_type = player_id[2:]
        return f"AI ({bot_type.capitalize()})"

    # Unknown format - return as-is
    return player_id


def extract_user_ids(player_ids: list[str]) -> list[int]:
    """Extract user IDs from a list of player IDs.

    Args:
        player_ids: List of player IDs to extract user IDs from

    Returns:
        List of user IDs (integers) for players that are registered users
    """
    user_ids = []
    for player_id in player_ids:
        if player_id.startswith("u:"):
            try:
                user_id = int(player_id[2:])
                user_ids.append(user_id)
            except ValueError:
                pass
    return user_ids


class _UserInfo:
    """Internal user info from DB query."""

    __slots__ = ("username", "picture_url")

    def __init__(self, username: str, picture_url: str | None) -> None:
        self.username = username
        self.picture_url = picture_url


async def _fetch_user_info(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, _UserInfo]:
    """Fetch user info (username + picture_url) for a list of user IDs.

    Args:
        session: Database session
        user_ids: List of user IDs to look up

    Returns:
        Dict mapping user_id -> _UserInfo
    """
    if not user_ids:
        return {}

    result = await session.execute(
        select(User.id, User.username, User.picture_url).where(User.id.in_(user_ids))
    )
    return {
        row.id: _UserInfo(username=row.username, picture_url=row.picture_url)
        for row in result.all()
    }


def _resolve_from_info(
    players: dict[int, str],
    user_info_map: dict[int, _UserInfo],
) -> dict[int, PlayerDisplay]:
    """Resolve player IDs to PlayerDisplay using a pre-fetched user info map.

    Args:
        players: Dict mapping player number to player ID
        user_info_map: Pre-fetched user info from _fetch_user_info()

    Returns:
        Dict mapping player number to PlayerDisplay
    """
    result: dict[int, PlayerDisplay] = {}
    for num, player_id in players.items():
        if player_id.startswith("u:"):
            try:
                uid = int(player_id[2:])
                info = user_info_map.get(uid)
                if info:
                    result[num] = PlayerDisplay(
                        name=info.username,
                        picture_url=info.picture_url,
                        user_id=uid,
                    )
                else:
                    result[num] = PlayerDisplay(
                        name=f"User {uid}",
                        picture_url=None,
                        user_id=uid,
                    )
            except ValueError:
                result[num] = PlayerDisplay(
                    name=player_id,
                    picture_url=None,
                    user_id=None,
                )
        else:
            result[num] = PlayerDisplay(
                name=format_player_id(player_id),
                picture_url=None,
                user_id=None,
                is_bot=player_id.startswith("bot:") or player_id.startswith("b:"),
            )
    return result


async def resolve_player_info(
    session: AsyncSession, players: dict[int, str]
) -> dict[int, PlayerDisplay]:
    """Resolve a dict of player IDs to PlayerDisplay objects with picture URLs.

    Args:
        session: Database session
        players: Dict mapping player number to player ID

    Returns:
        Dict mapping player number to PlayerDisplay
    """
    user_ids = extract_user_ids(list(players.values()))
    user_info_map = await _fetch_user_info(session, user_ids)
    return _resolve_from_info(players, user_info_map)


async def resolve_player_info_batch(
    session: AsyncSession,
    players_list: list[dict[int, str]],
) -> list[dict[int, PlayerDisplay]]:
    """Resolve multiple player dicts in a single DB query.

    Args:
        session: Database session
        players_list: List of player dicts (each mapping player number to player ID)

    Returns:
        List of resolved PlayerDisplay dicts, in the same order as input
    """
    # Collect all user IDs across all player dicts
    all_player_ids: list[str] = []
    for players in players_list:
        all_player_ids.extend(players.values())

    all_user_ids = extract_user_ids(all_player_ids)
    # Deduplicate
    unique_user_ids = list(set(all_user_ids))
    user_info_map = await _fetch_user_info(session, unique_user_ids)

    return [_resolve_from_info(players, user_info_map) for players in players_list]

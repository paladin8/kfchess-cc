"""Game snapshot for multi-server state persistence.

A GameSnapshot wraps a serialized GameState with metadata needed to fully
reconstruct a ManagedGame on another server (player keys, AI config, campaign
info, etc.). The snapshot is stored in Redis and used for crash recovery and
rolling deploys.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameSnapshot:
    """Serializable game snapshot for Redis persistence.

    Attributes:
        game_id: Unique game identifier
        state: GameState serialized via to_snapshot_dict()
        player_keys: Map of player number to secret player key
        ai_config: Map of player number to AI type name (e.g., "novice")
        campaign_level_id: Campaign level ID if this is a campaign game
        campaign_user_id: User ID who started the campaign game
        initial_board_str: Initial board string for campaign games
        resigned_piece_ids: IDs of kings captured via resignation (4-player)
        draw_offers: Set of player numbers who have offered a draw
        force_broadcast: Whether to force a state broadcast on next tick
        server_id: ID of the server that owns this game
        snapshot_tick: Game tick when snapshot was taken
        snapshot_time: Unix timestamp when snapshot was taken
    """

    game_id: str
    state: dict[str, Any]
    player_keys: dict[int, str] = field(default_factory=dict)
    ai_config: dict[int, str] = field(default_factory=dict)
    campaign_level_id: int | None = None
    campaign_user_id: int | None = None
    initial_board_str: str | None = None
    resigned_piece_ids: list[str] = field(default_factory=list)
    draw_offers: set[int] = field(default_factory=set)
    force_broadcast: bool = False
    server_id: str = ""
    snapshot_tick: int = 0
    snapshot_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to a dictionary for JSON/Redis storage."""
        return {
            "game_id": self.game_id,
            "state": self.state,
            "player_keys": {str(k): v for k, v in self.player_keys.items()},
            "ai_config": {str(k): v for k, v in self.ai_config.items()},
            "campaign_level_id": self.campaign_level_id,
            "campaign_user_id": self.campaign_user_id,
            "initial_board_str": self.initial_board_str,
            "resigned_piece_ids": self.resigned_piece_ids,
            "draw_offers": list(self.draw_offers),
            "force_broadcast": self.force_broadcast,
            "server_id": self.server_id,
            "snapshot_tick": self.snapshot_tick,
            "snapshot_time": self.snapshot_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameSnapshot:
        """Deserialize snapshot from a dictionary."""
        return cls(
            game_id=data["game_id"],
            state=data["state"],
            player_keys={int(k): v for k, v in data.get("player_keys", {}).items()},
            ai_config={int(k): v for k, v in data.get("ai_config", {}).items()},
            campaign_level_id=data.get("campaign_level_id"),
            campaign_user_id=data.get("campaign_user_id"),
            initial_board_str=data.get("initial_board_str"),
            resigned_piece_ids=data.get("resigned_piece_ids", []),
            draw_offers=set(data.get("draw_offers", [])),
            force_broadcast=data.get("force_broadcast", False),
            server_id=data.get("server_id", ""),
            snapshot_tick=data.get("snapshot_tick", 0),
            snapshot_time=data.get("snapshot_time", 0.0),
        )

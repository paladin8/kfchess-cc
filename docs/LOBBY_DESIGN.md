# Lobby System Design

This document describes the design for the lobby system in Kung Fu Chess.

---

## Table of Contents

1. [Overview](#overview)
2. [Goals](#goals)
3. [User Flow](#user-flow)
4. [Architecture](#architecture)
5. [Data Model](#data-model)
6. [WebSocket Protocol](#websocket-protocol)
7. [REST API](#rest-api)
8. [Backend Implementation](#backend-implementation)
9. [Frontend Implementation](#frontend-implementation)
10. [Edge Cases & Error Handling](#edge-cases--error-handling)
11. [Game Countdown](#game-countdown)
12. [Implementation Plan](#implementation-plan)
13. [Design Decisions](#design-decisions)

---

## Overview

The lobby system is a pre-game waiting room where players gather before starting a game. **Every game** goes through a lobby, including AI games and campaign levels. The lobby serves as the "lock" ensuring a player can only be in one game at a time.

**Key Concepts:**
- **Lobby**: A waiting room with configurable game settings
- **Host**: The player who created the lobby and controls settings/game start
- **Lobby Code**: A short, shareable code for joining private lobbies
- **Slot**: A position in the game (1-4 depending on player count)
- **Player Lock**: A player can only be in one lobby at a time; joining a new lobby leaves any existing one

---

## Goals

1. **Universal**: Every game goes through a lobby (including campaign)
2. **Player Lock**: A player can only be in one lobby/game at a time
3. **Rematch Flow**: Players return to the same lobby after a game ends
4. **Host Control**: Host manages settings, invites, kicks, and game start
5. **Ready System**: All players must ready up before the host can start
6. **Countdown on Board**: 3-second countdown happens on the game board, not in lobby
7. **Discoverability**: Public lobbies are browsable; private lobbies use codes/links

---

## User Flow

### Creating a Game (Play vs AI)

```
Home Page
    │
    ├── Click "Play vs AI"
    │
    ▼
Create Lobby Modal
    │
    ├── Select settings (speed, board type)
    ├── Click "Create"
    │
    ▼
Lobby Page (/lobby/{code})
    │
    ├── Player 1 (human) - Host
    ├── Player 2 (AI) - Auto-ready
    │
    ├── Host clicks "Ready"
    ├── Host clicks "Start Game"
    │
    ▼
Game Page (/game/{gameId})
    │
    ├── 3-second countdown on board
    │
    ▼
Game Starts
```

### Creating a Multiplayer Lobby

```
Home Page
    │
    ├── Click "Create Lobby"
    │
    ▼
Create Lobby Modal
    │
    ├── Select settings (public/private, speed, 2p/4p, ranked/unrated)
    ├── Click "Create"
    │
    ▼
Lobby Page (/lobby/{code})
    │
    ├── Player 1 (host) - Waiting for others
    ├── Share link or wait for public join
    │
    ├── Other players join
    ├── All players ready up
    ├── Host clicks "Start Game"
    │
    ▼
Game Page (/game/{gameId})
    │
    ├── 3-second countdown on board
    │
    ▼
Game Starts
```

### Campaign Level

```
Campaign Page
    │
    ├── Select level
    │
    ▼
Create Campaign Lobby (auto)
    │
    ├── Player 1 (human) - Host
    ├── Player 2 (Campaign AI) - Auto-ready
    ├── Settings locked (level-specific)
    │
    ▼
Lobby Page (/lobby/{code})
    │
    ├── Host clicks "Ready"
    ├── Host clicks "Start Game"
    │
    ▼
Game Page → 3-second countdown → Game Starts
```

### Joining a Lobby

```
Option A: Public Browse          Option B: Direct Link           Option C: Code Entry
        │                                │                               │
        ▼                                ▼                               ▼
Lobbies Page (/lobbies)          /lobby/{code}                   Join Modal on Home
        │                                │                               │
        ├── See WAITING lobbies          ├── Auto-join if not full       ├── Enter code
        ├── Click "Join"                 │                               ├── Click "Join"
        │                                │                               │
        └────────────────────────────────┴───────────────────────────────┘
                                         │
                                         ▼
                                 Lobby Page (/lobby/{code})
```

**Note:** The Lobbies page only shows lobbies waiting for players. Games in progress appear on the Live Games page instead.

### Spectating a Game

```
Option A: Live Games Browse      Option B: Direct Link
        │                                │
        ▼                                ▼
Live Games Page (/live)          /game/{gameId}
        │                                │
        ├── See games in progress        ├── Connect as spectator
        ├── Click "Spectate"             │   (no player key)
        │                                │
        └────────────────────────────────┘
                                         │
                                         ▼
                                 Game Page (spectator mode)
                                         │
                                         ├── Watch live gameplay
                                         ├── No move controls
                                         └── Can leave anytime
```

### Post-Game Flow

```
Game Over Modal
    │
    ├── "Return to Lobby" (primary CTA)
    │       │
    │       ▼
    │   Lobby Page (same lobby, ready states reset)
    │
    ├── "View Replay"
    │       │
    │       ▼
    │   Replay Page
    │
    └── "Leave" / "Home"
            │
            ▼
        Home Page
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLIENT                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │ Lobby Page  │───▶│ Lobby Store  │───▶│ Lobby Components     │   │
│  │             │    │ (Zustand)    │    │ (settings, players)  │   │
│  └─────────────┘    └──────────────┘    └──────────────────────┘   │
│         │                   ▲                                        │
│         │ WebSocket         │ state updates                          │
│         ▼                   │                                        │
└─────────┼───────────────────┼────────────────────────────────────────┘
          │                   │
          ▼                   │
┌─────────────────────────────────────────────────────────────────────┐
│                           SERVER                                     │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ Lobby WS        │───▶│ LobbyManager     │───▶│ LobbySession  │  │
│  │ Handler         │    │ (in-memory)      │    │ (per lobby)   │  │
│  └─────────────────┘    └──────────────────┘    └───────────────┘  │
│         │                        │                                   │
│         │                        ▼                                   │
│         │               ┌──────────────────┐                        │
│         │               │ GameService      │                        │
│         │               │ (creates games)  │                        │
│         │               └──────────────────┘                        │
│         │                        │                                   │
│         ▼                        ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      PostgreSQL                              │   │
│  │  lobbies, lobby_players (for persistence/history)           │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Flow:**
1. Client creates/joins lobby via REST API
2. Client connects to `/ws/lobby/{code}` for real-time updates
3. Server maintains lobby state in memory (LobbyManager)
4. When host starts game, server creates game via GameService
5. Server broadcasts transition message with game ID
6. All clients navigate to `/game/{gameId}`

---

## Data Model

### Lobby (Server-Side)

```python
# server/src/kfchess/lobby/models.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class LobbyStatus(Enum):
    WAITING = "waiting"      # Waiting for players to join/ready
    IN_GAME = "in_game"      # Game is in progress (countdown + playing)
    FINISHED = "finished"    # Game ended, lobby still exists for rematch

@dataclass
class LobbyPlayer:
    """A player in a lobby."""
    slot: int                    # 1-4
    user_id: int | None          # None for guests/anonymous
    username: str
    is_ai: bool = False
    ai_type: str | None = None   # e.g., "bot:dummy"
    is_ready: bool = False
    joined_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class LobbySettings:
    """Configurable lobby settings."""
    is_public: bool = True
    speed: str = "standard"      # "standard" or "lightning"
    player_count: int = 2        # 2 or 4
    is_ranked: bool = False      # Only for non-AI games

@dataclass
class Lobby:
    """A game lobby."""
    id: int                      # Database ID
    code: str                    # Short join code (e.g., "ABC123")
    host_slot: int               # Slot number of the host
    settings: LobbySettings
    players: dict[int, LobbyPlayer]  # slot -> player
    status: LobbyStatus = LobbyStatus.WAITING

    # Game tracking
    current_game_id: str | None = None
    games_played: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    game_finished_at: datetime | None = None  # For cleanup timing

    @property
    def host(self) -> LobbyPlayer | None:
        """Get the current host."""
        return self.players.get(self.host_slot)

    @property
    def is_full(self) -> bool:
        """Check if all slots are filled."""
        return len(self.players) >= self.settings.player_count

    @property
    def all_ready(self) -> bool:
        """Check if all players are ready."""
        if len(self.players) < self.settings.player_count:
            return False
        return all(p.is_ready for p in self.players.values())

    @property
    def human_players(self) -> list[LobbyPlayer]:
        """Get non-AI players."""
        return [p for p in self.players.values() if not p.is_ai]

    def get_next_slot(self) -> int | None:
        """Get the next available slot."""
        for slot in range(1, self.settings.player_count + 1):
            if slot not in self.players:
                return slot
        return None
```

### Database Models

The database schema is already defined in ARCHITECTURE.md. Here's the mapping:

```python
# server/src/kfchess/db/models.py

class Lobby(Base):
    """Database model for lobbies."""
    __tablename__ = "lobbies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    host_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    speed = Column(String(20), nullable=False)
    player_count = Column(Integer, default=2)
    is_public = Column(Boolean, default=True)
    is_ranked = Column(Boolean, default=False)
    status = Column(String(20), default="waiting")
    game_id = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)

    players = relationship("LobbyPlayer", back_populates="lobby", cascade="all, delete-orphan")

class LobbyPlayer(Base):
    """Database model for lobby players."""
    __tablename__ = "lobby_players"

    id = Column(Integer, primary_key=True)
    lobby_id = Column(Integer, ForeignKey("lobbies.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    player_slot = Column(Integer, nullable=False)
    is_ready = Column(Boolean, default=False)
    is_ai = Column(Boolean, default=False)
    ai_type = Column(String(50), nullable=True)
    joined_at = Column(DateTime, default=func.now())

    lobby = relationship("Lobby", back_populates="players")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("lobby_id", "player_slot"),
    )
```

### Frontend Types

```typescript
// client/src/stores/lobby.ts

export type LobbyStatus = 'waiting' | 'in_game' | 'finished';

export interface LobbyPlayer {
  slot: number;
  userId: number | null;
  username: string;
  isAi: boolean;
  aiType: string | null;
  isReady: boolean;
}

export interface LobbySettings {
  isPublic: boolean;
  speed: 'standard' | 'lightning';
  playerCount: 2 | 4;
  isRanked: boolean;
}

export interface Lobby {
  id: number;
  code: string;
  hostSlot: number;
  settings: LobbySettings;
  players: Record<number, LobbyPlayer>;
  status: LobbyStatus;
  currentGameId: string | null;
  gamesPlayed: number;
}
```

---

## WebSocket Protocol

### Connection

```
WebSocket: /ws/lobby/{code}?player_key={key}
```

The `player_key` is returned when joining the lobby and used to authenticate the WebSocket connection.

### Client → Server Messages

```typescript
// Set ready state
{ "type": "ready", "ready": true }

// Update settings (host only)
{
  "type": "update_settings",
  "settings": {
    "isPublic": false,
    "speed": "lightning",
    "playerCount": 4,
    "isRanked": true
  }
}

// Kick player (host only)
{ "type": "kick", "slot": 2 }

// Add AI player (host only)
{ "type": "add_ai", "aiType": "bot:dummy" }

// Remove AI player (host only)
{ "type": "remove_ai", "slot": 3 }

// Start game (host only, requires all ready)
{ "type": "start_game" }

// Leave lobby
{ "type": "leave" }

// Return to lobby (after game)
{ "type": "return_to_lobby" }

// Keep-alive
{ "type": "ping" }
```

### Server → Client Messages

```typescript
// Full lobby state (sent on connect and major updates)
{
  "type": "lobby_state",
  "lobby": {
    "id": 123,
    "code": "ABC123",
    "hostSlot": 1,
    "settings": { ... },
    "players": { ... },
    "status": "waiting",
    "currentGameId": null,
    "gamesPlayed": 0
  }
}

// Player joined (sent to OTHER connected players, not the joining player)
// The joining player receives lobby_state instead
{
  "type": "player_joined",
  "slot": 2,
  "player": {
    "slot": 2,
    "userId": 456,
    "username": "player2",
    "isAi": false,
    "aiType": null,
    "isReady": false
  }
}

// Player left
{
  "type": "player_left",
  "slot": 2,
  "reason": "left" | "kicked" | "disconnected" | "removed"  // "removed" for AI removal
}

// Player ready changed
{
  "type": "player_ready",
  "slot": 2,
  "ready": true
}

// Settings updated (host changed settings)
{
  "type": "settings_updated",
  "settings": { ... }
}

// Host changed (if host left and was transferred)
{
  "type": "host_changed",
  "newHostSlot": 2
}

// Game starting (immediate transition to game page)
// Countdown will happen on the game board, not in lobby
{
  "type": "game_starting",
  "gameId": "XYZ789",
  "lobbyCode": "ABC123",  // For post-game "Return to Lobby"
  "playerKey": "key1..."  // The receiving player's key
}

// Game ended (players can return to lobby)
// winner: slot number of winner, or 0 for draw/no winner
{
  "type": "game_ended",
  "winner": 1,
  "reason": "king_captured"
}

// Error
{
  "type": "error",
  "code": "not_host" | "lobby_full" | "game_in_progress" | "already_in_lobby" | ...,
  "message": "Only the host can change settings"
}

// Pong
{ "type": "pong" }
```

---

## REST API

### Endpoints

```
POST   /api/lobbies              Create a new lobby
GET    /api/lobbies              List public lobbies (WAITING only)
GET    /api/lobbies/{code}       Get lobby details
POST   /api/lobbies/{code}/join  Join a lobby
DELETE /api/lobbies/{code}       Delete lobby (host only)

GET    /api/games/live           List live games (for spectating)
```

### Create Lobby

```http
POST /api/lobbies
Content-Type: application/json
Authorization: Bearer <token>  (optional, creates guest lobby if not provided)

{
  "settings": {
    "isPublic": true,
    "speed": "standard",
    "playerCount": 2,
    "isRanked": false
  },
  "addAi": true,           // Automatically add AI to fill empty slots
  "aiType": "bot:dummy"    // AI type if addAi is true
}
```

**Response:**
```json
{
  "id": 123,
  "code": "ABC123",
  "playerKey": "secret-key-for-player-1",
  "slot": 1,
  "lobby": {
    "id": 123,
    "code": "ABC123",
    "hostSlot": 1,
    "settings": { ... },
    "players": { ... },
    "status": "waiting",
    "currentGameId": null,
    "gamesPlayed": 0
  }
}
```

### List Public Lobbies

Lists lobbies that are **waiting for players** (status = `WAITING`). Lobbies with games in progress do NOT appear here - see Live Games instead.

```http
GET /api/lobbies?speed=standard&playerCount=2
```

**Response:**
```json
{
  "lobbies": [
    {
      "id": 123,
      "code": "ABC123",
      "hostUsername": "player1",
      "settings": { ... },
      "playerCount": 2,
      "currentPlayers": 1,
      "status": "waiting"
    }
  ]
}
```

### List Live Games (for Spectating)

Lists games currently in progress. Users can spectate any public game.

```http
GET /api/games/live?speed=standard&playerCount=2
```

**Response:**
```json
{
  "games": [
    {
      "gameId": "abc123-def456",
      "lobbyCode": "XYZ789",
      "players": [
        { "slot": 1, "username": "player1", "isAi": false },
        { "slot": 2, "username": "player2", "isAi": false }
      ],
      "settings": { ... },
      "currentTick": 1234,
      "startedAt": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Spectating:** Navigate to `/game/{gameId}` without a player key to spectate. The game WebSocket accepts spectator connections.

### Join Lobby

```http
POST /api/lobbies/{code}/join
Content-Type: application/json
Authorization: Bearer <token>  (optional)

{
  "preferredSlot": 2  // Optional, server assigns if not available
}
```

**Response:**
```json
{
  "playerKey": "secret-key-for-player-2",
  "slot": 2,
  "lobby": { ... }
}
```

**Errors:**
- `404 Not Found`: Lobby does not exist
- `409 Conflict`: Lobby is full or game is in progress
- `403 Forbidden`: Lobby is private (must have invite link)

---

## Backend Implementation

### LobbyManager

```python
# server/src/kfchess/lobby/manager.py

class LobbyManager:
    """Manages all active lobbies in memory."""

    def __init__(self):
        self._lobbies: dict[str, Lobby] = {}  # code -> Lobby
        self._player_keys: dict[str, dict[int, str]] = {}  # code -> {slot: key}
        self._player_slots: dict[str, int] = {}  # player_key -> slot
        self._lock = asyncio.Lock()

    async def create_lobby(
        self,
        host_user_id: int | None,
        host_username: str,
        settings: LobbySettings,
        add_ai: bool = False,
        ai_type: str = "bot:dummy",
    ) -> tuple[Lobby, str]:
        """Create a new lobby.

        Returns:
            Tuple of (lobby, player_key for host)
        """
        ...

    async def join_lobby(
        self,
        code: str,
        user_id: int | None,
        username: str,
        preferred_slot: int | None = None,
    ) -> tuple[Lobby, str, int]:
        """Join an existing lobby.

        Returns:
            Tuple of (lobby, player_key, slot)
        """
        ...

    async def leave_lobby(self, code: str, player_key: str) -> Lobby | None:
        """Remove a player from a lobby."""
        ...

    async def set_ready(self, code: str, player_key: str, ready: bool) -> Lobby:
        """Set a player's ready state."""
        ...

    async def update_settings(
        self, code: str, player_key: str, settings: LobbySettings
    ) -> Lobby:
        """Update lobby settings (host only)."""
        ...

    async def kick_player(self, code: str, host_key: str, slot: int) -> Lobby:
        """Kick a player from the lobby (host only)."""
        ...

    async def add_ai(self, code: str, host_key: str, ai_type: str) -> Lobby:
        """Add an AI player (host only)."""
        ...

    async def start_game(self, code: str, host_key: str) -> tuple[str, dict[int, str]]:
        """Start the game (host only).

        Returns:
            Tuple of (game_id, {slot: player_key})
        """
        ...

    async def end_game(self, code: str, winner: int | None) -> Lobby:
        """Called when a game ends. Resets lobby for rematch."""
        ...

    def get_lobby(self, code: str) -> Lobby | None:
        """Get a lobby by code."""
        ...

    def get_public_lobbies(
        self,
        status: LobbyStatus | None = None,
        speed: str | None = None,
        player_count: int | None = None,
    ) -> list[Lobby]:
        """Get all public lobbies, optionally filtered."""
        ...

    def validate_player_key(self, code: str, player_key: str) -> int | None:
        """Validate a player key and return their slot."""
        ...


# Global singleton
_lobby_manager: LobbyManager | None = None

def get_lobby_manager() -> LobbyManager:
    global _lobby_manager
    if _lobby_manager is None:
        _lobby_manager = LobbyManager()
    return _lobby_manager
```

### WebSocket Handler

```python
# server/src/kfchess/ws/lobby_handler.py

from fastapi import WebSocket, WebSocketDisconnect

class LobbyConnectionManager:
    """Manages WebSocket connections for lobbies."""

    def __init__(self):
        # code -> set of (websocket, slot)
        self.connections: dict[str, set[tuple[WebSocket, int]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, code: str, websocket: WebSocket, slot: int):
        """Add a connection to a lobby."""
        ...

    async def disconnect(self, code: str, websocket: WebSocket):
        """Remove a connection from a lobby."""
        ...

    async def broadcast(self, code: str, message: dict):
        """Broadcast a message to all connections in a lobby."""
        ...

    async def send_to_slot(self, code: str, slot: int, message: dict):
        """Send a message to a specific player."""
        ...


lobby_connection_manager = LobbyConnectionManager()


async def handle_lobby_websocket(
    websocket: WebSocket,
    code: str,
    player_key: str,
) -> None:
    """Handle a WebSocket connection for a lobby."""

    manager = get_lobby_manager()

    # Validate player key
    slot = manager.validate_player_key(code, player_key)
    if slot is None:
        await websocket.close(code=4001, reason="Invalid player key")
        return

    # Get lobby
    lobby = manager.get_lobby(code)
    if lobby is None:
        await websocket.close(code=4004, reason="Lobby not found")
        return

    # Connect
    await lobby_connection_manager.connect(code, websocket, slot)

    # Send initial state
    await websocket.send_json({
        "type": "lobby_state",
        "lobby": serialize_lobby(lobby),
    })

    try:
        while True:
            data = await websocket.receive_json()
            await _handle_message(websocket, code, slot, player_key, data)
    except WebSocketDisconnect:
        await _handle_disconnect(code, player_key)
    finally:
        await lobby_connection_manager.disconnect(code, websocket)


async def _handle_message(
    websocket: WebSocket,
    code: str,
    slot: int,
    player_key: str,
    data: dict,
) -> None:
    """Handle a WebSocket message."""

    msg_type = data.get("type")
    manager = get_lobby_manager()

    if msg_type == "ready":
        lobby = await manager.set_ready(code, player_key, data.get("ready", True))
        await lobby_connection_manager.broadcast(code, {
            "type": "player_ready",
            "slot": slot,
            "ready": data.get("ready", True),
        })

    elif msg_type == "update_settings":
        # Verify host
        lobby = manager.get_lobby(code)
        if lobby and lobby.host_slot != slot:
            await websocket.send_json({
                "type": "error",
                "code": "not_host",
                "message": "Only the host can change settings",
            })
            return

        settings = LobbySettings(**data["settings"])
        lobby = await manager.update_settings(code, player_key, settings)
        await lobby_connection_manager.broadcast(code, {
            "type": "settings_updated",
            "settings": serialize_settings(lobby.settings),
        })

    elif msg_type == "start_game":
        lobby = manager.get_lobby(code)
        if lobby and lobby.host_slot != slot:
            await websocket.send_json({
                "type": "error",
                "code": "not_host",
                "message": "Only the host can start the game",
            })
            return

        if lobby and not lobby.all_ready:
            await websocket.send_json({
                "type": "error",
                "code": "not_all_ready",
                "message": "All players must be ready to start",
            })
            return

        # Create game immediately (countdown happens on game board)
        await _create_and_start_game(code)

    elif msg_type == "kick":
        lobby = manager.get_lobby(code)
        if lobby and lobby.host_slot != slot:
            await websocket.send_json({
                "type": "error",
                "code": "not_host",
                "message": "Only the host can kick players",
            })
            return

        kick_slot = data.get("slot")
        if kick_slot == slot:
            await websocket.send_json({
                "type": "error",
                "code": "cannot_kick_self",
                "message": "Cannot kick yourself",
            })
            return

        lobby = await manager.kick_player(code, player_key, kick_slot)
        await lobby_connection_manager.broadcast(code, {
            "type": "player_left",
            "slot": kick_slot,
            "reason": "kicked",
        })

    # ... handle other message types

    elif msg_type == "ping":
        await websocket.send_json({"type": "pong"})


async def _create_and_start_game(code: str) -> None:
    """Create a game from the lobby and start it.

    The game will show a 3-second countdown on the board before starting.
    """
    manager = get_lobby_manager()
    lobby = manager.get_lobby(code)

    if lobby is None or lobby.status != LobbyStatus.WAITING:
        return

    # Create game via GameService (game starts in COUNTDOWN status)
    # Pass lobby code so game can reference back to lobby for post-game flow
    game_id, player_keys = await manager.start_game(code, lobby_code=code, ...)

    # Update lobby status
    lobby.status = LobbyStatus.IN_GAME
    lobby.current_game_id = game_id

    # Send game starting message to each player with their key
    # Players will navigate to game page where countdown is shown
    for slot, player in lobby.players.items():
        if not player.is_ai:
            await lobby_connection_manager.send_to_slot(code, slot, {
                "type": "game_starting",
                "gameId": game_id,
                "lobbyCode": code,  # For post-game "Return to Lobby"
                "playerKey": player_keys.get(slot),
            })


async def _handle_disconnect(code: str, player_key: str) -> None:
    """Handle a player disconnecting - they leave the lobby."""
    manager = get_lobby_manager()
    slot = manager.validate_player_key(code, player_key)

    if slot is None:
        return

    lobby = manager.get_lobby(code)
    if lobby is None:
        return

    # If in game, don't remove from lobby (handled by game)
    if lobby.status == LobbyStatus.IN_GAME:
        return

    # Remove player from lobby
    was_host = (lobby.host_slot == slot)
    lobby = await manager.leave_lobby(code, player_key)

    if lobby is None:
        # Lobby was deleted (no human players left)
        return

    await lobby_connection_manager.broadcast(code, {
        "type": "player_left",
        "slot": slot,
        "reason": "disconnected",
    })

    # Transfer host if needed (to next human player)
    if was_host:
        human_players = [p for p in lobby.players.values() if not p.is_ai]
        if human_players:
            new_host_slot = min(p.slot for p in human_players)
            lobby.host_slot = new_host_slot
            await lobby_connection_manager.broadcast(code, {
                "type": "host_changed",
                "newHostSlot": new_host_slot,
            })
```

---

## Frontend Implementation

### Lobby Store

```typescript
// client/src/stores/lobby.ts

interface LobbyState {
  // Connection state
  code: string | null;
  playerKey: string | null;
  mySlot: number | null;
  connectionState: 'disconnected' | 'connecting' | 'connected';
  error: string | null;

  // Lobby data
  lobby: Lobby | null;

  // Actions - REST
  createLobby: (settings: LobbySettings, addAi?: boolean) => Promise<string>;
  joinLobby: (code: string) => Promise<void>;
  fetchPublicLobbies: () => Promise<Lobby[]>;

  // Actions - WebSocket
  connect: (code: string, playerKey: string) => void;
  disconnect: () => void;
  setReady: (ready: boolean) => void;
  updateSettings: (settings: Partial<LobbySettings>) => void;
  kickPlayer: (slot: number) => void;
  addAi: (aiType: string) => void;
  removeAi: (slot: number) => void;
  startGame: () => void;
  leaveLobby: () => void;
  returnToLobby: () => void;

  // Internal
  _ws: WebSocket | null;
  _handleMessage: (event: MessageEvent) => void;
}

export const useLobbyStore = create<LobbyState>((set, get) => ({
  code: null,
  playerKey: null,
  mySlot: null,
  connectionState: 'disconnected',
  error: null,
  lobby: null,
  _ws: null,

  createLobby: async (settings, addAi = false) => {
    const response = await fetch('/api/lobbies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings, addAi, aiType: 'bot:dummy' }),
    });

    if (!response.ok) {
      throw new Error('Failed to create lobby');
    }

    const data = await response.json();
    set({
      code: data.code,
      playerKey: data.playerKey,
      mySlot: data.slot,
      lobby: data.lobby,
    });

    return data.code;
  },

  joinLobby: async (code) => {
    const response = await fetch(`/api/lobbies/${code}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to join lobby');
    }

    const data = await response.json();
    set({
      code,
      playerKey: data.playerKey,
      mySlot: data.slot,
      lobby: data.lobby,
    });
  },

  connect: (code, playerKey) => {
    const { _ws } = get();
    if (_ws) {
      _ws.close();
    }

    set({ connectionState: 'connecting', error: null });

    const ws = new WebSocket(`/ws/lobby/${code}?player_key=${playerKey}`);

    ws.onopen = () => {
      set({ connectionState: 'connected', _ws: ws });
    };

    ws.onmessage = (event) => {
      get()._handleMessage(event);
    };

    ws.onclose = () => {
      set({ connectionState: 'disconnected', _ws: null });
    };

    ws.onerror = () => {
      set({ error: 'Connection error', connectionState: 'disconnected' });
    };
  },

  _handleMessage: (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'lobby_state':
        set({ lobby: data.lobby });
        break;

      case 'player_joined':
        set((state) => ({
          lobby: state.lobby ? {
            ...state.lobby,
            players: {
              ...state.lobby.players,
              [data.slot]: data.player,
            },
          } : null,
        }));
        break;

      case 'player_left':
        set((state) => {
          if (!state.lobby) return state;
          const { [data.slot]: _, ...remainingPlayers } = state.lobby.players;
          return {
            lobby: {
              ...state.lobby,
              players: remainingPlayers,
            },
          };
        });
        break;

      case 'player_ready':
        set((state) => {
          if (!state.lobby) return state;
          const player = state.lobby.players[data.slot];
          if (!player) return state;
          return {
            lobby: {
              ...state.lobby,
              players: {
                ...state.lobby.players,
                [data.slot]: { ...player, isReady: data.ready },
              },
            },
          };
        });
        break;

      case 'settings_updated':
        set((state) => ({
          lobby: state.lobby ? {
            ...state.lobby,
            settings: data.settings,
          } : null,
        }));
        break;

      case 'host_changed':
        set((state) => ({
          lobby: state.lobby ? {
            ...state.lobby,
            hostSlot: data.newHostSlot,
          } : null,
        }));
        break;

      case 'game_starting':
        // Store game info and trigger navigation
        const { gameId, playerKey } = data;
        // Navigation will be handled by the component
        set((state) => ({
          lobby: state.lobby ? {
            ...state.lobby,
            status: 'in_game',
            currentGameId: gameId,
          } : null,
        }));
        // Store player key for game
        if (gameId && playerKey) {
          sessionStorage.setItem(`playerKey_${gameId}`, playerKey);
        }
        // Navigate (handled by Lobby page component)
        break;

      case 'game_ended':
        set((state) => ({
          lobby: state.lobby ? {
            ...state.lobby,
            status: 'finished',
            gamesPlayed: state.lobby.gamesPlayed + 1,
          } : null,
        }));
        break;

      case 'error':
        set({ error: data.message });
        break;
    }
  },

  setReady: (ready) => {
    const { _ws } = get();
    _ws?.send(JSON.stringify({ type: 'ready', ready }));
  },

  updateSettings: (settings) => {
    const { _ws, lobby } = get();
    if (!lobby) return;
    _ws?.send(JSON.stringify({
      type: 'update_settings',
      settings: { ...lobby.settings, ...settings },
    }));
  },

  startGame: () => {
    const { _ws } = get();
    _ws?.send(JSON.stringify({ type: 'start_game' }));
  },

  leaveLobby: () => {
    const { _ws } = get();
    _ws?.send(JSON.stringify({ type: 'leave' }));
    _ws?.close();
    set({
      code: null,
      playerKey: null,
      mySlot: null,
      lobby: null,
      connectionState: 'disconnected',
    });
  },

  // ... other actions
}));
```

### Lobby Page

```typescript
// client/src/pages/Lobby.tsx

export function Lobby() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();

  const lobby = useLobbyStore((s) => s.lobby);
  const mySlot = useLobbyStore((s) => s.mySlot);
  const playerKey = useLobbyStore((s) => s.playerKey);
  const connectionState = useLobbyStore((s) => s.connectionState);
  const connect = useLobbyStore((s) => s.connect);
  const setReady = useLobbyStore((s) => s.setReady);
  const startGame = useLobbyStore((s) => s.startGame);
  const leaveLobby = useLobbyStore((s) => s.leaveLobby);

  // Connect on mount
  useEffect(() => {
    if (code && playerKey) {
      connect(code, playerKey);
    }
    return () => {
      // Don't disconnect on unmount if navigating to game
      // The game page will handle the transition
    };
  }, [code, playerKey]);

  // Navigate to game when it starts
  useEffect(() => {
    if (lobby?.status === 'in_game' && lobby.currentGameId) {
      navigate(`/game/${lobby.currentGameId}`);
    }
  }, [lobby?.status, lobby?.currentGameId]);

  const isHost = mySlot === lobby?.hostSlot;
  const myPlayer = mySlot ? lobby?.players[mySlot] : null;
  const allReady = lobby ? Object.values(lobby.players).every((p) => p.isReady) : false;
  const isFull = lobby ? Object.keys(lobby.players).length >= lobby.settings.playerCount : false;
  const canStart = isHost && allReady && isFull;

  if (!lobby) {
    return <div>Loading lobby...</div>;
  }

  return (
    <div className="lobby-page">
      <header className="lobby-header">
        <h1>Lobby: {code}</h1>
        <button className="btn-link" onClick={leaveLobby}>Leave</button>
      </header>

      {/* Settings (host can edit) */}
      <LobbySettings
        settings={lobby.settings}
        isHost={isHost}
        disabled={lobby.status !== 'waiting'}
      />

      {/* Player slots */}
      <div className="player-slots">
        {Array.from({ length: lobby.settings.playerCount }, (_, i) => i + 1).map((slot) => (
          <PlayerSlot
            key={slot}
            slot={slot}
            player={lobby.players[slot]}
            isHost={slot === lobby.hostSlot}
            isMe={slot === mySlot}
            canKick={isHost && slot !== mySlot && !lobby.players[slot]?.isAi}
          />
        ))}
      </div>

      {/* Actions */}
      <div className="lobby-actions">
        {myPlayer && !myPlayer.isReady && (
          <button className="btn btn-primary" onClick={() => setReady(true)}>
            Ready
          </button>
        )}

        {myPlayer?.isReady && !isHost && (
          <button className="btn btn-secondary" onClick={() => setReady(false)}>
            Cancel Ready
          </button>
        )}

        {isHost && !myPlayer?.isReady && (
          <button className="btn btn-secondary" onClick={() => setReady(true)}>
            Ready
          </button>
        )}

        {isHost && myPlayer?.isReady && (
          <>
            <button className="btn btn-secondary" onClick={() => setReady(false)}>
              Cancel Ready
            </button>
            <button
              className="btn btn-primary"
              onClick={startGame}
              disabled={!canStart}
            >
              Start Game
            </button>
          </>
        )}
      </div>

      {/* Share link */}
      {lobby.settings.isPublic === false && (
        <div className="share-section">
          <p>Share this link to invite players:</p>
          <code>{window.location.href}</code>
          <button onClick={() => navigator.clipboard.writeText(window.location.href)}>
            Copy
          </button>
        </div>
      )}
    </div>
  );
}
```

### Updated Home Page

```typescript
// client/src/pages/Home.tsx (modified)

export function Home() {
  const navigate = useNavigate();
  const createLobby = useLobbyStore((s) => s.createLobby);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showJoinModal, setShowJoinModal] = useState(false);

  const handlePlayVsAI = async () => {
    // Create lobby with AI
    const code = await createLobby(
      { isPublic: false, speed: 'standard', playerCount: 2, isRanked: false },
      true // addAi
    );
    navigate(`/lobby/${code}`);
  };

  const handleCreateLobby = () => {
    setShowCreateModal(true);
  };

  const handleBrowseLobbies = () => {
    navigate('/lobbies');
  };

  return (
    <div className="home-page">
      <h1>Kung Fu Chess</h1>

      <div className="play-options">
        <button onClick={handlePlayVsAI}>Play vs AI</button>
        <button onClick={handleCreateLobby}>Create Lobby</button>
        <button onClick={handleBrowseLobbies}>Browse Lobbies</button>
        <button onClick={() => setShowJoinModal(true)}>Join by Code</button>
      </div>

      {showCreateModal && (
        <CreateLobbyModal onClose={() => setShowCreateModal(false)} />
      )}

      {showJoinModal && (
        <JoinLobbyModal onClose={() => setShowJoinModal(false)} />
      )}
    </div>
  );
}
```

### Updated Game Over Modal

```typescript
// client/src/components/game/GameOverModal.tsx (modified)

export function GameOverModal({ winner, reason, gameId }: GameOverModalProps) {
  const navigate = useNavigate();
  const lobbyCode = useLobbyStore((s) => s.code);

  const handleReturnToLobby = () => {
    if (lobbyCode) {
      navigate(`/lobby/${lobbyCode}`);
    } else {
      navigate('/');
    }
  };

  return (
    <div className="modal game-over-modal">
      <h2>{winner === myPlayer ? 'Victory!' : 'Defeat'}</h2>
      <p>{formatReason(reason)}</p>

      <div className="modal-actions">
        {lobbyCode && (
          <button className="btn btn-primary" onClick={handleReturnToLobby}>
            Return to Lobby
          </button>
        )}
        <button className="btn btn-secondary" onClick={() => navigate(`/replay/${gameId}`)}>
          View Replay
        </button>
        <button className="btn btn-link" onClick={() => navigate('/')}>
          Home
        </button>
      </div>
    </div>
  );
}
```

---

## Edge Cases & Error Handling

### Player Lock (One Lobby Per Player)

**Behavior:** A player can only be in one lobby at a time. Joining a new lobby automatically leaves any existing lobby.

**Identity for Player Lock:**
- **Logged-in users**: Use `user_id`
- **Anonymous users**: Use `guest_id` - a random UUID stored in localStorage

The guest ID is generated on the client when first needed and persists across page reloads. This ensures anonymous players can't bypass the one-lobby rule.

```typescript
// client/src/utils/identity.ts
export function getPlayerId(): string {
  const user = useAuthStore.getState().user;
  if (user) {
    return `user:${user.id}`;
  }

  // Anonymous user - use persistent guest ID
  let guestId = localStorage.getItem('kfchess_guest_id');
  if (!guestId) {
    guestId = crypto.randomUUID();
    localStorage.setItem('kfchess_guest_id', guestId);
  }
  return `guest:${guestId}`;
}
```

```python
async def join_lobby(
    self,
    code: str,
    player_id: str,  # "user:123" or "guest:uuid"
    username: str,
) -> tuple[Lobby, str, int]:
    # If player is already in a lobby, leave it first
    existing_lobby = self._find_lobby_for_player(player_id)
    if existing_lobby and existing_lobby.code != code:
        await self.leave_lobby(existing_lobby.code, player_id)

    # Normal join logic...
```

**Frontend:** The lobby store tracks the current lobby. Navigation away from the lobby page (except to the game) triggers a leave.

### Navigation and Disconnection

**Behavior:** WebSocket disconnection = leaving the lobby. This includes:
- Closing the browser/tab
- Navigating to a different page (except the game page during transition)
- Network disconnection

There is no "reconnect to same slot" - if you disconnect, you leave and must rejoin (getting a new slot if one is available).

```python
async def _handle_disconnect(code: str, player_key: str) -> None:
    """Handle a player disconnecting - they leave the lobby."""
    manager = get_lobby_manager()
    slot = manager.validate_player_key(code, player_key)

    if slot is None:
        return

    lobby = manager.get_lobby(code)
    if lobby is None:
        return

    # If in game, don't remove from lobby (handled by game)
    if lobby.status == LobbyStatus.IN_GAME:
        return

    # Remove player from lobby
    await manager.leave_lobby(code, player_key)
```

### Host Leaves

**Behavior:** Transfer host to the next human player (lowest slot number). If no human players remain, delete the lobby.

```python
async def _handle_host_leave(code: str, old_host_slot: int) -> None:
    lobby = manager.get_lobby(code)

    # Check for remaining human players
    human_players = [p for p in lobby.players.values() if not p.is_ai]
    if not human_players:
        # No human players left, delete lobby
        await manager.delete_lobby(code)
        return

    # Transfer to lowest human slot
    new_host_slot = min(p.slot for p in human_players)
    lobby.host_slot = new_host_slot

    await lobby_connection_manager.broadcast(code, {
        "type": "host_changed",
        "newHostSlot": new_host_slot,
    })
```

### AI Players

**Behavior:** AI players are automatically ready and don't disconnect.

```python
@dataclass
class LobbyPlayer:
    # ...
    is_ai: bool = False

    @property
    def is_ready(self) -> bool:
        if self.is_ai:
            return True  # AI is always ready
        return self._is_ready
```

### Settings Changes with Players

**Restrictions:**
- Cannot reduce `playerCount` below current player count
- Cannot enable `isRanked` if there are AI players

**Auto-Unready on Settings Change:** When the host changes any setting, all human players are automatically set to not ready. This prevents bait-and-switch scenarios where the host changes settings after players have readied up.

```python
async def update_settings(self, code: str, player_key: str, settings: LobbySettings) -> Lobby:
    lobby = self._lobbies.get(code)

    # Validate player count change
    if settings.player_count < len(lobby.players):
        raise ValidationError("Cannot reduce player count below current players")

    # Validate ranked with AI
    if settings.is_ranked and any(p.is_ai for p in lobby.players.values()):
        raise ValidationError("Cannot enable ranked with AI players")

    # Check if settings actually changed
    settings_changed = (
        settings.is_public != lobby.settings.is_public or
        settings.speed != lobby.settings.speed or
        settings.player_count != lobby.settings.player_count or
        settings.is_ranked != lobby.settings.is_ranked
    )

    lobby.settings = settings

    # Auto-unready all human players on any settings change
    if settings_changed:
        for player in lobby.players.values():
            if not player.is_ai:
                player.is_ready = False

    return lobby
```

The server broadcasts both `settings_updated` and `player_ready` messages for each affected player:

```python
if settings_changed:
    await lobby_connection_manager.broadcast(code, {
        "type": "settings_updated",
        "settings": serialize_settings(lobby.settings),
    })
    # Notify about unready players
    for slot, player in lobby.players.items():
        if not player.is_ai:
            await lobby_connection_manager.broadcast(code, {
                "type": "player_ready",
                "slot": slot,
                "ready": False,
            })
```

### Lobby Cleanup

**Behavior:** Lobbies are deleted when no human players remain, **except** if a game is in progress. A background task also cleans up orphaned lobbies.

**Cleanup Rules:**
1. Immediate cleanup: No human players AND status is NOT `IN_GAME`
2. Background cleanup: Orphaned lobbies (no humans, not in game) older than 1 hour
3. **Never cleanup lobbies with `IN_GAME` status** - the game needs the lobby for post-game flow

```python
async def leave_lobby(self, code: str, player_key: str) -> Lobby | None:
    """Remove a player from a lobby."""
    lobby = self._lobbies.get(code)
    # ... remove player ...

    # Check if any human players remain
    human_players = [p for p in lobby.players.values() if not p.is_ai]

    # Don't delete if game is in progress - needed for post-game flow
    if not human_players and lobby.status != LobbyStatus.IN_GAME:
        await self.delete_lobby(code)
        return None

    return lobby

async def _cleanup_orphaned_lobbies() -> None:
    """Background task to clean up orphaned lobbies."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes

        now = datetime.utcnow()
        orphan_threshold = timedelta(hours=1)
        finished_threshold = timedelta(hours=24)  # Longer for finished games

        for code, lobby in list(manager._lobbies.items()):
            human_players = [p for p in lobby.players.values() if not p.is_ai]

            # Never cleanup lobbies with live games
            if lobby.status == LobbyStatus.IN_GAME:
                continue

            # Cleanup empty WAITING lobbies after 1 hour
            if lobby.status == LobbyStatus.WAITING and not human_players:
                if now - lobby.created_at > orphan_threshold:
                    await manager.delete_lobby(code)

            # Cleanup FINISHED lobbies after 24 hours (regardless of players)
            if lobby.status == LobbyStatus.FINISHED:
                # Use game end time if available, otherwise created_at
                age = now - (lobby.game_finished_at or lobby.created_at)
                if age > finished_threshold:
                    await manager.delete_lobby(code)
```

**Note:** When a game finishes, the server should call `lobby_manager.end_game(code)` to update the lobby status to `FINISHED` and record `game_finished_at`. This ensures the lobby is available for "Return to Lobby" but eventually gets cleaned up.

### Game Start (Race Condition Handling)

**Behavior:** When the host clicks "Start Game", the server performs an atomic check:
1. Verify all players are ready
2. If check passes, **immediately** transition to game - no further checks
3. Any concurrent unready/leave messages are ignored once the check passes

This prevents race conditions where a player unreadies at the exact moment the host clicks start. The check is the commitment point - once it passes, the game will start.

```python
async def start_game(self, code: str, host_key: str) -> tuple[str, dict[int, str]]:
    async with self._lock:  # Atomic operation
        lobby = self._lobbies.get(code)

        # Validate
        if not lobby.all_ready:
            raise ValidationError("Not all players ready")

        # Immediately transition - no going back
        lobby.status = LobbyStatus.IN_GAME

        # Create game
        game_id, player_keys = await self._create_game(lobby)
        lobby.current_game_id = game_id

        return game_id, player_keys
```

### Game Transition

**Behavior:** Once the start check passes:
1. Lobby status immediately becomes `IN_GAME`
2. Server creates the game via GameService
3. Server sends `game_starting` message to all players with their game keys
4. Players navigate to `/game/{gameId}` where a 3-second countdown is shown on the board

The countdown happens on the **game board**, not in the lobby.

### Disconnects During Countdown/Game

**Behavior:** Once the game starts (including countdown), disconnects are treated as **AFK**, not as leaving:
- The game continues without the disconnected player
- Their pieces remain on the board but don't move
- They can rejoin the game if they reconnect (using their player key)
- The lobby remains in `IN_GAME` status

This is intentional - games shouldn't be cancelled because someone's internet hiccupped. The disconnected player can:
1. Reconnect to the game (if they still have their player key in sessionStorage)
2. Wait for the game to finish and return to the lobby
3. Accept the loss if they can't reconnect

### Return to Lobby After Game

**Behavior:** When a game finishes:
1. Server notifies lobby manager: `lobby_manager.end_game(code, winner)`
2. Lobby status changes from `IN_GAME` to `FINISHED`
3. Ready states are reset for all human players
4. Players can click "Return to Lobby" in the game over modal
5. Players navigate to `/lobby/{code}` and reconnect via WebSocket

**Edge Case - Lobby Deleted:** If the lobby was somehow deleted (server crash, manual cleanup), "Return to Lobby" should redirect to home with a message.

```python
async def end_game(self, code: str, winner: int | None) -> Lobby | None:
    """Called when a game ends. Prepares lobby for rematch."""
    lobby = self._lobbies.get(code)
    if lobby is None:
        return None

    lobby.status = LobbyStatus.FINISHED
    lobby.current_game_id = None
    lobby.games_played += 1
    lobby.game_finished_at = datetime.utcnow()

    # Reset ready states for human players
    for player in lobby.players.values():
        if not player.is_ai:
            player.is_ready = False

    return lobby
```

### Multiple Browser Tabs

**Behavior:** If a player opens the same lobby in multiple tabs:
- Each tab creates a separate WebSocket connection
- All tabs receive the same broadcasts
- Actions from any tab affect the shared player state
- This is intentional - we don't prevent multi-tab usage

**Potential Issue:** If the player has the lobby open in one tab and navigates away in another, the disconnect from the second tab could leave the lobby (depending on implementation).

**Resolution:** The `leave_lobby` operation should be idempotent and check if the player is still in the lobby before removing them. Additionally, the "player lock" check happens at join time, not continuously.

### Direct URL Navigation

**Behavior:** If a user navigates directly to `/lobby/{code}` without joining:
1. Client checks if `playerKey` exists in store for this lobby
2. If not, attempt to join via REST API
3. If join fails (full, private, doesn't exist), redirect to home with error

```typescript
// Lobby.tsx
useEffect(() => {
  if (code && !playerKey) {
    // Try to join the lobby
    joinLobby(code).catch((error) => {
      // Redirect to home with error message
      navigate('/', { state: { error: error.message } });
    });
  }
}, [code, playerKey]);
```

### Lobby Code Collision

**Behavior:** Lobby codes are generated randomly. While collision is unlikely with sufficient entropy, we should handle it.

**Resolution:** Use 6-character alphanumeric codes (excluding ambiguous characters like O/0, I/1/l) = 30^6 ≈ 729 million combinations. Check for collision on generation and regenerate if needed.

```python
def generate_lobby_code() -> str:
    """Generate a unique lobby code."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # No O/0/I/1/L
    while True:
        code = ''.join(random.choices(alphabet, k=6))
        if code not in self._lobbies:
            return code
```

### Rate Limiting

**Behavior:** To prevent abuse, rate limit lobby operations:
- Lobby creation: 5 per minute per player
- Join attempts: 10 per minute per player
- Settings changes: 10 per minute per lobby

These limits are enforced server-side and return HTTP 429 when exceeded.

### Player Key Security

**Concern:** Player keys are passed in WebSocket URL query strings, which can be logged.

**Mitigation:**
1. Player keys are short-lived (valid only for current lobby session)
2. Keys are regenerated on each game start
3. HTTPS encrypts the URL in transit
4. Consider moving to WebSocket handshake authentication in future

---

## Game Countdown

The 3-second countdown happens on the **game board**, not in the lobby. This provides a clear separation between the lobby (preparation) and the game (action).

### Game State Changes

```python
class GameStatus(Enum):
    COUNTDOWN = "countdown"  # 3-second countdown before game
    PLAYING = "playing"      # Game in progress
    FINISHED = "finished"    # Game has ended

@dataclass
class GameState:
    # ... existing fields ...
    lobby_code: str | None = None  # Reference back to creating lobby for post-game flow
```

The `lobby_code` field allows the game to know which lobby it came from, enabling the "Return to Lobby" functionality after the game ends.

### Countdown Flow

1. Host clicks "Start Game" in lobby
2. Server creates game with status `COUNTDOWN`
3. Server sends `game_starting` to all lobby players
4. Players navigate to `/game/{gameId}`
5. Game page shows countdown overlay on the board (3... 2... 1...)
6. Server ticks countdown (3 seconds = 30 ticks at 10 ticks/sec)
7. Game transitions to `PLAYING` status
8. Countdown overlay fades out, game begins

### Frontend Implementation

```typescript
// client/src/components/game/GameCountdown.tsx

interface GameCountdownProps {
  secondsRemaining: number;  // 3, 2, 1, 0
}

export function GameCountdown({ secondsRemaining }: GameCountdownProps) {
  if (secondsRemaining <= 0) return null;

  return (
    <div className="game-countdown-overlay">
      <div className="countdown-number">{secondsRemaining}</div>
    </div>
  );
}
```

```typescript
// In Game.tsx
const status = useGameStore((s) => s.status);
const countdownTick = useGameStore((s) => s.countdownTick);  // 0-30

// Convert ticks to seconds (10 ticks/sec, so tick 0-9 = 3, 10-19 = 2, 20-29 = 1)
const countdownSeconds = status === 'countdown'
  ? Math.ceil((30 - countdownTick) / 10)
  : 0;

return (
  <div className="game-page">
    <GameBoard ... />
    {status === 'countdown' && (
      <GameCountdown secondsRemaining={countdownSeconds} />
    )}
    {/* No more ready button needed */}
  </div>
);
```

### WebSocket Protocol Update

The game WebSocket now sends countdown updates:

```typescript
// State update during countdown
{
  "type": "state_update",
  "status": "countdown",
  "tick": 15,  // Countdown tick (0-29)
  "pieces": [...],
  ...
}

// Game starts
{
  "type": "game_started",
  "tick": 0  // Game tick resets to 0 when playing starts
}
```

---

## Implementation Plan

### Phase 1: Data Models & Manager ✅

1. ✅ Create lobby models (`server/src/kfchess/lobby/models.py`)
2. ⏳ Create database models and migration (deferred - using in-memory for MVP)
3. ✅ Implement LobbyManager class (`server/src/kfchess/lobby/manager.py`)
4. ✅ Write unit tests for LobbyManager

**Files:**
- `server/src/kfchess/lobby/models.py` ✅
- `server/src/kfchess/lobby/manager.py` ✅
- `server/alembic/versions/003_add_lobbies.py` (deferred)
- `server/tests/unit/lobby/test_manager.py` ✅

### Phase 2: REST API ✅

1. ✅ Create lobby API routes (`server/src/kfchess/api/lobbies.py`)
2. ✅ Implement create, join, list (WAITING only), delete endpoints
3. ⏳ Add live games endpoint to games API (deferred to Phase 5)
4. ✅ Write API tests

**Files:**
- `server/src/kfchess/api/lobbies.py` ✅
- `server/src/kfchess/api/games.py` (live games endpoint deferred)
- `server/tests/unit/test_api_lobbies.py` ✅

### Phase 3: WebSocket Handler ✅

1. ✅ Create lobby WebSocket handler (`server/src/kfchess/ws/lobby_handler.py`)
2. ✅ Implement all message handlers
3. ✅ Integrate with GameService for game creation
4. ✅ Write WebSocket tests
5. ✅ Wire up game end notification from game handler

**Files:**
- `server/src/kfchess/ws/lobby_handler.py` ✅
- `server/src/kfchess/ws/handler.py` (added `_notify_lobby_game_ended`) ✅
- `server/src/kfchess/lobby/manager.py` (added `find_lobby_by_game`) ✅
- `server/tests/unit/test_lobby_websocket.py` ✅

### Phase 4: Frontend Store

1. Update lobby store with full functionality
2. Add WebSocket connection handling
3. Add REST API calls

**Files:**
- `client/src/stores/lobby.ts`
- `client/src/api/client.ts` (add lobby endpoints)
- `client/src/api/types.ts` (add lobby types)

### Phase 5: Frontend Pages & Components

1. Create Lobby page
2. Create Lobbies browser page
3. Create lobby components (settings, player slots)
4. Update Home page with new flow
5. Update GameOverModal with "Return to Lobby"
6. Add countdown display to Game page (replaces ready button)

**Files:**
- `client/src/pages/Lobby.tsx`
- `client/src/pages/Lobby.css`
- `client/src/pages/Lobbies.tsx` (public lobbies waiting for players)
- `client/src/pages/Lobbies.css`
- `client/src/pages/LiveGames.tsx` (games in progress for spectating)
- `client/src/pages/LiveGames.css`
- `client/src/components/lobby/LobbySettings.tsx`
- `client/src/components/lobby/PlayerSlot.tsx`
- `client/src/components/lobby/CreateLobbyModal.tsx`
- `client/src/components/lobby/JoinLobbyModal.tsx`
- `client/src/pages/Home.tsx` (update)
- `client/src/pages/Game.tsx` (add countdown, remove ready button)
- `client/src/components/game/GameOverModal.tsx` (update)
- `client/src/components/game/GameCountdown.tsx` (new)
- `client/src/App.tsx` (add routes)

### Phase 6: Integration & Polish

1. Test full flow: create → join → ready → start → play → return
2. Test edge cases (disconnect, kick, settings changes)
3. Add loading states and error handling
4. Polish UI/UX

---

## Design Decisions

### 1. Lobby vs Game IDs

**Decision:** Lobbies have a separate ID (short code) from games (UUID).

**Rationale:**
- Lobby codes are short and shareable (e.g., "ABC123")
- Game IDs are UUIDs for uniqueness across rematches
- Same lobby can have multiple games (rematch flow)

### 2. Universal Lobbies (Including Campaign)

**Decision:** Every game goes through a lobby, including campaign levels.

**Rationale:**
- Consistent architecture for all game modes
- Lobby serves as the "player lock" - one game at a time
- Campaign lobbies can have locked settings based on the level
- Simplifies the codebase - no special case for "direct game start"

### 3. Player Lock (One Lobby Per Player)

**Decision:** A player can only be in one lobby at a time. Joining a new lobby automatically leaves any existing one.

**Rationale:**
- Prevents players from being in multiple games
- Clear mental model for players
- Simplifies reconnection logic (no slot preservation needed)
- Lobby is the authoritative "where is this player?" state

### 4. Disconnect = Leave

**Decision:** WebSocket disconnection means leaving the lobby. No automatic reconnection to the same slot.

**Rationale:**
- Simple and predictable behavior
- Avoids complex reconnection state management
- Players can rejoin manually if slots are available
- Consistent with how most multiplayer games work

### 5. Countdown on Game Board

**Decision:** The 3-second countdown happens on the game board, not in the lobby.

**Rationale:**
- Players can't "unready" during countdown - once started, committed
- Visual context of the board during countdown is better UX
- Replaces the current "ready up" button on the game page
- Cleaner separation: lobby = preparation, game = action

### 6. AI Auto-Ready

**Decision:** AI players are always marked as ready.

**Rationale:**
- No user action needed for AI
- Simplifies the ready logic
- Host still needs to click "Start"

### 7. Host Cannot Skip Ready

**Decision:** Host must be ready themselves before starting.

**Rationale:**
- Consistent rules for all players
- Prevents accidental game starts
- Host can use "Start Game" button as implicit ready

**Implementation:** When host clicks "Start Game", we first set them as ready if they aren't already.

### 8. Host Transfer to Human Players Only

**Decision:** Host transfers to the next human player (lowest slot) when original host leaves. If no human players remain, delete the lobby.

**Rationale:**
- AI can't control the lobby
- No point keeping a lobby with only AI players
- Deterministic and predictable

### 9. Lobby Cleanup on No Humans

**Decision:** Lobby is deleted immediately when the last human player leaves, regardless of AI players remaining.

**Rationale:**
- AI-only lobbies serve no purpose
- Prevents orphaned lobbies
- Cleaner resource management

### 10. No Lobby Chat (MVP)

**Decision:** Defer lobby chat to a future phase.

**Rationale:**
- Adds complexity (message history, moderation)
- Players can use external communication
- Focus on core functionality first

### 11. Atomic Game Start

**Decision:** Once the "all players ready" check passes, the game starts unconditionally. No further state changes can prevent it.

**Rationale:**
- Prevents race conditions where players unready at the exact moment of start
- Simple mental model: click Start → game happens
- The all_ready check is the commitment point

### 12. Auto-Unready on Settings Change

**Decision:** When the host changes any lobby setting, all human players are automatically set to not ready.

**Rationale:**
- Prevents bait-and-switch (host changes settings after players ready)
- Players should confirm they're still willing to play with new settings
- Simple and predictable behavior

### 13. Disconnects During Game = AFK

**Decision:** Once a game starts (including countdown), disconnects are treated as AFK, not as leaving. The game continues without the disconnected player.

**Rationale:**
- Games shouldn't be cancelled due to network hiccups
- Consistent with competitive game behavior
- Players can rejoin if they reconnect quickly
- Avoids griefing (disconnect to cancel losing game)

### 14. Anonymous Player Tracking

**Decision:** Anonymous players are tracked using a `guest_id` (UUID) stored in localStorage, not just session-based tracking.

**Rationale:**
- Enables the "one lobby per player" rule for guests
- Persists across page reloads within the same browser
- Different browsers/devices get different IDs (intentional)
- Simple implementation, no server-side session management needed

### 15. Game-to-Lobby Tracking

**Decision:** The LobbyManager maintains a `_game_to_lobby` mapping (game_id → lobby_code) to enable game end notifications.

**Rationale:**
- Game handler needs to notify the lobby when a game ends
- Game doesn't know its lobby code, only its game ID
- Reverse lookup allows decoupled notification from game handler to lobby
- Mapping is updated when game starts (may differ from pre-generated ID) and cleared when game ends

### 16. game_starting Sent to All Human Players

**Decision:** The `game_starting` message is sent to ALL human players in the lobby, not just the host.

**Rationale:**
- Future-proofs for multiplayer lobbies with 2+ human players
- All players need their game player_key to join the game
- Consistent behavior regardless of player count

---

## Future Enhancements

- **Lobby Chat**: Text chat in the waiting room
- **Spectator Slots**: Allow spectators to watch from lobby
- **Team Selection**: For 4-player mode, allow team configuration
- **Saved Settings**: Remember user's preferred lobby settings
- **Quick Rematch**: One-click rematch without going back to lobby
- **Invite System**: Send in-app invitations to friends
- **Lobby Timeout Warning**: Warn players before auto-kick for inactivity

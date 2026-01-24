# Kung Fu Chess - Rebuild Architecture

This document defines the architecture for the rebuilt Kung Fu Chess game. It serves as the blueprint for implementation.

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Directory Structure](#directory-structure)
4. [Backend Architecture](#backend-architecture)
5. [Frontend Architecture](#frontend-architecture)
6. [Game Engine](#game-engine)
7. [Real-Time Communication](#real-time-communication)
8. [Database Schema](#database-schema)
9. [AI System](#ai-system)
10. [Authentication](#authentication)
11. [Deployment Architecture](#deployment-architecture)
12. [Testing Strategy](#testing-strategy)
13. [Development Workflow](#development-workflow)
14. [Migration Strategy](#migration-strategy)
15. [Future: 4-Player Mode](#future-4-player-mode)

---

## Overview

> **Note**: This document serves as both the architecture blueprint and implementation reference.
> See the "Implementation Status" section at the end for current progress.
> See `CLAUDE.md` in the repo root for quick developer reference.

### Goals

1. **Maintainability**: Well-tested, typed, modern tooling
2. **Scalability**: Distributed game servers with shared state
3. **New Features**: Lobbies, improved AI, replay seeking, email auth
4. **Backwards Compatibility**: Preserve existing users and replays

### Key Architectural Decisions

| Decision | Choice | Rationale | MVP Status |
|----------|--------|-----------|------------|
| Game state storage | In-memory (Redis planned) | Fast access, real-time updates. Redis for distributed scaling. | In-memory implemented |
| Game tick ownership | Async task per game | Clear ownership, explicit handoff | Implemented |
| WebSocket routing | Direct connection (Redis pub/sub planned) | MVP simplicity, pub/sub for multi-server | Direct implemented |
| Frontend state | Zustand | Lightweight, excellent TypeScript support | Implemented |
| Auth | FastAPI-Users | Handles email + OAuth, battle-tested | Implemented |

---

## Tech Stack

### Backend

| Component | Technology | Version | Status |
|-----------|------------|---------|--------|
| Framework | FastAPI | 0.115+ | Implemented |
| ASGI Server | Uvicorn | 0.34+ | Implemented |
| Database ORM | SQLAlchemy | 2.0+ | Configured (models TODO) |
| Migrations | Alembic | 1.14+ | Configured (migrations TODO) |
| Cache/State | Redis | 7+ (client 5.2+) | Placeholder |
| Auth | FastAPI-Users | 14+ | Implemented |
| Task Queue | None (game loops run in-process) | - | - |
| Python | Python | 3.12+ | Implemented |
| Package Manager | uv | latest | Implemented |
| Linting/Formatting | Ruff | 0.8+ | Implemented |
| Testing | pytest + pytest-asyncio | 8.3+/0.25+ | Implemented |

### Frontend

| Component | Technology | Version | Status |
|-----------|------------|---------|--------|
| Framework | React | 19 | Implemented |
| Language | TypeScript | 5.7+ | Implemented |
| Build Tool | Vite | 6 | Implemented |
| State Management | Zustand | 5 | Implemented |
| Canvas Rendering | PixiJS | 8.6+ | Implemented |
| Routing | React Router | 7 | Implemented |
| HTTP Client | fetch (native) | - | Implemented |
| Styling | CSS | - | Implemented |
| Testing | Vitest + React Testing Library | 3/16+ | Implemented |
| Node.js | Node.js | 20+ | Required |

### Infrastructure

| Component | Technology | Status |
|-----------|------------|--------|
| Database | PostgreSQL 15+ | Dev ready (docker-compose) |
| Cache/Pub-Sub | Redis 7+ | Dev ready (docker-compose) |
| Reverse Proxy | Nginx | Production TODO |
| Process Manager | systemd | Production TODO |
| Deployment | Simple VMs | Production TODO |

---

## Directory Structure

> **Note**: This is the target structure. Files marked with ✓ are implemented, others are planned.

```
kfchess-cc/
├── README.md                       ✓
├── CLAUDE.md                       ✓ Claude Code context
├── docker-compose.yml              ✓ Dev environment
│
├── docs/                           ✓ Documentation
│   ├── ARCHITECTURE.md             ✓ This file (blueprint)
│   ├── MVP_IMPLEMENTATION.md       ✓ MVP implementation details
│   ├── FOUR_PLAYER_DESIGN.md       ✓ 4-player mode design
│   └── KFCHESS_ORIGINAL_IMPLEMENTATION.md  ✓ Legacy reference
│
├── scripts/                        ✓ Utility scripts
│   ├── dev.sh                      ✓ Start full dev environment
│   ├── dev-servers.sh              ✓ Start only dev servers
│   └── migrate.sh                  ✓ Run migrations
│
├── server/                         ✓ Python backend
│   ├── pyproject.toml              ✓
│   ├── uv.lock                     ✓
│   ├── .env.example                ✓
│   ├── alembic/                    ✓ Database migrations
│   │   ├── env.py                  ✓
│   │   └── versions/               ✓
│   │       ├── 001_add_game_replays.py  ✓
│   │       └── 002_add_users.py         ✓
│   │
│   ├── src/kfchess/
│   │   ├── __init__.py             ✓
│   │   ├── main.py                 ✓ FastAPI app entry point
│   │   ├── settings.py             ✓ Pydantic settings
│   │   │
│   │   ├── auth/                   ✓ Authentication (COMPLETE)
│   │   │   ├── schemas.py          ✓ UserRead, UserCreate, UserUpdate
│   │   │   ├── users.py            ✓ UserManager + OAuth
│   │   │   ├── backend.py          ✓ Cookie JWT backend
│   │   │   ├── dependencies.py     ✓ current_user, DEV_MODE bypass
│   │   │   ├── router.py           ✓ Route registration
│   │   │   ├── email.py            ✓ Resend integration
│   │   │   └── rate_limit.py       ✓ SlowAPI rate limiting
│   │   │
│   │   ├── api/                    ✓ HTTP API routes
│   │   │   ├── router.py           ✓ Main router
│   │   │   ├── games.py            ✓ Game management endpoints
│   │   │   ├── replays.py          ✓ Replay list endpoint
│   │   │   └── users.py            ✓ User profile endpoints
│   │   │   # TODO: lobbies.py, campaign.py
│   │   │
│   │   ├── ws/                     ✓ WebSocket handlers
│   │   │   ├── handler.py          ✓ Connection handler + game loop
│   │   │   ├── protocol.py         ✓ Message types/schemas
│   │   │   └── replay_handler.py   ✓ Replay WebSocket handler
│   │   │
│   │   ├── game/                   ✓ Game engine (COMPLETE)
│   │   │   ├── engine.py           ✓ Core game logic
│   │   │   ├── board.py            ✓ Board representation
│   │   │   ├── pieces.py           ✓ Piece definitions
│   │   │   ├── moves.py            ✓ Move validation
│   │   │   ├── collision.py        ✓ Collision detection
│   │   │   ├── state.py            ✓ Game state management
│   │   │   └── replay.py           ✓ Replay data structures & engine
│   │   │
│   │   ├── replay/                 ✓ Replay playback
│   │   │   └── session.py          ✓ WebSocket replay session
│   │   │
│   │   ├── ai/                     ✓ AI system
│   │   │   ├── base.py             ✓ AI interface
│   │   │   └── dummy.py            ✓ Random move AI
│   │   │   # TODO: mcts.py, heuristics.py, difficulty.py
│   │   │
│   │   ├── services/               ✓ Business logic
│   │   │   └── game_service.py     ✓ In-memory game management
│   │   │   # TODO: elo.py, s3.py
│   │   │
│   │   ├── db/                     ✓ Database layer
│   │   │   ├── models.py           ✓ SQLAlchemy models (User, OAuthAccount, GameReplay)
│   │   │   ├── session.py          ✓ Database session management
│   │   │   └── repositories/       ✓ Repository pattern
│   │   │       ├── replays.py      ✓ Replay CRUD operations
│   │   │       └── users.py        ✓ User CRUD operations
│   │   ├── redis/                  Placeholder - TODO
│   │   ├── lobby/                  Placeholder - TODO
│   │   └── campaign/               Placeholder - TODO
│   │
│   └── tests/                      ✓ Test suite
│       ├── conftest.py             ✓
│       ├── test_health.py          ✓
│       ├── unit/
│       │   ├── game/               ✓ Game engine tests (comprehensive)
│       │   ├── auth/               ✓ Auth unit tests
│       │   ├── test_game_service.py ✓
│       │   ├── test_api_games.py   ✓
│       │   └── test_websocket.py   ✓
│       └── integration/
│           └── auth/               ✓ Auth integration tests
│
├── client/                         ✓ TypeScript frontend
│   ├── package.json                ✓
│   ├── vite.config.ts              ✓
│   ├── tsconfig.json               ✓
│   ├── index.html                  ✓
│   ├── .env.example                ✓
│   │
│   ├── src/
│   │   ├── main.tsx                ✓ App entry point
│   │   ├── App.tsx                 ✓ Root component + routes
│   │   │
│   │   ├── api/                    ✓ API client
│   │   │   ├── client.ts           ✓ HTTP client
│   │   │   ├── types.ts            ✓ API types
│   │   │   └── index.ts            ✓
│   │   │
│   │   ├── ws/                     ✓ WebSocket client
│   │   │   ├── client.ts           ✓ WebSocket manager
│   │   │   ├── types.ts            ✓ Message types
│   │   │   └── index.ts            ✓
│   │   │
│   │   ├── stores/                 ✓ Zustand stores
│   │   │   ├── game.ts             ✓ Game state (main)
│   │   │   ├── replay.ts           ✓ Replay state
│   │   │   ├── auth.ts             ✓ Auth state (COMPLETE)
│   │   │   └── lobby.ts            ✓ Lobby state (placeholder)
│   │   │
│   │   ├── game/                   ✓ Game rendering
│   │   │   ├── renderer.ts         ✓ PixiJS rendering logic
│   │   │   ├── constants.ts        ✓ Board dimensions, colors
│   │   │   ├── sprites.ts          ✓ Sprite management
│   │   │   ├── interpolation.ts    ✓ Position smoothing
│   │   │   ├── moves.ts            ✓ Client-side validation
│   │   │   └── index.ts            ✓
│   │   │
│   │   ├── components/             ✓ React components
│   │   │   ├── game/
│   │   │   │   ├── GameBoard.tsx   ✓ PixiJS canvas wrapper
│   │   │   │   ├── GameStatus.tsx  ✓
│   │   │   │   └── GameOverModal.tsx ✓
│   │   │   ├── replay/             ✓ Replay components
│   │   │   │   ├── ReplayBoard.tsx ✓
│   │   │   │   └── ReplayControls.tsx ✓
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx      ✓ With user menu + verification banner
│   │   │   │   └── Layout.tsx      ✓
│   │   │   └── AuthProvider.tsx    ✓ Auto-fetch user on load
│   │   │   # TODO: lobby/, campaign/, common/
│   │   │
│   │   ├── pages/                  ✓ Route pages
│   │   │   ├── Home.tsx            ✓ Home/game creation
│   │   │   ├── Game.tsx            ✓ Game play page
│   │   │   ├── Replay.tsx          ✓ Replay viewer
│   │   │   ├── Replays.tsx         ✓ Replay browser
│   │   │   ├── Login.tsx           ✓ Login page
│   │   │   ├── Register.tsx        ✓ Registration page
│   │   │   ├── ForgotPassword.tsx  ✓ Request password reset
│   │   │   ├── ResetPassword.tsx   ✓ Set new password
│   │   │   ├── Verify.tsx          ✓ Email verification
│   │   │   └── GoogleCallback.tsx  ✓ OAuth callback
│   │   │   # TODO: Lobby, Campaign, Profile
│   │   │
│   │   ├── styles/
│   │   │   └── index.css           ✓
│   │   │
│   │   └── assets/                 ✓ Static assets
│   │       └── sprites/            ✓ Chess piece images
│   │
│   └── tests/                      ✓
│       ├── setup.ts                ✓
│       └── components/
│           └── Home.test.tsx       ✓
```

---

## Backend Architecture

### Application Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│  API Layer (api/)           │  WebSocket Layer (ws/)        │
│  - REST endpoints           │  - Connection management      │
│  - Request validation       │  - Message routing            │
│  - Response serialization   │  - Protocol handling          │
├─────────────────────────────────────────────────────────────┤
│                     Service Layer (services/)                │
│  - Game server management                                    │
│  - Business logic                                            │
│  - Cross-cutting concerns                                    │
├─────────────────────────────────────────────────────────────┤
│  Game Engine (game/)        │  AI System (ai/)              │
│  - Board state              │  - MCTS                       │
│  - Move validation          │  - Heuristics                 │
│  - Collision detection      │  - Difficulty scaling         │
├─────────────────────────────────────────────────────────────┤
│  Data Layer                                                  │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   PostgreSQL    │  │      Redis      │                   │
│  │   (persistent)  │  │   (real-time)   │                   │
│  │  - Users        │  │  - Game state   │                   │
│  │  - Replays      │  │  - Lobbies      │                   │
│  │  - Campaigns    │  │  - Pub/sub      │                   │
│  │  - History      │  │  - Sessions     │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow

**HTTP Request:**
```
Client → Nginx → Uvicorn → FastAPI Router → Handler → Service → DB/Redis → Response
```

**WebSocket Connection:**
```
Client → Nginx (upgrade) → Uvicorn → WebSocket Handler → Connection Manager
                                                              ↓
                                                        Redis Pub/Sub
                                                              ↓
                                                        Game Server
```

### Game Server Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    Game Server Process                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Startup                                                  │
│     - Register with Redis (server ID, capacity)             │
│     - Subscribe to game assignment channel                  │
│     - Start health check heartbeat                          │
│                                                              │
│  2. Game Assignment                                          │
│     - Receive game ID from coordinator                      │
│     - Load game state from Redis                            │
│     - Start tick loop for game                              │
│                                                              │
│  3. Tick Loop (per game)                                    │
│     - Process AI moves                                      │
│     - Advance game state                                    │
│     - Detect collisions/captures                            │
│     - Publish updates via Redis pub/sub                     │
│     - Persist state to Redis periodically                   │
│                                                              │
│  4. Graceful Shutdown                                        │
│     - Stop accepting new games                              │
│     - For each active game:                                 │
│       - Persist final state to Redis                        │
│       - Publish handoff message                             │
│     - Deregister from Redis                                 │
│                                                              │
│  5. Crash Recovery (by other servers)                       │
│     - Detect missing heartbeat                              │
│     - Claim orphaned games                                  │
│     - Resume from last persisted state                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Frontend Architecture

### Component Hierarchy

```
App
├── AuthProvider (context)
├── Router
│   ├── Layout
│   │   ├── Header
│   │   │   ├── Logo
│   │   │   ├── Navigation
│   │   │   └── UserMenu
│   │   └── Main (outlet)
│   │
│   ├── Home
│   │   ├── QuickPlay
│   │   ├── LobbyPreview
│   │   └── CampaignProgress
│   │
│   ├── Game
│   │   ├── GameBoard (PIXI canvas)
│   │   ├── GameControls
│   │   ├── PlayerInfo (x2-4)
│   │   └── GameOverModal
│   │
│   ├── Lobby
│   │   ├── LobbyList
│   │   │   └── LobbyCard (xN)
│   │   ├── LobbyDetail
│   │   └── CreateLobbyModal
│   │
│   ├── Campaign
│   │   ├── BeltSelector
│   │   ├── LevelGrid
│   │   └── LevelDetail
│   │
│   ├── Replays
│   │   ├── ReplayBrowser
│   │   │   ├── Filters
│   │   │   └── ReplayCard (xN)
│   │   └── ReplayViewer
│   │       ├── GameBoard
│   │       └── ReplayControls
│   │
│   ├── Profile
│   │   ├── ProfileHeader
│   │   ├── StatsDisplay
│   │   └── GameHistory
│   │
│   ├── Login
│   └── Register
│
└── Modals (portal)
    ├── Alert
    └── Confirm
```

### State Management

```typescript
// stores/auth.ts
interface AuthState {
  user: User | null;
  isLoading: boolean;
  login: (credentials: Credentials) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
}

// stores/game.ts
interface GameState {
  gameId: string | null;
  playerNumber: number;  // 0 = spectator, 1-4 = player
  board: Board;
  pieces: Piece[];
  moves: ActiveMove[];
  cooldowns: Cooldown[];
  status: 'waiting' | 'ready' | 'playing' | 'finished';
  winner: number | null;

  // Actions
  connect: (gameId: string, playerKey?: string) => void;
  disconnect: () => void;
  ready: () => void;
  move: (pieceId: string, toRow: number, toCol: number) => void;
}

// stores/lobby.ts
interface LobbyState {
  lobbies: Lobby[];
  currentLobby: Lobby | null;
  isLoading: boolean;

  // Actions
  fetchLobbies: () => Promise<void>;
  createLobby: (options: LobbyOptions) => Promise<Lobby>;
  joinLobby: (lobbyId: string) => Promise<void>;
  leaveLobby: () => Promise<void>;
  setReady: (ready: boolean) => void;
}
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        React App                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Components ←──── Zustand Stores ←──── API/WebSocket       │
│       │                  │                    │              │
│       │                  │                    │              │
│       ▼                  ▼                    ▼              │
│   [Render]          [State]              [Server]           │
│                                                              │
│   User Action → Store Action → API Call → Server            │
│                                              │               │
│                                              ▼               │
│   Components ← Store Update ← WebSocket ← Server Push       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Game Engine

### Core Data Structures

```python
# game/pieces.py
from enum import Enum
from dataclasses import dataclass

class PieceType(Enum):
    PAWN = "P"
    KNIGHT = "N"
    BISHOP = "B"
    ROOK = "R"
    QUEEN = "Q"
    KING = "K"

@dataclass
class Piece:
    id: str                    # e.g., "P:1:6:0" (type:player:start_row:start_col)
    type: PieceType
    player: int                # 1-4
    row: float                 # Current position (float for interpolation)
    col: float
    captured: bool = False
    moved: bool = False        # For castling eligibility

# game/board.py
@dataclass
class Board:
    pieces: list[Piece]
    width: int = 8             # Standard: 8, 4-player: 12
    height: int = 8            # Standard: 8, 4-player: 12

    def get_piece_by_id(self, piece_id: str) -> Piece | None: ...
    def get_piece_at(self, row: int, col: int) -> Piece | None: ...
    def get_pieces_for_player(self, player: int) -> list[Piece]: ...

# game/moves.py
@dataclass
class Move:
    piece_id: str
    path: list[tuple[int, int]]  # Sequence of (row, col)
    start_tick: int
    extra_move: "Move | None" = None  # For castling (rook move)

@dataclass
class Cooldown:
    piece_id: str
    start_tick: int
    duration: int

# game/state.py
@dataclass
class GameState:
    game_id: str
    board: Board
    speed: Speed
    players: dict[int, str]     # player_number -> player_id ("u:123" or "bot:novice")
    active_moves: list[Move]
    cooldowns: list[Cooldown]
    current_tick: int
    started_at: datetime | None
    finished_at: datetime | None
    winner: int | None          # None = ongoing, 0 = draw, 1-4 = winner
    replay_moves: list[ReplayMove]  # For recording
```

### Game Engine Interface

```python
# game/engine.py
class GameEngine:
    """Core game logic. Mutates state in place for performance.
    Use GameState.copy() if you need to preserve state (e.g., AI lookahead).
    """

    @staticmethod
    def create_game(
        speed: Speed,
        players: dict[int, str],
        board_type: BoardType = BoardType.STANDARD,
    ) -> GameState:
        """Create a new game with initial board state"""
        ...

    @staticmethod
    def validate_move(
        state: GameState,
        player: int,
        piece_id: str,
        to_row: int,
        to_col: int,
    ) -> Move | None:
        """Validate and compute move path. Returns None if invalid."""
        ...

    @staticmethod
    def apply_move(state: GameState, move: Move) -> tuple[GameState, list[GameEvent]]:
        """Apply a move to the game state (mutates in place)"""
        ...

    @staticmethod
    def tick(state: GameState) -> tuple[GameState, list[GameEvent]]:
        """
        Advance game by one tick (mutates state in place).
        Returns state and list of events (captures, promotions, etc.)
        """
        ...

    @staticmethod
    def check_winner(state: GameState) -> int | None:
        """Check if game is over. Returns winner (0=draw, 1-4=player) or None."""
        ...
```

### Speed Configuration

```python
# game/engine.py
from enum import Enum

class Speed(Enum):
    STANDARD = "standard"
    LIGHTNING = "lightning"

SPEED_CONFIG = {
    Speed.STANDARD: {
        "tick_period_ms": 100,      # 10 ticks per second
        "move_ticks": 10,           # 1 second per square
        "cooldown_ticks": 100,      # 10 second cooldown
        "draw_no_move_ticks": 1200, # 2 min
        "draw_no_capture_ticks": 1800,  # 3 min
    },
    Speed.LIGHTNING: {
        "tick_period_ms": 100,
        "move_ticks": 2,            # 0.2 seconds per square
        "cooldown_ticks": 20,       # 2 second cooldown
        "draw_no_move_ticks": 300,  # 30 sec
        "draw_no_capture_ticks": 450,   # 45 sec
    },
}
```

---

## Real-Time Communication

### WebSocket Protocol

**Message Format:**
```typescript
interface WSMessage {
  type: string;
  payload: any;
  timestamp: number;
}
```

**Client → Server Messages:**

| Type | Payload | Description |
|------|---------|-------------|
| `join` | `{gameId, playerKey?}` | Join a game (spectator if no key) |
| `ready` | `{}` | Signal ready to start |
| `move` | `{pieceId, toRow, toCol}` | Request a move |
| `leave` | `{}` | Leave the game |
| `ping` | `{}` | Keep-alive |

**Server → Client Messages:**

| Type | Payload | Description |
|------|---------|-------------|
| `joined` | `{gameState, playerNumber}` | Confirm join with full state |
| `player_joined` | `{player, playerNumber}` | Another player joined |
| `player_left` | `{playerNumber}` | Player left |
| `player_ready` | `{playerNumber}` | Player is ready |
| `game_start` | `{startTick}` | Game is starting |
| `update` | `{tick, moves, cooldowns, captures, ...}` | Game state delta |
| `game_over` | `{winner, ratings?}` | Game ended |
| `error` | `{code, message}` | Error occurred |
| `pong` | `{}` | Keep-alive response |

### Connection Management

```python
# ws/manager.py
class ConnectionManager:
    """Manages WebSocket connections per server instance"""

    def __init__(self, redis: Redis):
        self.connections: dict[str, WebSocket] = {}  # conn_id -> websocket
        self.game_connections: dict[str, set[str]] = {}  # game_id -> conn_ids
        self.redis = redis

    async def connect(self, websocket: WebSocket, conn_id: str):
        """Accept connection and register"""
        await websocket.accept()
        self.connections[conn_id] = websocket

    async def join_game(self, conn_id: str, game_id: str):
        """Associate connection with a game"""
        if game_id not in self.game_connections:
            self.game_connections[game_id] = set()
            # Subscribe to Redis channel for this game
            await self.redis.subscribe(f"game:{game_id}")
        self.game_connections[game_id].add(conn_id)

    async def broadcast_to_game(self, game_id: str, message: dict):
        """Send message to all connections in a game"""
        # Publish to Redis so all servers receive it
        await self.redis.publish(f"game:{game_id}", json.dumps(message))

    async def handle_redis_message(self, channel: str, message: str):
        """Handle message from Redis pub/sub"""
        game_id = channel.split(":")[1]
        if game_id in self.game_connections:
            for conn_id in self.game_connections[game_id]:
                ws = self.connections.get(conn_id)
                if ws:
                    await ws.send_text(message)
```

### Distributed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                              │
│   ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐     │
│   │ C1  │  │ C2  │  │ C3  │  │ C4  │  │ C5  │  │ C6  │     │
│   └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘     │
└──────┼────────┼────────┼────────┼────────┼────────┼─────────┘
       │        │        │        │        │        │
       ▼        ▼        ▼        ▼        ▼        ▼
┌─────────────────────────────────────────────────────────────┐
│                        Nginx (LB)                            │
└──────┬──────────────────┬───────────────────────┬───────────┘
       │                  │                       │
       ▼                  ▼                       ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Server 1   │    │  Server 2   │    │  Server 3   │
│  ┌───────┐  │    │  ┌───────┐  │    │  ┌───────┐  │
│  │Game A │  │    │  │Game C │  │    │  │Game E │  │
│  │Game B │  │    │  │Game D │  │    │  │Game F │  │
│  └───────┘  │    │  └───────┘  │    │  └───────┘  │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │
       └────────────┬─────┴──────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                          Redis                               │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   Game States   │  │    Pub/Sub      │                   │
│  │   game:ABC      │  │  channel:ABC    │                   │
│  │   game:DEF      │  │  channel:DEF    │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

**Flow for a move:**
1. Client C1 sends `move` to Server 1 via WebSocket
2. Server 1 validates move, updates game state in Redis
3. Server 1 publishes update to `channel:gameA`
4. All servers subscribed to `channel:gameA` receive update
5. Each server forwards to connected clients for that game

---

## Database Schema

### Updated Schema

```sql
-- Users table (updated for email auth)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,          -- Can be NULL for legacy Google-only users
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255),          -- NULL for Google-only users
    picture_url TEXT,
    google_id VARCHAR(255) UNIQUE,       -- For Google OAuth
    ratings JSONB DEFAULT '{}',          -- {"standard": 1200, "lightning": 1200}
    created_at TIMESTAMP DEFAULT NOW(),
    last_online TIMESTAMP DEFAULT NOW(),
    is_verified BOOLEAN DEFAULT FALSE,   -- Email verification
    is_active BOOLEAN DEFAULT TRUE
);

-- Lobbies (new)
CREATE TABLE lobbies (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,    -- Short join code
    name VARCHAR(100) NOT NULL,
    host_id INTEGER REFERENCES users(id),
    speed VARCHAR(20) NOT NULL,
    player_count INTEGER DEFAULT 2,      -- 2 or 4
    is_public BOOLEAN DEFAULT TRUE,
    is_ranked BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,                -- NULL until game starts
    game_id VARCHAR(20),                 -- Set when game starts
    status VARCHAR(20) DEFAULT 'waiting' -- waiting, starting, in_game, finished
);

-- Lobby players (new)
CREATE TABLE lobby_players (
    id SERIAL PRIMARY KEY,
    lobby_id INTEGER REFERENCES lobbies(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    player_slot INTEGER NOT NULL,        -- 1-4
    is_ready BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(lobby_id, player_slot)
);

-- Game history (replays)
CREATE TABLE game_history (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(20) UNIQUE NOT NULL,
    speed VARCHAR(20) NOT NULL,
    player_count INTEGER DEFAULT 2,
    players JSONB NOT NULL,              -- {1: {userId, username}, 2: {...}}
    winner INTEGER,                      -- 0 = draw, 1-4 = winner
    duration_ticks INTEGER,
    replay_data JSONB NOT NULL,          -- {moves: [...], initialBoard: {...}}
    created_at TIMESTAMP DEFAULT NOW(),
    is_public BOOLEAN DEFAULT TRUE,      -- For replay browser
    upvotes INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0
);

-- User game history (junction table)
CREATE TABLE user_game_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    game_history_id INTEGER REFERENCES game_history(id) ON DELETE CASCADE,
    player_slot INTEGER NOT NULL,
    rating_before INTEGER,
    rating_after INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, game_history_id)
);

-- Campaign progress
CREATE TABLE campaign_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    levels_completed JSONB DEFAULT '{}', -- {"0": true, "1": true, ...}
    belts_completed JSONB DEFAULT '{}',  -- {"1": true, ...}
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Replay upvotes (new)
CREATE TABLE replay_upvotes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    game_history_id INTEGER REFERENCES game_history(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, game_history_id)
);

-- Password reset tokens (new)
CREATE TABLE password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP
);

-- Email verification tokens (new)
CREATE TABLE email_verification_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    verified_at TIMESTAMP
);

-- Indexes
CREATE INDEX idx_users_google_id ON users(google_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_lobbies_status ON lobbies(status);
CREATE INDEX idx_lobbies_is_public ON lobbies(is_public) WHERE is_public = TRUE;
CREATE INDEX idx_game_history_created ON game_history(created_at DESC);
CREATE INDEX idx_game_history_public ON game_history(is_public, upvotes DESC) WHERE is_public = TRUE;
CREATE INDEX idx_user_game_history_user ON user_game_history(user_id, created_at DESC);
CREATE INDEX idx_campaign_progress_user ON campaign_progress(user_id);
```

### Redis Data Structures

```
# Game state (Hash)
game:{game_id}:state -> {
    "board": <serialized board>,
    "players": <json>,
    "active_moves": <json>,
    "cooldowns": <json>,
    "current_tick": <int>,
    "status": "waiting|playing|finished",
    "winner": <int|null>,
    "server_id": <string>        # Which server owns this game
}

# Game lock (String with TTL)
game:{game_id}:lock -> <server_id>
# TTL: 5 seconds, refreshed by owning server

# Server registry (Hash)
servers:{server_id} -> {
    "host": <string>,
    "port": <int>,
    "game_count": <int>,
    "last_heartbeat": <timestamp>
}
# TTL: 30 seconds, refreshed every 10 seconds

# Lobby state (Hash)
lobby:{lobby_id}:state -> {
    "players": <json>,
    "ready": <json>,
    "chat": <json>
}

# Online users (Sorted Set)
online_users -> {user_id: last_seen_timestamp, ...}

# Pub/Sub channels
game:{game_id}         # Game updates
lobby:{lobby_id}       # Lobby updates
user:{user_id}         # Direct messages (invites, etc.)
```

---

## AI System

### Architecture

```python
# ai/base.py
from abc import ABC, abstractmethod

class AIPlayer(ABC):
    """Base class for AI implementations"""

    @abstractmethod
    def choose_move(
        self,
        state: GameState,
        player: int,
    ) -> tuple[str, int, int] | None:
        """
        Choose a move for the given player.
        Returns (piece_id, to_row, to_col) or None if no move.
        """
        ...

# ai/difficulty.py
@dataclass
class DifficultyConfig:
    name: str
    think_ticks: int          # Ticks between moves
    search_depth: int         # MCTS iterations or lookahead depth
    randomness: float         # 0-1, higher = more random moves
    mistake_rate: float       # 0-1, chance to make suboptimal move

DIFFICULTIES = {
    "novice": DifficultyConfig("Novice", 40, 100, 0.3, 0.2),
    "intermediate": DifficultyConfig("Intermediate", 25, 500, 0.15, 0.1),
    "advanced": DifficultyConfig("Advanced", 15, 2000, 0.05, 0.02),
    "expert": DifficultyConfig("Expert", 10, 5000, 0.01, 0.0),
    "campaign": DifficultyConfig("Campaign", 12, 1000, 0.1, 0.05),
}
```

### MCTS Implementation

```python
# ai/mcts.py
from dataclasses import dataclass
import random
import math

@dataclass
class MCTSNode:
    state: GameState
    move: tuple[str, int, int] | None  # Move that led here
    parent: "MCTSNode | None"
    children: list["MCTSNode"]
    visits: int = 0
    wins: float = 0.0

    @property
    def ucb1(self) -> float:
        if self.visits == 0:
            return float('inf')
        exploitation = self.wins / self.visits
        exploration = math.sqrt(2 * math.log(self.parent.visits) / self.visits)
        return exploitation + exploration

class MCTSPlayer(AIPlayer):
    """Monte Carlo Tree Search AI"""

    def __init__(self, config: DifficultyConfig):
        self.config = config
        self.evaluator = PositionEvaluator()

    def choose_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        root = MCTSNode(state=state, move=None, parent=None, children=[])

        # Run MCTS iterations
        for _ in range(self.config.search_depth):
            node = self._select(root)
            if not self._is_terminal(node.state):
                node = self._expand(node, player)
            result = self._simulate(node.state, player)
            self._backpropagate(node, result)

        # Choose best move
        if not root.children:
            return None

        # Add randomness based on difficulty
        if random.random() < self.config.randomness:
            return random.choice(root.children).move

        best = max(root.children, key=lambda n: n.visits)
        return best.move

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select most promising node using UCB1"""
        while node.children:
            node = max(node.children, key=lambda n: n.ucb1)
        return node

    def _expand(self, node: MCTSNode, player: int) -> MCTSNode:
        """Expand node with possible moves"""
        moves = self._get_legal_moves(node.state, player)
        for move in moves:
            new_state = self._apply_move(node.state, move)
            child = MCTSNode(
                state=new_state,
                move=move,
                parent=node,
                children=[],
            )
            node.children.append(child)
        return random.choice(node.children) if node.children else node

    def _simulate(self, state: GameState, player: int) -> float:
        """Simulate game to estimate value"""
        # Use heuristic evaluation instead of full playout
        # (more appropriate for real-time game)
        return self.evaluator.evaluate(state, player)

    def _backpropagate(self, node: MCTSNode, result: float):
        """Update node statistics up the tree"""
        while node:
            node.visits += 1
            node.wins += result
            node = node.parent
```

### Position Evaluation

```python
# ai/heuristics.py
class PositionEvaluator:
    """Evaluate board position for a player"""

    # Piece values
    PIECE_VALUES = {
        PieceType.PAWN: 100,
        PieceType.KNIGHT: 320,
        PieceType.BISHOP: 330,
        PieceType.ROOK: 500,
        PieceType.QUEEN: 900,
        PieceType.KING: 20000,
    }

    def evaluate(self, state: GameState, player: int) -> float:
        """
        Evaluate position from player's perspective.
        Returns value in [0, 1] range.
        """
        score = 0.0

        # Material
        score += self._material_score(state, player)

        # Piece activity (mobility)
        score += self._mobility_score(state, player) * 0.1

        # King safety
        score += self._king_safety_score(state, player) * 0.3

        # Pressure (pieces threatening opponent)
        score += self._pressure_score(state, player) * 0.2

        # Cooldown penalty (pieces on cooldown are less valuable)
        score -= self._cooldown_penalty(state, player) * 0.1

        # Active moves (pieces currently moving are committed)
        score -= self._active_move_risk(state, player) * 0.1

        # Normalize to [0, 1]
        return 1 / (1 + math.exp(-score / 1000))

    def _material_score(self, state: GameState, player: int) -> float:
        """Sum of piece values for player minus opponents"""
        my_material = sum(
            self.PIECE_VALUES[p.type]
            for p in state.board.pieces
            if p.player == player and not p.captured
        )
        opponent_material = sum(
            self.PIECE_VALUES[p.type]
            for p in state.board.pieces
            if p.player != player and not p.captured
        )
        return my_material - opponent_material

    # ... other evaluation methods
```

---

## Authentication

> **Status: Implemented** - See [AUTHENTICATION_DESIGN.md](./AUTHENTICATION_DESIGN.md) for full details.

### Overview

Authentication uses FastAPI-Users with cookie-based JWT tokens, supporting both email/password and Google OAuth.

| Feature | Implementation |
|---------|----------------|
| Session | 30-day JWT in httponly cookie |
| Password Auth | Email + password with Argon2 hashing |
| Google OAuth | Full flow with legacy user migration |
| Email Verification | Via Resend (optional for login) |
| Password Reset | Token-based, 1-hour expiry |
| Rate Limiting | SlowAPI per-endpoint limits |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Register with email/password |
| `/api/auth/login` | POST | Login (form-encoded) |
| `/api/auth/logout` | POST | Clear auth cookie |
| `/api/auth/forgot-password` | POST | Request reset email |
| `/api/auth/reset-password` | POST | Reset with token |
| `/api/auth/verify` | POST | Verify email with token |
| `/api/auth/request-verify-token` | POST | Request verification email |
| `/api/users/me` | GET | Get current user |
| `/api/users/me` | PATCH | Update profile |
| `/api/auth/google/authorize` | GET | Start Google OAuth |
| `/api/auth/google/callback` | GET | Google OAuth callback |

### Backend Structure

```
server/src/kfchess/auth/
├── schemas.py        # UserRead, UserCreate, UserUpdate
├── users.py          # UserManager with OAuth + random usernames
├── backend.py        # Cookie JWT configuration
├── dependencies.py   # current_user + DEV_MODE bypass
├── router.py         # Route registration with rate limiting
├── email.py          # Resend integration
└── rate_limit.py     # SlowAPI configuration
```

### Frontend Pages

- `/login` - Email/password + Google OAuth button
- `/register` - Registration with optional username
- `/forgot-password` - Request password reset
- `/reset-password` - Set new password (from email link)
- `/verify` - Email verification handler
- `/auth/google/callback` - OAuth callback

### DEV_MODE Bypass

For development, set `DEV_MODE=true` and `DEV_USER_ID=1` to auto-login without authentication.

```python
# When DEV_MODE=true and no auth cookie present:
# GET /api/users/me returns the DEV_USER_ID user automatically
```

---

## Deployment Architecture

### Production Setup

```
┌─────────────────────────────────────────────────────────────┐
│                        Internet                              │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Nginx (Load Balancer)                      │
│  - SSL termination                                           │
│  - Static file serving                                       │
│  - WebSocket upgrade handling                                │
│  - Health check routing                                      │
└────────────┬──────────────────────────────────┬─────────────┘
             │                                  │
             ▼                                  ▼
┌────────────────────────┐        ┌────────────────────────┐
│      App Server 1      │        │      App Server 2      │
│  ┌──────────────────┐  │        │  ┌──────────────────┐  │
│  │     Uvicorn      │  │        │  │     Uvicorn      │  │
│  │   (FastAPI app)  │  │        │  │   (FastAPI app)  │  │
│  │                  │  │        │  │                  │  │
│  │  - HTTP API      │  │        │  │  - HTTP API      │  │
│  │  - WebSocket     │  │        │  │  - WebSocket     │  │
│  │  - Game loops    │  │        │  │  - Game loops    │  │
│  └──────────────────┘  │        │  └──────────────────┘  │
│                        │        │                        │
│  systemd managed       │        │  systemd managed       │
└───────────┬────────────┘        └───────────┬────────────┘
            │                                 │
            └────────────┬────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  PostgreSQL  │  │    Redis     │  │      S3      │
│   (primary)  │  │   (primary)  │  │   (images)   │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Nginx Configuration

```nginx
# /etc/nginx/sites-available/kfchess
upstream kfchess_backend {
    least_conn;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}

server {
    listen 443 ssl http2;
    server_name kfchess.com www.kfchess.com;

    ssl_certificate /etc/letsencrypt/live/kfchess.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kfchess.com/privkey.pem;

    # Static files
    location /assets/ {
        alias /var/www/kfchess/client/dist/assets/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API
    location /api/ {
        proxy_pass http://kfchess_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://kfchess_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # SPA fallback
    location / {
        root /var/www/kfchess/client/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

### Systemd Service

```ini
# /etc/systemd/system/kfchess@.service
[Unit]
Description=KFChess Server Instance %i
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=kfchess
Group=kfchess
WorkingDirectory=/var/www/kfchess/server
Environment="PORT=800%i"
ExecStart=/var/www/kfchess/server/.venv/bin/uvicorn \
    kfchess.main:app \
    --host 127.0.0.1 \
    --port 800%i \
    --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Rolling Deployment

```bash
#!/bin/bash
# deploy.sh

set -e

# 1. Build new version
cd /var/www/kfchess
git pull origin main

# Build frontend
cd client
npm ci
npm run build

# Build backend
cd ../server
uv sync

# Run migrations
uv run alembic upgrade head

# 2. Rolling restart
for i in 1 2; do
    echo "Restarting instance $i..."

    # Signal graceful shutdown (games will handoff)
    systemctl kill --signal=SIGTERM kfchess@$i

    # Wait for handoff (games persist to Redis)
    sleep 10

    # Restart with new code
    systemctl restart kfchess@$i

    # Wait for health check
    sleep 5
    until curl -s http://127.0.0.1:800$i/health | grep -q "ok"; do
        sleep 1
    done

    echo "Instance $i is healthy"
done

echo "Deployment complete"
```

---

## Testing Strategy

### Test Pyramid

```
        ┌─────────────┐
        │    E2E      │  Few, slow, high confidence
        │  (Playwright)│
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ Integration │  Some, medium speed
        │  (pytest)   │  API + DB + Redis
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │    Unit     │  Many, fast
        │  (pytest +  │  Game logic, AI, utils
        │   vitest)   │
        └─────────────┘
```

### Backend Testing

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def db_session():
    """Create test database session"""
    engine = create_async_engine("postgresql+asyncpg://test:test@localhost/kfchess_test")
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
async def client(db_session):
    """Create test HTTP client"""
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def redis_mock():
    """Mock Redis for unit tests"""
    return fakeredis.FakeRedis()

# tests/unit/game/test_engine.py
class TestGameEngine:
    def test_pawn_move_forward(self):
        state = GameEngine.create_game(Speed.STANDARD, {1: "u:1", 2: "u:2"})
        move = GameEngine.validate_move(state, 1, "P:1:6:4", 5, 4)
        assert move is not None
        assert move.path == [(6, 4), (5, 4)]

    def test_pawn_cannot_move_backward(self):
        state = GameEngine.create_game(Speed.STANDARD, {1: "u:1", 2: "u:2"})
        move = GameEngine.validate_move(state, 1, "P:1:6:4", 7, 4)
        assert move is None

    def test_collision_detection(self):
        # ... test piece captures

# tests/integration/api/test_games.py
class TestGameAPI:
    async def test_create_game(self, client, auth_headers):
        response = await client.post(
            "/api/games",
            json={"speed": "standard"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "gameId" in data
        assert "playerKey" in data
```

### Frontend Testing

```typescript
// tests/game/renderer.test.ts
import { describe, it, expect } from 'vitest';
import { calculatePiecePosition } from '../../src/game/renderer';

describe('renderer', () => {
  it('calculates piece position during move', () => {
    const piece = { row: 6, col: 4 };
    const move = { path: [[6, 4], [5, 4], [4, 4]], startTick: 0 };

    // Halfway through move
    const pos = calculatePiecePosition(piece, move, 5, { moveTicks: 10 });
    expect(pos.row).toBe(5.5);
    expect(pos.col).toBe(4);
  });
});

// tests/components/GameBoard.test.tsx
import { render, screen } from '@testing-library/react';
import { GameBoard } from '../../src/components/game/GameBoard';

describe('GameBoard', () => {
  it('renders canvas element', () => {
    render(<GameBoard gameState={mockGameState} />);
    expect(screen.getByTestId('game-canvas')).toBeInTheDocument();
  });
});
```

---

## Development Workflow

### Local Setup

```bash
# 1. Clone and enter directory
git clone <repo> kfchess-cc
cd kfchess-cc

# 2. Start infrastructure
docker-compose up -d postgres redis

# 3. Backend setup
cd server
uv sync
uv run alembic upgrade head
uv run python -m kfchess.scripts.seed  # Optional: seed data

# 4. Frontend setup
cd ../client
npm install

# 5. Start development servers (in separate terminals)
# Terminal 1: Backend
cd server && uv run uvicorn kfchess.main:app --reload --port 8000

# Terminal 2: Frontend
cd client && npm run dev

# Or use the convenience script:
./scripts/dev.sh
```

### Docker Compose (Dev)

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: kfchess
      POSTGRES_PASSWORD: kfchess
      POSTGRES_DB: kfchess
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # Optional: run full stack in Docker
  backend:
    build:
      context: ./server
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      - ./server/src:/app/src
    environment:
      DATABASE_URL: postgresql+asyncpg://kfchess:kfchess@postgres/kfchess
      REDIS_URL: redis://redis:6379
      DEV_MODE: "true"
      DEV_USER_ID: "1"
    depends_on:
      - postgres
      - redis

  frontend:
    build:
      context: ./client
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    volumes:
      - ./client/src:/app/src

volumes:
  postgres_data:
  redis_data:
```

### Environment Variables

```bash
# server/.env.example
DATABASE_URL=postgresql+asyncpg://kfchess:kfchess@localhost/kfchess
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key-here

# Auth
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx

# Dev mode
DEV_MODE=true
DEV_USER_ID=1

# AWS (for profile pics)
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_BUCKET=kfchess-uploads
AWS_REGION=us-west-2

# client/.env.example
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

---

## Migration Strategy

### Database Migration

```python
# alembic/versions/001_initial_from_legacy.py
"""
Migrate from legacy schema to new schema.
Preserves all existing data.
"""

def upgrade():
    # 1. Add new columns to users
    op.add_column('users', sa.Column('password_hash', sa.String(255)))
    op.add_column('users', sa.Column('google_id', sa.String(255)))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), default=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), default=True))

    # 2. Populate google_id from email (legacy users are all Google)
    op.execute("""
        UPDATE users
        SET google_id = email,
            is_verified = true,
            is_active = true
        WHERE google_id IS NULL
    """)

    # 3. Create new tables
    op.create_table('lobbies', ...)
    op.create_table('lobby_players', ...)
    op.create_table('replay_upvotes', ...)
    op.create_table('password_reset_tokens', ...)
    op.create_table('email_verification_tokens', ...)

    # 4. Add indexes
    op.create_index('idx_users_google_id', 'users', ['google_id'])
    ...

    # 5. Migrate game_history replay format if needed
    # (only if replay format changes)

def downgrade():
    # Reverse operations
    ...
```

### Replay Format Migration

If replay format changes, migrate lazily:

```python
# game/replay.py
def load_replay(replay_data: dict) -> Replay:
    version = replay_data.get("version", 1)

    if version == 1:
        # Legacy format
        return migrate_v1_to_v2(replay_data)
    elif version == 2:
        return Replay(**replay_data)
    else:
        raise ValueError(f"Unknown replay version: {version}")

def migrate_v1_to_v2(data: dict) -> Replay:
    """Convert legacy replay format to new format"""
    # ... conversion logic
```

---

## 4-Player Mode

> **Status**: Game engine support is implemented. Frontend rendering needs additional work for 4-player perspectives.

### Board Layout

```
         0 1 2 3 4 5 6 7 8 9 10 11
       ┌─────────────────────────┐
    0  │     │ R N B Q K B N R │     │  Player 4 (top)
    1  │     │ P P P P P P P P │     │
       ├─────┼─────────────────┼─────┤
    2  │ R P │                 │ P R │
    3  │ N P │                 │ P N │
    4  │ B P │                 │ P B │  Player 3     Player 1
    5  │ Q P │     8x8 core    │ P K │  (left)       (right)
    6  │ K P │                 │ P Q │
    7  │ B P │                 │ P B │
    8  │ N P │                 │ P N │
    9  │ R P │                 │ P R │
       ├─────┼─────────────────┼─────┤
   10  │     │ P P P P P P P P │     │
   11  │     │ R N B Q K B N R │     │  Player 2 (bottom)
       └─────────────────────────────┘
```

### Data Model Changes

```python
class BoardType(Enum):
    STANDARD = "standard"      # 8x8
    FOUR_PLAYER = "four_player"  # 12x12 with corners cut

@dataclass
class Board:
    pieces: list[Piece]
    board_type: BoardType

    @property
    def valid_squares(self) -> set[tuple[int, int]]:
        if self.board_type == BoardType.STANDARD:
            return {(r, c) for r in range(8) for c in range(8)}
        else:
            # 12x12 minus corners
            squares = {(r, c) for r in range(12) for c in range(12)}
            corners = {
                (r, c) for r in range(2) for c in range(2)
            } | {
                (r, c) for r in range(2) for c in range(10, 12)
            } | {
                (r, c) for r in range(10, 12) for c in range(2)
            } | {
                (r, c) for r in range(10, 12) for c in range(10, 12)
            }
            return squares - corners
```

### Win Conditions

```python
def check_winner_4player(state: GameState) -> int | None:
    """
    4-player win condition: last king standing
    Returns: None (ongoing), 0 (draw), or player number (1-4)
    """
    alive_kings = [
        p.player for p in state.board.pieces
        if p.type == PieceType.KING and not p.captured
    ]

    if len(alive_kings) == 1:
        return alive_kings[0]
    elif len(alive_kings) == 0:
        return 0  # Draw (simultaneous capture)
    else:
        return None  # Game continues
```

---

## Summary

This architecture provides:

1. **Maintainability**: TypeScript frontend, typed Python backend, comprehensive tests
2. **Scalability**: Redis-backed distributed game servers with handoff (planned)
3. **New Features**: Lobbies, improved AI (MCTS), replay seeking
4. **Backwards Compatibility**: Migration path for existing data

The system is designed for 2-player now with clear extension points for 4-player mode later.

---

## Implementation Status

### Completed (MVP+)
- [x] Project structure and tooling (uv, Vite, TypeScript)
- [x] Core game engine with comprehensive tests
  - Board, pieces, moves, collision detection
  - 2-player and 4-player board support
  - Tick-based movement system
  - Castling, pawn promotion
- [x] REST API layer (game creation, moves, ready, legal-moves)
- [x] WebSocket real-time communication
- [x] Frontend React/TypeScript/PixiJS rendering
- [x] Zustand state management
- [x] Basic AI (DummyAI - random moves)
- [x] Development scripts (dev.sh, migrate.sh)
- [x] Docker Compose for dev databases
- [x] Replay system (recording, storage, playback)
  - Database model and repository
  - Auto-save on game completion
  - WebSocket-based playback with play/pause/seek
  - O(n) incremental playback optimization
  - Replay browser UI
  - See [REPLAY_DESIGN.md](./REPLAY_DESIGN.md) for details
- [x] User authentication
  - Email/password registration and login
  - Google OAuth with legacy user migration
  - Email verification and password reset
  - Rate limiting on auth endpoints
  - DEV_MODE bypass for development
  - See [AUTHENTICATION_DESIGN.md](./AUTHENTICATION_DESIGN.md) for details

### In Progress / Next Steps
1. Lobby system for matchmaking
2. Advanced AI (MCTS implementation)
3. ELO rating system

### Future
- Campaign mode with AI opponents
- 4-player game support (engine ready, UI needs work)
- Redis for distributed scaling
- Multi-server replay support (keyframe caching)
- Production deployment (Nginx, systemd)

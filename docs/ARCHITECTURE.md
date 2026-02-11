# Kung Fu Chess - Architecture

This document describes the system architecture for Kung Fu Chess.

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Game state storage | In-memory + Redis snapshots | Fast access with crash recovery via periodic snapshots |
| Game tick ownership | Async task per game | Clear ownership, explicit handoff |
| WebSocket routing | Redis routing keys + nginx | `game:{id}:server` keys with client-side redirect (code 4302) |
| Frontend state | Zustand | Lightweight, excellent TypeScript support |
| Auth | FastAPI-Users | Handles email + OAuth, battle-tested |
| Lobby persistence | Redis | Atomic operations via WATCH/MULTI/EXEC, Pub/Sub for real-time sync |
| Analytics | Amplitude | Session replay, auto-capture, no-op when API key absent |

---

## Tech Stack

**Backend**: FastAPI, SQLAlchemy 2.0, Alembic, FastAPI-Users, Python 3.12+, uv, Ruff, pytest

**Frontend**: React 19, TypeScript, Vite, Zustand, PixiJS, React Router 7, Amplitude, Vitest

**Infrastructure**: PostgreSQL 15+, Redis 7+, Caddy (reverse proxy + auto Let's Encrypt), Docker Compose

---

## Project Structure

```
kfchess-cc/
├── server/                    # Python backend
│   ├── src/kfchess/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── auth/              # Authentication (FastAPI-Users)
│   │   ├── api/               # REST endpoints (games, lobbies, campaign, replays, users)
│   │   ├── ws/                # WebSocket handlers (game, lobby, replay)
│   │   ├── game/              # Game engine (board, pieces, moves, collision, state, snapshot)
│   │   ├── ai/                # AI system (DummyAI, KungFuAI L1-L3)
│   │   ├── campaign/          # Campaign mode (levels, service)
│   │   ├── services/          # Business logic (game_service, game_registry)
│   │   ├── redis/             # Redis integration (client, routing, snapshots, heartbeat, lobby store)
│   │   ├── db/                # Database (models, session, repositories/)
│   │   ├── lobby/             # Lobby system (manager, models)
│   │   └── replay/            # Replay playback (session)
│   └── tests/                 # 1250+ tests
│
├── client/                    # TypeScript frontend
│   ├── src/
│   │   ├── api/               # HTTP client
│   │   ├── ws/                # WebSocket client
│   │   ├── stores/            # Zustand stores (game, replay, auth, lobby)
│   │   ├── game/              # PixiJS rendering (renderer, sprites, interpolation)
│   │   ├── components/        # React components
│   │   └── pages/             # Route pages
│   └── tests/                 # 420+ test cases
│
└── docs/                      # Documentation
```

---

## Backend Layers

```
┌──────────────────────────────────────────────────────────────────┐
│                     nginx (load balancer)                        │
│  - Round-robin across uvicorn workers                            │
│  - ?server= param routing for WebSocket redirects                │
├──────────────────────────────────────────────────────────────────┤
│                      FastAPI Application                         │
├───────────────────────────┬──────────────────────────────────────┤
│  API Layer (api/)         │  WebSocket Layer (ws/)               │
│  - REST endpoints         │  - Connection management             │
│  - Drain guards (503)     │  - Game routing + crash recovery     │
│  - Request validation     │  - Lobby pub/sub relay               │
├───────────────────────────┴──────────────────────────────────────┤
│                    Service Layer (services/)                     │
│  - Game lifecycle, active game registry, drain shutdown          │
├───────────────────────────┬──────────────────────────────────────┤
│  Game Engine (game/)      │  AI System (ai/)                     │
│  - Board state + snapshot │  - DummyAI (random moves)            │
│  - Move validation        │  - KungFuAI (L1-L3 tactical)         │
│  - Collision detection    │                                      │
├───────────────────────────┴──────────────────────────────────────┤
│  Redis (real-time)                │  PostgreSQL (persistent)     │
│  - Game snapshots + routing keys  │  - Users, replays, ratings   │
│  - Server heartbeats              │  - Active games registry     │
│  - Lobby state + pub/sub          │  - Campaign progress         │
└───────────────────────────────────┴──────────────────────────────┘
```

---

## Game Engine

### Core Data Structures

- **Piece**: `id`, `type` (P/N/B/R/Q/K), `player` (1-4), `row`/`col` (float for interpolation), `captured`, `moved`
- **Board**: `pieces` list, `board_type` (standard 8x8 or four_player 12x12)
- **Move**: `piece_id`, `path` (list of (row, col)), `start_tick`, `extra_move` (for castling)
- **Cooldown**: `piece_id`, `start_tick`, `duration`
- **GameState**: `game_id`, `board`, `speed`, `players`, `active_moves`, `cooldowns`, `current_tick`, `winner`, `replay_moves`

### Engine Interface

```python
class GameEngine:
    @staticmethod
    def create_game(speed, players, board_type) -> GameState
    @staticmethod
    def validate_move(state, player, piece_id, to_row, to_col) -> Move | None
    @staticmethod
    def apply_move(state, move) -> tuple[GameState, list[GameEvent]]
    @staticmethod
    def tick(state) -> tuple[GameState, list[GameEvent]]
    @staticmethod
    def check_winner(state) -> int | None  # None=ongoing, 0=draw, 1-4=winner
```

### Speed Configuration

| Speed | Move Time | Cooldown | Draw (no move) | Draw (no capture) |
|-------|-----------|----------|----------------|-------------------|
| Standard | 1s/square (10 ticks) | 10s (100 ticks) | 2 min | 3 min |
| Lightning | 0.2s/square (2 ticks) | 2s (20 ticks) | 30s | 45s |

---

## WebSocket Protocol

### Game Messages

**Client → Server:**

| Type | Payload | Description |
|------|---------|-------------|
| `join` | `{gameId, playerKey?}` | Join game (spectator if no key) |
| `ready` | `{}` | Signal ready to start |
| `move` | `{pieceId, toRow, toCol}` | Request a move |
| `leave` | `{}` | Leave the game |

**Server → Client:**

| Type | Payload | Description |
|------|---------|-------------|
| `joined` | `{gameState, playerNumber}` | Confirm join with full state |
| `player_joined` | `{player, playerNumber}` | Another player joined |
| `player_ready` | `{playerNumber}` | Player is ready |
| `game_start` | `{startTick}` | Game is starting |
| `update` | `{tick, moves, cooldowns, captures, ...}` | Game state delta |
| `game_over` | `{winner, ratings?}` | Game ended |
| `error` | `{code, message}` | Error occurred |

### Replay Messages

**Client → Server:** `play`, `pause`, `seek` (with tick number)

**Server → Client:** `replay_info`, `state_update` (same as game), `playback_status`, `game_over`

---

## Database Schema

### Core Tables

- **users**: id, email, username, password_hash, google_id, ratings (JSONB), is_verified, is_active
- **game_replays**: id (=game_id), speed, board_type, players (JSONB), moves (JSONB), total_ticks, winner
- **active_games**: game_id, game_type, speed, player_count, board_type, players (JSONB), server_id, started_at
- **campaign_progress**: user_id, level_id, completed_at (tracks campaign completion)
- **oauth_account**: user_id, oauth_name, account_id, account_email (for Google OAuth)

Note: Lobbies have migrated from PostgreSQL to Redis (Phase 4). The `lobbies` and `lobby_players` tables are no longer used.

### Redis Keys

- `game:{id}:snapshot` — serialized game state for crash recovery (2h TTL)
- `game:{id}:server` — routing key mapping game to server_id (2h TTL)
- `server:{id}:heartbeat` — server liveness indicator (5s TTL, refreshed every 1s)
- `lobby:{code}` — lobby state (hash)
- `lobby_events:{code}` — lobby pub/sub channel

---

## Authentication

Cookie-based JWT (30-day expiry) via FastAPI-Users.

| Feature | Implementation |
|---------|----------------|
| Password Auth | Email + password with Argon2 hashing |
| Google OAuth | Full flow with legacy user migration |
| Email Verification | Via Resend (optional for login) |
| Password Reset | Token-based, 1-hour expiry |
| Rate Limiting | SlowAPI per-endpoint limits |
| DEV_MODE | Set `DEV_MODE=true` + `DEV_USER_ID=1` to bypass auth |

---

## Replay System

Server-side simulation streamed via WebSocket (same format as live games). Client has no game engine logic.

- **Recording**: Moves stored as `ReplayMove` (tick, piece_id, to_row, to_col, player)
- **Playback**: ReplaySession runs ReplayEngine, streams state_update messages
- **Optimization**: Cached state for O(1) sequential playback, O(n) seek

See `docs/REPLAY_DESIGN.md` for full details.

---

## Multi-Server Architecture

Multiple uvicorn workers run behind nginx, sharing state via Redis. See `docs/MULTI_SERVER_DESIGN.md` for full design.

### Game Routing
- Each game has a Redis routing key (`game:{id}:server`) mapping it to its owning worker
- When a WebSocket connects to the wrong worker, it receives close code **4302** with the correct server_id as reason
- The client reconnects with `?server=workerN` query param; nginx routes to the correct upstream
- Routing keys are registered synchronously (awaited) at game creation to prevent races in multi-worker deployments

### Crash Recovery
- **Periodic snapshots**: Every 30 ticks (~1s at 30 Hz), full game state is saved to Redis
- **Server heartbeat**: Each worker writes a 5s-TTL heartbeat key, refreshed every 1s
- **On-demand recovery**: When a WebSocket arrives for a game on a dead server (no heartbeat), the receiving worker atomically claims the game via Lua CAS, loads the snapshot, and resumes the game loop
- **Startup restore**: On boot, workers scan for orphaned snapshots from dead servers and restore them
- **Split-brain protection**: Game loops periodically check their routing key ownership (every ~3s) and stop if another server has claimed the game

### Graceful Shutdown (Drain Mode)
- SIGTERM sets a drain flag; `/health` returns 503 (nginx stops routing new traffic)
- Game creation endpoints return 503; lobby `start_game` returns an error
- Final snapshots saved for all active games; heartbeat stopped; all WebSockets closed with code **4301**
- Routing keys are preserved so other workers can claim games via CAS

### Lobby System
- All lobby state lives in Redis with WATCH/MULTI/EXEC for atomic operations
- Real-time updates via Redis Pub/Sub relay per lobby channel
- Each WebSocket runs two concurrent tasks: pub/sub listener + message handler

---

## 4-Player Mode

Engine supports 12x12 board with corners cut (128 valid squares). Players at N/S/E/W positions.

See `docs/FOUR_PLAYER_DESIGN.md` for board layout and implementation plan.

---

## Analytics

Client-side instrumentation via Amplitude (`@amplitude/analytics-browser` + session replay plugin). Controlled by the `VITE_AMPLITUDE_API_KEY` env var — when absent, all calls are safe no-ops (dev/test).

**Wrapper:** `client/src/analytics.ts` exports `init`, `identify`, `track`, `reset`. All other files import from here, never from Amplitude directly.

**Identity:** User ID and properties (`username`, `pictureUrl`) are set on login/register/page-load via `identify()`; cleared on logout via `reset()`.

**Events tracked:**
- Page views (Home, Campaign, Lobbies, Watch, Profile, About, Privacy)
- Game lifecycle (Start Game, Finish Game, Resign, Offer Draw)
- Lobby actions (Create, Join, Ready, Start, Leave, Kick, Add AI, Update Settings)
- Campaign actions (Belt select, Level start)
- Replay actions (Watch, Like/Unlike, Copy Link)
- Auth actions (Login, Register, Logout, Resend Verification)
- UI interactions (Speed change, Volume change, Copy links, Reddit/Amplitude clicks)

---

## Implementation Status

- Core game engine (board, pieces, moves, collision, 2P and 4P support)
- REST API and WebSocket real-time communication
- React/TypeScript/PixiJS frontend with Zustand state
- Replay system (recording, storage, WebSocket playback with seek)
- Authentication (email/password, Google OAuth, verification, password reset)
- Lobby system (Redis-backed with Pub/Sub for real-time sync)
- AI opponents: 3 difficulty levels with arrival fields, tactical scoring, dodge/recapture analysis (see `docs/AI_DESIGN.md`)
- Campaign mode (belt progression, AI opponents per level)
- 4-player UI
- Multi-server support (game routing, crash recovery, drain mode, split-brain protection)
- ELO rating system with belt progression
- Game sound/music + volume controls
- Mobile-responsive UI (dynamic board sizing, touch drag-to-move, collapsible sidebars, landscape support)
- Comprehensive tests (1250+ backend, 420+ frontend)
- Amplitude analytics (page views, game lifecycle, lobby actions, auth events, session replay)
- Production deployment (Caddy + Let's Encrypt, systemd, rolling restarts, legacy data migration)

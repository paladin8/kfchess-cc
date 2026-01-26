# Kung Fu Chess - Architecture

This document describes the system architecture for Kung Fu Chess.

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Game state storage | In-memory (Redis planned) | Fast access, real-time updates |
| Game tick ownership | Async task per game | Clear ownership, explicit handoff |
| WebSocket routing | Direct connection | MVP simplicity (Redis pub/sub planned for multi-server) |
| Frontend state | Zustand | Lightweight, excellent TypeScript support |
| Auth | FastAPI-Users | Handles email + OAuth, battle-tested |
| Lobby persistence | PostgreSQL | Reliable storage, ACID transactions |

---

## Tech Stack

**Backend**: FastAPI, SQLAlchemy 2.0, Alembic, FastAPI-Users, Python 3.12+, uv, Ruff, pytest

**Frontend**: React 19, TypeScript, Vite, Zustand, PixiJS, React Router 7, Vitest

**Infrastructure**: PostgreSQL 15+, Redis 7+ (dev-ready via docker-compose)

---

## Project Structure

```
kfchess-cc/
├── server/                    # Python backend
│   ├── src/kfchess/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── auth/              # Authentication (FastAPI-Users)
│   │   ├── api/               # REST endpoints (games, lobbies, replays, users)
│   │   ├── ws/                # WebSocket handlers (game, lobby, replay)
│   │   ├── game/              # Game engine (board, pieces, moves, collision, state, replay)
│   │   ├── ai/                # AI system (base interface, dummy AI)
│   │   ├── services/          # Business logic (game_service)
│   │   ├── db/                # Database (models, session, repositories/)
│   │   ├── lobby/             # Lobby system (manager, models)
│   │   └── replay/            # Replay playback (session)
│   └── tests/                 # 532+ tests
│
├── client/                    # TypeScript frontend
│   ├── src/
│   │   ├── api/               # HTTP client
│   │   ├── ws/                # WebSocket client
│   │   ├── stores/            # Zustand stores (game, replay, auth, lobby)
│   │   ├── game/              # PixiJS rendering (renderer, sprites, interpolation)
│   │   ├── components/        # React components
│   │   └── pages/             # Route pages
│   └── tests/                 # 1800+ test cases
│
└── docs/                      # Documentation
```

---

## Backend Layers

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
├──────────────────────────┬──────────────────────────────┤
│  API Layer (api/)        │  WebSocket Layer (ws/)       │
│  - REST endpoints        │  - Connection management     │
│  - Request validation    │  - Message routing           │
├──────────────────────────┴──────────────────────────────┤
│                   Service Layer (services/)              │
│  - Game server management, business logic               │
├──────────────────────────┬──────────────────────────────┤
│  Game Engine (game/)     │  AI System (ai/)             │
│  - Board state           │  - AI interface              │
│  - Move validation       │  - DummyAI (random moves)    │
│  - Collision detection   │  - MCTS (planned)            │
├──────────────────────────┴──────────────────────────────┤
│  Data Layer: PostgreSQL (persistent) + Redis (planned)  │
└─────────────────────────────────────────────────────────┘
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
- **lobbies**: id, code, name, host_id, speed, player_count, is_public, is_ranked, status, game_id
- **lobby_players**: lobby_id, user_id, player_slot, is_ready
- **game_replays**: id (=game_id), speed, board_type, players (JSONB), moves (JSONB), total_ticks, winner
- **oauth_account**: user_id, oauth_name, account_id, account_email (for Google OAuth)

### Relationships

```
users 1──N lobby_players N──1 lobbies
users 1──N oauth_account
game_replays (standalone, players stored as JSONB)
```

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

## 4-Player Mode

Engine supports 12x12 board with corners cut (128 valid squares). Players at N/S/E/W positions.

See `docs/FOUR_PLAYER_DESIGN.md` for board layout and implementation plan.

---

## Implementation Status

### Completed
- Core game engine (board, pieces, moves, collision, 2P and 4P support)
- REST API and WebSocket real-time communication
- React/TypeScript/PixiJS frontend with Zustand state
- Replay system (recording, storage, WebSocket playback with seek)
- Authentication (email/password, Google OAuth, verification, password reset)
- Lobby system (create/join/leave, ready states, AI slots, persistence)
- Basic AI (DummyAI - random moves)
- 4-player UI
- Comprehensive tests (532+ backend, 1800+ frontend)

### Next Steps
1. Game sound/music + volume controls
2. Analytics + instrumentation
3. Advanced AI (MCTS implementation)
4. ELO rating system
5. Campaign mode
6. Redis for distributed scaling
7. Production deployment

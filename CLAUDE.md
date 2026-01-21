# Claude Code Project Context

## Project Overview
Kung Fu Chess - a real-time chess variant where pieces move simultaneously with cooldowns and collision-based captures.

## Project Structure
```
kfchess-cc/
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # Full architecture blueprint (design spec)
│   ├── MVP_IMPLEMENTATION.md # MVP implementation details
│   └── FOUR_PLAYER_DESIGN.md # 4-player mode design spec
├── scripts/                 # Development scripts
│   ├── dev.sh               # Start full dev environment (docker + servers)
│   ├── dev-servers.sh       # Start only dev servers (backend + frontend)
│   └── migrate.sh           # Run database migrations
├── server/                  # Python backend (FastAPI)
│   ├── src/kfchess/         # Source code
│   │   ├── main.py          # FastAPI app entry point
│   │   ├── settings.py      # Pydantic settings configuration
│   │   ├── game/            # Game engine (engine.py, board.py, moves.py, collision.py, state.py, pieces.py)
│   │   ├── api/             # HTTP API routes (router.py, games.py)
│   │   ├── ws/              # WebSocket handlers (handler.py, protocol.py)
│   │   ├── ai/              # AI system (base.py, dummy.py)
│   │   ├── services/        # Business logic (game_service.py)
│   │   ├── db/              # Database layer (placeholder)
│   │   ├── redis/           # Redis integration (placeholder)
│   │   ├── lobby/           # Lobby system (placeholder)
│   │   └── campaign/        # Campaign system (placeholder)
│   ├── tests/               # pytest tests
│   │   └── unit/game/       # Game engine unit tests
│   ├── alembic/             # Database migrations
│   └── pyproject.toml
├── client/                  # TypeScript frontend (React + Vite + PixiJS)
│   ├── src/
│   │   ├── api/             # HTTP API client (client.ts, types.ts)
│   │   ├── ws/              # WebSocket client (client.ts, types.ts)
│   │   ├── stores/          # Zustand state stores (game.ts, auth.ts, lobby.ts)
│   │   ├── game/            # Game rendering (renderer.ts, constants.ts, sprites.ts, interpolation.ts)
│   │   ├── components/      # React components (game/, layout/)
│   │   └── pages/           # Route pages (Home.tsx, Game.tsx)
│   ├── tests/               # Vitest tests
│   └── package.json
└── docker-compose.yml       # Dev infrastructure (PostgreSQL, Redis)
```

## Development Commands

### Quick Start
```bash
./scripts/dev.sh             # Start everything (docker + both servers)
./scripts/dev-servers.sh     # Start only dev servers (if docker already running)
./scripts/migrate.sh         # Run database migrations
```

### Backend (server/)
```bash
cd server
uv sync                      # Install dependencies
uv run alembic upgrade head  # Run migrations
uv run uvicorn kfchess.main:app --reload --port 8000  # Dev server

# Tests
uv run pytest tests/ -v      # Run all tests
uv run pytest tests/unit/game/ -v  # Run game engine tests only

# Linting
uv run ruff check src/
uv run ruff format src/
```

### Frontend (client/)
```bash
cd client
npm install                  # Install dependencies
npm run dev                  # Dev server (Vite, port 5173)
npm run build                # Production build
npm test                     # Run tests (Vitest)
npm run lint                 # Lint with ESLint
npm run typecheck            # Type check with tsc
```

### Infrastructure
```bash
docker-compose up -d postgres redis  # Start dev databases
```

## Tech Stack
- **Backend**: Python 3.12+, FastAPI 0.115+, SQLAlchemy 2.0+, Redis 5.2+, PostgreSQL 15+
- **Frontend**: React 19, TypeScript 5.7+, Vite 6, Zustand 5, PixiJS 8
- **Package Manager**: uv (Python), npm (TypeScript)
- **Linting**: Ruff (Python), ESLint (TypeScript)
- **Testing**: pytest + pytest-asyncio (Python), Vitest + React Testing Library (TypeScript)

## Game Engine Key Concepts
- **Tick-based**: 10 ticks/second (100ms tick period)
- **Mutable state**: Engine functions mutate state in place for performance. Use `GameState.copy()` if you need to preserve state (e.g., for AI lookahead)
- **Speed configs**: Standard (1s/square, 10s cooldown) and Lightning (0.2s/square, 2s cooldown)
- **Collision detection**: Pieces capture when within 0.4 squares distance
- **Knight mechanics**: Airborne (invisible) for 85% of move, can capture at 85%+
- **Castling**: King move includes extra_move for the rook

## Key Files for Game Logic
- `server/src/kfchess/game/engine.py` - Core game logic, tick processing, GameEngine class
- `server/src/kfchess/game/moves.py` - Move validation, path computation, castling
- `server/src/kfchess/game/collision.py` - Collision detection, capture logic
- `server/src/kfchess/game/state.py` - GameState dataclass, Speed enum, SpeedConfig
- `server/src/kfchess/game/board.py` - Board class, BoardType enum (standard/4-player)
- `server/src/kfchess/game/pieces.py` - Piece class, PieceType enum

## Key Files for Backend API/Services
- `server/src/kfchess/main.py` - FastAPI app, routes, WebSocket endpoint
- `server/src/kfchess/api/games.py` - Game REST endpoints (create, move, ready, legal-moves)
- `server/src/kfchess/ws/handler.py` - WebSocket connection handler, game loop
- `server/src/kfchess/ws/protocol.py` - WebSocket message types
- `server/src/kfchess/services/game_service.py` - GameService (in-memory game management)

## Key Files for Frontend
- `client/src/stores/game.ts` - Main game state store (Zustand)
- `client/src/game/renderer.ts` - GameRenderer class (PixiJS board rendering)
- `client/src/api/client.ts` - HTTP API client
- `client/src/ws/client.ts` - GameWebSocketClient class
- `client/src/pages/Game.tsx` - Game play page component

## Environment
- Copy `server/.env.example` to `server/.env`
- DEV_MODE=true bypasses authentication
- Frontend proxies `/api` and `/ws` to backend in dev mode (configured in vite.config.ts)

## Implementation Status

### Completed (MVP)
- Game engine with tick-based movement and collision detection
- 2-player and 4-player board support
- REST API for game management
- WebSocket real-time communication
- PixiJS board rendering
- Basic AI (DummyAI with random moves)
- Comprehensive game engine tests

### Placeholder/TODO
- Database persistence (models, migrations)
- User authentication (FastAPI-Users configured but not wired up)
- Lobby system
- Campaign mode
- Replay recording/playback
- Advanced AI (MCTS)
- ELO rating system

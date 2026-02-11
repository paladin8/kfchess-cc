# Kung Fu Chess

A real-time, turn-free chess game where players move pieces simultaneously. Play now at [kfchess.com](https://kfchess.com)!

## Overview

Kung Fu Chess removes the turn-based nature of traditional chess. Both players can move any of their pieces at any time, subject to cooldown periods after each move. This creates a fast-paced, action-oriented chess experience.

### Game Mechanics

- **Simultaneous movement**: No turns - move any piece at any time
- **Cooldowns**: After moving, a piece must wait before it can move again
- **Collision captures**: Pieces capture when they collide (within 0.4 squares)
- **Speed modes**:
  - **Standard**: 1 second per square, 10 second cooldown
  - **Lightning**: 0.2 seconds per square, 2 second cooldown
- **Special rules**:
  - Knights are "airborne" for the middle 70% of their move
  - Pawns only capture diagonally (straight moves don't capture)
  - Castling and pawn promotion supported

### Features

- [x] Core game engine with tick-based movement and collision detection
- [x] 2-player and 4-player board support (12x12 with corners cut)
- [x] REST API and WebSocket real-time communication
- [x] React/PixiJS frontend with smooth interpolated rendering
- [x] AI opponents with 3 difficulty levels (novice, intermediate, advanced)
- [x] Game replay recording, playback, and browser with likes
- [x] User authentication (email/password + Google OAuth)
- [x] Lobby system (create, join, ready, AI slots)
- [x] Campaign mode (belt progression, AI opponents per level)
- [x] ELO rating system with belt progression
- [x] Mobile-responsive UI (touch drag-to-move, collapsible sidebars, landscape)
- [x] Multi-server support (game routing, crash recovery, drain mode)
- [x] Game sound/music with volume controls
- [x] Amplitude analytics (page views, game lifecycle, session replay)
- [x] Production deployment (Caddy, systemd, rolling restarts)

## Tech Stack

**Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, FastAPI-Users, uv, Ruff, pytest

**Frontend**: React 19, TypeScript, Vite, Zustand, PixiJS, React Router 7, Vitest

**Infrastructure**: PostgreSQL 15+, Redis 7+, Caddy (auto Let's Encrypt), Docker Compose, systemd

## Architecture

```
Internet (HTTPS :443)
    │
    ▼
Caddy (auto Let's Encrypt)
├── /              → static files from client/dist/
├── /api/*         → ?server=workerN routing (or round-robin)
├── /ws/game/*     → ?server=workerN routing (or round-robin)
├── /ws/lobby/*    → round-robin
└── /ws/replay/*   → round-robin
    │
    ▼
systemd services
├── kfchess@worker1 → uvicorn :8001
└── kfchess@worker2 → uvicorn :8002
    │
    ▼
Docker Compose
├── postgres:15 → 127.0.0.1:5432
└── redis:7     → 127.0.0.1:6379
```

Game state lives in memory for low-latency access, with Redis snapshots every ~1 second for crash recovery. Workers share state via Redis routing keys and Pub/Sub. Rolling restarts are safe — workers save snapshots on SIGTERM, and clients auto-reconnect.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full system design.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker and Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python package manager)

### Quick Start

The easiest way to get started:

```bash
# Clone and enter the directory
git clone https://github.com/paladin8/kfchess-cc.git
cd kfchess-cc

# Copy environment files
cp server/.env.example server/.env
cp client/.env.example client/.env

# Start everything (Docker + both servers)
./scripts/dev.sh
```

Or step by step:

1. **Start infrastructure**
   ```bash
   docker-compose up -d postgres redis
   ```

2. **Backend setup**
   ```bash
   cd server
   uv sync
   uv run alembic upgrade head
   uv run uvicorn kfchess.main:app --reload --port 8000
   ```

3. **Frontend setup** (in another terminal)
   ```bash
   cd client
   npm install
   npm run dev
   ```

4. **Open the app**
   - Frontend: http://localhost:5173
   - API docs: http://localhost:8000/docs

### Running Tests

```bash
# Backend tests (1000+)
cd server
uv run pytest tests/ -v

# Frontend tests (400+)
cd client
npm test
```

### Development Scripts

```bash
./scripts/dev.sh         # Start Docker + both dev servers
./scripts/dev-servers.sh # Start only dev servers (Docker already running)
./scripts/migrate.sh     # Run database migrations
```

### Environment Variables

The backend runs in `DEV_MODE=true` by default, which auto-logs in as `DEV_USER_ID` for easier development. Set `DEV_MODE=false` to test actual authentication flows.

Key environment variables (see `server/.env.example` for full list):
- `DEV_MODE` - Enable development mode auto-login
- `SECRET_KEY` - JWT signing key (required in production)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - For Google OAuth (optional)
- `RESEND_API_KEY` - For sending verification/reset emails (optional)

## Production Deployment

Runs on a single AWS Lightsail instance (Ubuntu 24.04 LTS) with Caddy handling HTTPS via Let's Encrypt.

```bash
# Initial setup
sudo bash deploy/bootstrap.sh

# Deploy updates
sudo bash deploy/deploy.sh
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full instructions including legacy data migration.

## Project Structure

```
kfchess-cc/
├── server/              # Python FastAPI backend
│   ├── src/kfchess/
│   │   ├── game/        # Core game engine
│   │   ├── api/         # REST API routes
│   │   ├── ws/          # WebSocket handlers
│   │   ├── auth/        # Authentication (FastAPI-Users)
│   │   ├── lobby/       # Lobby management
│   │   ├── ai/          # AI opponents
│   │   ├── campaign/    # Campaign mode (levels, service)
│   │   ├── replay/      # Replay playback
│   │   ├── redis/       # Redis integration (routing, snapshots, heartbeat)
│   │   ├── services/    # Business logic (game lifecycle, registry)
│   │   └── db/          # Database (models, repositories)
│   ├── tests/           # pytest tests (unit + integration)
│   └── alembic/         # Database migrations
├── client/              # TypeScript React frontend
│   ├── src/
│   │   ├── game/        # PixiJS rendering
│   │   ├── stores/      # Zustand state (game, lobby, replay, auth)
│   │   ├── api/         # HTTP client
│   │   ├── ws/          # WebSocket client
│   │   ├── components/  # React components
│   │   └── pages/       # Route pages
│   └── tests/           # Vitest tests
├── deploy/              # Production deployment scripts
├── docs/                # Documentation
└── scripts/             # Development utilities
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and tech decisions
- [Deployment](docs/DEPLOYMENT.md) - Production setup, operations, and migration
- A variety of other documents for different parts of the game can be found in [docs/](docs/).

## License

MIT

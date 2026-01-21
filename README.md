# Kung Fu Chess

A real-time, turn-free chess game where players move pieces simultaneously.

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
  - Knights are "airborne" (invisible) for 85% of their move
  - Pawns only capture diagonally (straight moves don't capture)
  - Castling and pawn promotion supported

## Current Status

This is a rebuild of the original Kung Fu Chess. The MVP is functional:

- [x] Core game engine with tick-based movement and collision detection
- [x] 2-player and 4-player board support
- [x] REST API and WebSocket real-time communication
- [x] React/PixiJS frontend with smooth rendering
- [x] Basic AI opponent (random moves)
- [ ] User authentication and accounts
- [ ] Lobby system and matchmaking
- [ ] Game replay recording/playback
- [ ] Advanced AI (MCTS)

## Tech Stack

- **Backend**: Python 3.12+, FastAPI 0.115+, SQLAlchemy 2.0+
- **Frontend**: React 19, TypeScript 5.7+, Vite 6, PixiJS 8, Zustand 5
- **Database**: PostgreSQL 15+
- **Cache/Pub-Sub**: Redis 7+

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
git clone <repo-url> kfchess-cc
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
# Backend tests
cd server
uv run pytest tests/ -v

# Frontend tests
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

The backend runs in `DEV_MODE=true` by default, which bypasses authentication for easier development.

## Project Structure

```
kfchess-cc/
├── server/              # Python FastAPI backend
│   ├── src/kfchess/
│   │   ├── game/        # Core game engine
│   │   ├── api/         # REST API routes
│   │   ├── ws/          # WebSocket handlers
│   │   ├── ai/          # AI opponents
│   │   └── services/    # Business logic
│   ├── tests/           # pytest tests
│   └── alembic/         # Database migrations
├── client/              # TypeScript React frontend
│   ├── src/
│   │   ├── game/        # PixiJS rendering
│   │   ├── stores/      # Zustand state
│   │   ├── api/         # HTTP client
│   │   ├── ws/          # WebSocket client
│   │   ├── components/  # React components
│   │   └── pages/       # Route pages
│   └── tests/           # Vitest tests
├── docs/                # Documentation
└── scripts/             # Development utilities
```

## Documentation

- [Architecture](./docs/ARCHITECTURE.md) - System design, technical decisions, and implementation status
- [MVP Implementation](./docs/MVP_IMPLEMENTATION.md) - Detailed MVP implementation notes
- [4-Player Design](./docs/FOUR_PLAYER_DESIGN.md) - 4-player mode specification
- [Original Implementation](./docs/KFCHESS_ORIGINAL_IMPLEMENTATION.md) - Reference for the legacy system
- [CLAUDE.md](./CLAUDE.md) - Quick reference for Claude Code development

## License

MIT

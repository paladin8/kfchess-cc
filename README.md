# Kung Fu Chess

A real-time, turn-free chess game where players move pieces simultaneously.

## Overview

Kung Fu Chess removes the turn-based nature of traditional chess. Both players can move any of their pieces at any time, subject to cooldown periods after each move. This creates a fast-paced, action-oriented chess experience.

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2, Redis
- **Frontend**: React 18, TypeScript, Vite, PixiJS 8, Zustand
- **Database**: PostgreSQL 15+
- **Cache/Pub-Sub**: Redis 7+

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker and Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python package manager)

### Quick Start

1. **Start infrastructure**
   ```bash
   docker-compose up -d
   ```

2. **Backend setup**
   ```bash
   cd server
   uv sync
   uv run alembic upgrade head
   ```

3. **Frontend setup**
   ```bash
   cd client
   npm install
   ```

4. **Start development servers**
   ```bash
   # Terminal 1: Backend
   cd server && uv run uvicorn kfchess.main:app --reload --port 8000

   # Terminal 2: Frontend
   cd client && npm run dev
   ```

   Or use the convenience script:
   ```bash
   ./scripts/dev.sh
   ```

5. **Open the app**
   - Frontend: http://localhost:5173
   - API docs: http://localhost:8000/docs

### Environment Variables

Copy the example env files and configure:

```bash
cp server/.env.example server/.env
cp client/.env.example client/.env
```

## Project Structure

```
kfchess-cc/
├── server/           # Python FastAPI backend
│   ├── src/kfchess/  # Application code
│   ├── tests/        # Backend tests
│   └── alembic/      # Database migrations
├── client/           # TypeScript React frontend
│   ├── src/          # Application code
│   └── tests/        # Frontend tests
└── scripts/          # Development utilities
```

## Documentation

- [Architecture](./ARCHITECTURE.md) - System design and technical decisions
- [Original Implementation](./KFCHESS_ORIGINAL_IMPLEMENTATION.md) - Reference for the legacy system

## License

MIT

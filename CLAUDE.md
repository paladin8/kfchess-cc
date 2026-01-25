# Kung Fu Chess - Claude Code Instructions

## Git Workflow
- Do NOT commit or push changes unless explicitly asked
- Always run tests and linting before committing:
  - Backend: `cd server && uv run pytest tests/ -v && uv run ruff check src/ tests/`
  - Frontend: `cd client && npm test && npm run lint && npm run typecheck`

## Development Commands
```bash
# Quick start
./scripts/dev.sh             # Start docker + both servers

# Backend (uses uv, not pip)
cd server
uv sync                      # Install dependencies
uv run alembic upgrade head  # Run migrations
uv run pytest tests/ -v      # Run tests
uv run ruff check src/       # Lint

# Frontend
cd client
npm install && npm run dev   # Install and start dev server
npm test                     # Run tests
```

## Game Engine Gotchas
- **Mutable state**: Engine functions mutate `GameState` in place for performance. Use `GameState.copy()` if you need to preserve state (e.g., for AI lookahead).
- **Tick-based**: 10 ticks/second (100ms period). All timing is in ticks, not milliseconds.
- **Collision threshold**: Pieces capture when within 0.4 squares distance.
- **Knight mechanics**: Airborne (invisible) for 85% of move, can only capture at 85%+ progress.
- **Speed configs**: Standard (1s/square, 10s cooldown) vs Lightning (0.2s/square, 2s cooldown).

## Environment
- `DEV_MODE=true` bypasses authentication (auto-logs in as DEV_USER_ID)
- Frontend proxies `/api` and `/ws` to backend in dev mode (vite.config.ts)

## Architecture References
For detailed specs, see:
- @docs/ARCHITECTURE.md - System design and implementation status
- @docs/REPLAY_DESIGN.md - Replay system details
- @docs/FOUR_PLAYER_DESIGN.md - 4-player board layout

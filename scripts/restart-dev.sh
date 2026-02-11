#!/bin/bash
# Restart development servers (for Claude Code)
# Kills any existing servers and starts new ones in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Kill existing servers
echo "Stopping existing servers..."
pkill -f "uvicorn kfchess.main:app" 2>/dev/null || true
pkill -f "vite.*kfchess" 2>/dev/null || true
sleep 1

# Start backend (stable server ID so games survive restarts, like production)
echo "Starting backend..."
cd "$PROJECT_DIR/server"
KFCHESS_SERVER_ID=dev uv run uvicorn kfchess.main:app --reload --port 8000 > /tmp/kfchess-backend.log 2>&1 &

# Start frontend
echo "Starting frontend..."
cd "$PROJECT_DIR/client"
npm run dev > /tmp/kfchess-frontend.log 2>&1 &

# Wait for servers to be ready
sleep 3

# Verify
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "Backend ready: http://localhost:8000"
else
    echo "Backend may still be starting (check /tmp/kfchess-backend.log)"
fi

if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "Frontend ready: http://localhost:5173"
else
    echo "Frontend may still be starting (check /tmp/kfchess-frontend.log)"
fi

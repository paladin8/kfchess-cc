#!/bin/bash
# Start both development servers
# Uses trap to cleanup on exit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "Starting development servers..."

# Start backend
cd "$PROJECT_DIR/server"
uv run uvicorn kfchess.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
cd "$PROJECT_DIR/client"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Servers running:"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for either process to exit
wait

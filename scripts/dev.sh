#!/bin/bash
# Development startup script
# Starts all services needed for local development

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting Kung Fu Chess development environment..."

# Check for required tools
command -v docker >/dev/null 2>&1 || { echo "docker is required but not installed."; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "uv is required but not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required but not installed."; exit 1; }

# Start infrastructure
echo "Starting PostgreSQL and Redis..."
docker-compose -f "$PROJECT_DIR/docker-compose.yml" up -d

# Wait for services to be ready
echo "Waiting for services..."
sleep 3

# Check if .env files exist
if [ ! -f "$PROJECT_DIR/server/.env" ]; then
    echo "Creating server/.env from example..."
    cp "$PROJECT_DIR/server/.env.example" "$PROJECT_DIR/server/.env"
fi

if [ ! -f "$PROJECT_DIR/client/.env" ]; then
    echo "Creating client/.env from example..."
    cp "$PROJECT_DIR/client/.env.example" "$PROJECT_DIR/client/.env"
fi

# Install dependencies if needed
if [ ! -d "$PROJECT_DIR/server/.venv" ]; then
    echo "Installing Python dependencies..."
    cd "$PROJECT_DIR/server"
    uv sync
fi

if [ ! -d "$PROJECT_DIR/client/node_modules" ]; then
    echo "Installing Node dependencies..."
    cd "$PROJECT_DIR/client"
    npm install
fi

echo ""
echo "Development environment is ready!"
echo ""
echo "Start the servers in separate terminals:"
echo ""
echo "  Backend:  cd server && uv run uvicorn kfchess.main:app --reload --port 8000"
echo "  Frontend: cd client && npm run dev"
echo ""
echo "Or run them together with:"
echo "  ./scripts/dev-servers.sh"
echo ""
echo "URLs:"
echo "  Frontend: http://localhost:5173"
echo "  API:      http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"

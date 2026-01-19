#!/bin/bash
# Run database migrations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/server"

case "$1" in
    "upgrade")
        echo "Running migrations..."
        uv run alembic upgrade head
        ;;
    "downgrade")
        echo "Rolling back last migration..."
        uv run alembic downgrade -1
        ;;
    "new")
        if [ -z "$2" ]; then
            echo "Usage: $0 new <migration_message>"
            exit 1
        fi
        echo "Creating new migration: $2"
        uv run alembic revision --autogenerate -m "$2"
        ;;
    "history")
        echo "Migration history:"
        uv run alembic history
        ;;
    *)
        echo "Usage: $0 {upgrade|downgrade|new <message>|history}"
        exit 1
        ;;
esac

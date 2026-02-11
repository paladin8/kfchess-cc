#!/usr/bin/env bash
# Worker wrapper script for systemd.
# Derives the port from KFCHESS_SERVER_ID (e.g., worker1 → 8001, worker2 → 8002).
set -euo pipefail

if [[ -z "${KFCHESS_SERVER_ID:-}" ]]; then
    echo "ERROR: KFCHESS_SERVER_ID is not set" >&2
    exit 1
fi

NUM="${KFCHESS_SERVER_ID//[!0-9]/}"
if [[ -z "$NUM" ]]; then
    echo "ERROR: Cannot extract number from KFCHESS_SERVER_ID=$KFCHESS_SERVER_ID" >&2
    exit 1
fi

PORT=$((8000 + NUM))

exec uv run uvicorn kfchess.main:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --workers 1 \
    --log-level info

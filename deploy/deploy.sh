#!/usr/bin/env bash
# Deploy the latest code to production.
# Run as root or with sudo: sudo bash deploy.sh
#
# Options:
#   --skip-frontend   Skip npm ci + npm run build (use when frontend
#                     bundle was pre-built and uploaded by e2e-deploy.sh)
#
# Steps:
#   1. Pull latest code
#   2. Install backend dependencies (+ frontend unless --skip-frontend)
#   3. Build frontend (unless --skip-frontend)
#   4. Run database migrations
#   5. Regenerate Caddyfile and reload Caddy
#   6. Rolling restart workers with health checks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# ─── Parse flags ──────────────────────────────────────────────

SKIP_FRONTEND=false
for arg in "$@"; do
    case "$arg" in
        --skip-frontend) SKIP_FRONTEND=true ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

# ─── Helpers ──────────────────────────────────────────────────

log() { echo -e "\n\033[1;34m==>\033[0m \033[1m$*\033[0m"; }
die() { echo -e "\033[1;31mERROR:\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "This script must be run as root (sudo bash deploy.sh)"
[[ -d "$DEPLOY_DIR/.git" ]] || die "Repo not found at $DEPLOY_DIR — run bootstrap.sh first"

# ─── 1. Pull latest code ─────────────────────────────────────

log "Pulling latest code"
sudo -u kfchess git -C "$DEPLOY_DIR" fetch origin "$BRANCH"
sudo -u kfchess git -C "$DEPLOY_DIR" reset --hard "origin/$BRANCH"

# ─── 2. Install dependencies ─────────────────────────────────

log "Installing backend dependencies"
sudo -u kfchess bash -c "cd $DEPLOY_DIR/server && uv sync --frozen"

if [[ "$SKIP_FRONTEND" == "false" ]]; then
    log "Installing frontend dependencies"
    sudo -u kfchess bash -c "cd $DEPLOY_DIR/client && npm ci"
else
    log "Skipping frontend dependencies (--skip-frontend)"
fi

# ─── 3. Build frontend ───────────────────────────────────────

if [[ "$SKIP_FRONTEND" == "false" ]]; then
    log "Building frontend"
    sudo -u kfchess bash -c "cd $DEPLOY_DIR/client && npm run build"
else
    log "Skipping frontend build (--skip-frontend)"
fi

# ─── 4. Database migrations ──────────────────────────────────

log "Running database migrations"
sudo -u kfchess bash -c "cd $DEPLOY_DIR/server && uv run alembic upgrade head"

# ─── 5. Caddyfile ────────────────────────────────────────────

log "Regenerating Caddyfile"
bash "$DEPLOY_DIR/deploy/generate-caddyfile.sh" --install
systemctl daemon-reload
systemctl reload caddy

# ─── 6. Rolling restart workers ──────────────────────────────

# Final daemon-reload right before restarts to ensure systemd has
# picked up any changes from previous steps (Caddyfile install, etc.)
systemctl daemon-reload

log "Rolling restart of $NUM_WORKERS workers"

HEALTH_TIMEOUT=15  # seconds to wait for health check
RESTART_BUFFER=5   # seconds to wait between workers for game handoff

for i in $(seq 1 "$NUM_WORKERS"); do
    WORKER="kfchess@worker${i}"
    PORT=$((8000 + i))

    echo "Restarting $WORKER..."
    systemctl restart "$WORKER"

    # Wait for health check
    for attempt in $(seq 1 "$HEALTH_TIMEOUT"); do
        if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
            echo "  $WORKER is healthy (port $PORT)"
            break
        fi
        if [[ $attempt -eq $HEALTH_TIMEOUT ]]; then
            die "$WORKER failed health check after ${HEALTH_TIMEOUT}s. Aborting rolling restart."
        fi
        sleep 1
    done

    # Buffer between workers so the next worker can claim games from the one
    # that just drained before it also restarts
    if [[ $i -lt $NUM_WORKERS ]]; then
        echo "  Waiting ${RESTART_BUFFER}s before next worker..."
        sleep "$RESTART_BUFFER"
    fi
done

# ─── Done ─────────────────────────────────────────────────────

log "Deploy complete!"
echo "All $NUM_WORKERS workers are healthy."

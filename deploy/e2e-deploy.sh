#!/usr/bin/env bash
# End-to-end deploy: pre-checks → SSH deploy → sanity check.
# Usage: bash deploy/e2e-deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SSH_KEY="$HOME/.ssh/LightsailDefaultKey-us-west-2.pem"
SSH_HOST="ubuntu@35.167.158.216"
REMOTE_DEPLOY_DIR="/var/www/kfchess"
SITE_URL="https://kfchess.com"

# ─── Helpers ──────────────────────────────────────────────────

log() { echo -e "\n\033[1;34m==>\033[0m \033[1m$*\033[0m"; }
die() { echo -e "\033[1;31mFAILED:\033[0m $*" >&2; exit 1; }

# ─── Phase 1: Pre-deploy checks ──────────────────────────────

log "Phase 1: Pre-deploy checks"

echo "Checking git status..."
if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
    die "Working tree is dirty. Commit or stash changes first."
fi

echo "Checking for unpushed commits..."
git -C "$REPO_DIR" fetch origin main --quiet
LOCAL=$(git -C "$REPO_DIR" rev-parse HEAD)
REMOTE=$(git -C "$REPO_DIR" rev-parse origin/main)
if [[ "$LOCAL" != "$REMOTE" ]]; then
    die "Local HEAD ($LOCAL) differs from origin/main ($REMOTE). Push first."
fi

echo "Running backend tests..."
(cd "$REPO_DIR/server" && uv run pytest tests/ -v) || die "Backend tests failed."

echo "Running backend lint..."
(cd "$REPO_DIR/server" && uv run ruff check src/ tests/) || die "Backend lint failed."

echo "Running frontend tests..."
(cd "$REPO_DIR/client" && npm test -- --run) || die "Frontend tests failed."

echo "Running frontend lint..."
(cd "$REPO_DIR/client" && npm run lint) || die "Frontend lint failed."

echo "Running frontend typecheck..."
(cd "$REPO_DIR/client" && npm run typecheck) || die "Frontend typecheck failed."

echo "Pre-deploy checks passed."

# ─── Phase 2: Build frontend locally ─────────────────────────

log "Phase 2: Build frontend"

echo "Building frontend bundle..."
(cd "$REPO_DIR/client" && npm run build) || die "Frontend build failed."

# ─── Phase 3: Upload frontend bundle ─────────────────────────

log "Phase 3: Upload frontend bundle"

# Upload to temp dir (ubuntu user can't write to kfchess-owned dist/)
# then move into place with correct ownership
rsync -az --delete -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
    "$REPO_DIR/client/dist/" "$SSH_HOST:/tmp/kfchess-dist/" \
    || die "Frontend upload failed."

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$SSH_HOST" \
    "sudo rsync -a --delete /tmp/kfchess-dist/ $REMOTE_DEPLOY_DIR/client/dist/ && sudo chown -R kfchess:kfchess $REMOTE_DEPLOY_DIR/client/dist/ && rm -rf /tmp/kfchess-dist" \
    || die "Frontend install failed."

echo "Frontend bundle uploaded."

# ─── Phase 4: Deploy backend ─────────────────────────────────

log "Phase 4: Deploy via SSH (--skip-frontend)"

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$SSH_HOST" \
    "sudo bash $REMOTE_DEPLOY_DIR/deploy/deploy.sh --skip-frontend" \
    || die "Remote deploy failed."

echo "Deploy completed."

# ─── Phase 5: Sanity check ───────────────────────────────────

log "Phase 5: Sanity check ($SITE_URL)"

# Brief pause for workers to fully start
sleep 3

uv run "$SCRIPT_DIR/sanity_check.py" "$SITE_URL" --timeout 20 \
    || die "Sanity check failed."

# ─── Done ─────────────────────────────────────────────────────

log "E2E deploy complete!"

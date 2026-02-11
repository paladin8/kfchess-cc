#!/usr/bin/env bash
# Bootstrap script for a fresh AWS Lightsail instance (Ubuntu 24.04 LTS).
# Run as root or with sudo: sudo bash bootstrap.sh
#
# This script:
#   1. Installs system packages (Docker, Caddy, Python 3.12, uv, Node.js 20)
#   2. Creates the kfchess system user
#   3. Clones the repo
#   4. Starts Postgres + Redis via Docker Compose
#   5. Installs dependencies and builds the frontend
#   6. Runs database migrations
#   7. Installs systemd services and Caddyfile
#   8. Starts everything
#
# Prerequisites:
#   - DNS for kfchess.com must point to this instance's public IP
#     (Caddy needs this to obtain a Let's Encrypt certificate)
#   - Ports 80 and 443 must be open in the Lightsail firewall
#   - deploy/.env must exist with POSTGRES_PASSWORD set (see deploy/.env.example)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# ─── Helpers ──────────────────────────────────────────────────

log() { echo -e "\n\033[1;34m==>\033[0m \033[1m$*\033[0m"; }
warn() { echo -e "\033[1;33mWARN:\033[0m $*"; }
die() { echo -e "\033[1;31mERROR:\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "This script must be run as root (sudo bash bootstrap.sh)"

# Load secrets
DEPLOY_ENV="$SCRIPT_DIR/.env"
if [[ ! -f "$DEPLOY_ENV" ]]; then
    die "Missing $DEPLOY_ENV — copy deploy/.env.example to deploy/.env and set POSTGRES_PASSWORD"
fi
source "$DEPLOY_ENV"
[[ -n "${POSTGRES_PASSWORD:-}" ]] || die "POSTGRES_PASSWORD is not set in $DEPLOY_ENV"
export POSTGRES_PASSWORD

# ─── 1. System packages ──────────────────────────────────────

log "Installing system packages"
apt-get update -qq
apt-get install -y -qq \
    git curl wget software-properties-common \
    ca-certificates gnupg

# Docker (official repo)
if ! command -v docker &>/dev/null; then
    log "Installing Docker"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# Caddy (official repo)
if ! command -v caddy &>/dev/null; then
    log "Installing Caddy"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
fi

# ─── 2. Python 3.12 ──────────────────────────────────────────

if ! command -v python3.12 &>/dev/null; then
    log "Installing Python 3.12"
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
fi

# ─── 3. uv ───────────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    log "Installing uv"
    # Install directly to /usr/local/bin so it's available to all users
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
fi

# ─── 4. Node.js 20 ───────────────────────────────────────────

if ! command -v node &>/dev/null || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]]; then
    log "Installing Node.js 20"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi

# ─── 5. Claude Code ──────────────────────────────────────────

if ! command -v claude &>/dev/null; then
    log "Installing Claude Code"
    curl -fsSL https://claude.ai/install.sh | bash
    # Make claude available system-wide
    if [[ -f /root/.claude/local/bin/claude ]]; then
        ln -sf /root/.claude/local/bin/claude /usr/local/bin/claude
    elif [[ -f /root/.local/bin/claude ]]; then
        ln -sf /root/.local/bin/claude /usr/local/bin/claude
    fi
fi

# ─── 6. Create kfchess user ──────────────────────────────────

if ! id kfchess &>/dev/null; then
    log "Creating kfchess system user"
    useradd --system --create-home --shell /bin/bash kfchess
    usermod -aG docker kfchess
fi

# ─── 7. Clone repo ───────────────────────────────────────────

if [[ ! -d "$DEPLOY_DIR/.git" ]]; then
    log "Cloning repo to $DEPLOY_DIR"
    mkdir -p "$(dirname "$DEPLOY_DIR")"
    chown kfchess:kfchess "$(dirname "$DEPLOY_DIR")"
    sudo -u kfchess git clone --branch "$BRANCH" "$REPO_URL" "$DEPLOY_DIR"
else
    log "Repo already exists at $DEPLOY_DIR, pulling latest"
    sudo -u kfchess git -C "$DEPLOY_DIR" pull origin "$BRANCH"
fi

# Copy deploy secrets into the clone (gitignored, so not in the repo)
cp "$DEPLOY_ENV" "$DEPLOY_DIR/deploy/.env"
chown kfchess:kfchess "$DEPLOY_DIR/deploy/.env"
chmod 600 "$DEPLOY_DIR/deploy/.env"

# ─── 8. Environment files ────────────────────────────────────

if [[ ! -f "$DEPLOY_DIR/server/.env" ]]; then
    log "Creating server .env from template"
    cp "$DEPLOY_DIR/server/.env.example" "$DEPLOY_DIR/server/.env"
    # Set production defaults
    sed -i 's/DEV_MODE=true/DEV_MODE=false/' "$DEPLOY_DIR/server/.env"
    sed -i 's/DEV_USER_ID=1/DEV_USER_ID=0/' "$DEPLOY_DIR/server/.env"
    sed -i "s|FRONTEND_URL=http://localhost:5173|FRONTEND_URL=https://${DOMAIN}|" "$DEPLOY_DIR/server/.env"
    # Set DATABASE_URL with the correct password (use python to avoid sed issues with special chars)
    python3.12 -c "
import sys, urllib.parse
env = '$DEPLOY_DIR/server/.env'
pw = urllib.parse.quote(sys.argv[1], safe='')
with open(env) as f: text = f.read()
text = text.replace(
    'DATABASE_URL=postgresql+asyncpg://kfchess:kfchess@localhost:5432/kfchess',
    f'DATABASE_URL=postgresql+asyncpg://kfchess:{pw}@localhost:5432/kfchess'
)
with open(env, 'w') as f: f.write(text)
" "$POSTGRES_PASSWORD"
    # Generate a random secret key
    SECRET=$(python3.12 -c "import secrets; print(secrets.token_urlsafe(48))")
    sed -i "s/SECRET_KEY=change-me-to-a-real-secret-key/SECRET_KEY=${SECRET}/" "$DEPLOY_DIR/server/.env"
    chown kfchess:kfchess "$DEPLOY_DIR/server/.env"
    chmod 600 "$DEPLOY_DIR/server/.env"
    warn "Review $DEPLOY_DIR/server/.env — GOOGLE_CLIENT_ID/SECRET, RESEND_API_KEY, etc. still need to be set."
fi

if [[ ! -f "$DEPLOY_DIR/client/.env" ]]; then
    log "Creating client .env"
    cat > "$DEPLOY_DIR/client/.env" << EOF
# Production client config
# No API/WS URLs needed — Caddy proxies everything on the same origin
VITE_AMPLITUDE_API_KEY=
EOF
    chown kfchess:kfchess "$DEPLOY_DIR/client/.env"
fi

# ─── 9. Start Postgres + Redis ────────────────────────────────

log "Starting Postgres and Redis"
cd "$DEPLOY_DIR"
docker compose -f deploy/docker-compose.prod.yml up -d

# Wait for Postgres
log "Waiting for Postgres to be ready"
for i in $(seq 1 30); do
    if docker compose -f deploy/docker-compose.prod.yml exec -T postgres pg_isready -U kfchess &>/dev/null; then
        echo "Postgres is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        die "Postgres failed to start within 30 seconds"
    fi
    sleep 1
done

# ─── 10. Install dependencies ────────────────────────────────

log "Installing backend dependencies"
sudo -u kfchess bash -c "cd $DEPLOY_DIR/server && uv sync"

log "Installing frontend dependencies and building"
sudo -u kfchess bash -c "cd $DEPLOY_DIR/client && npm ci && npm run build"

# ─── 11. Run migrations ──────────────────────────────────────

log "Running database migrations"
sudo -u kfchess bash -c "cd $DEPLOY_DIR/server && uv run alembic upgrade head"

# ─── 12. Install systemd services ────────────────────────────

log "Installing systemd services"
cp "$DEPLOY_DIR/deploy/systemd/kfchess@.service" /etc/systemd/system/kfchess@.service
chmod +x "$DEPLOY_DIR/deploy/kfchess-worker.sh"
systemctl daemon-reload

# ─── 13. Generate and install Caddyfile ───────────────────────

log "Generating Caddyfile"
bash "$DEPLOY_DIR/deploy/generate-caddyfile.sh" --install

# ─── 14. Start services ──────────────────────────────────────

log "Starting worker services"
for i in $(seq 1 "$NUM_WORKERS"); do
    systemctl enable "kfchess@worker${i}"
    systemctl start "kfchess@worker${i}"
    echo "Started kfchess@worker${i}"
done

log "Starting Caddy"
systemctl enable caddy
systemctl restart caddy

# ─── Done ─────────────────────────────────────────────────────

log "Bootstrap complete!"
echo ""
echo "Caddy will automatically obtain a Let's Encrypt certificate for ${DOMAIN}."
echo "Make sure DNS is pointing to this instance and ports 80/443 are open."
echo ""
echo "Next steps:"
echo "  1. Review $DEPLOY_DIR/server/.env (optional services: Google OAuth, Resend, S3)"
echo "  2. Set VITE_AMPLITUDE_API_KEY in $DEPLOY_DIR/client/.env"
echo "  3. If you changed .env files, redeploy: sudo bash $DEPLOY_DIR/deploy/deploy.sh"
echo "  4. Verify: curl https://${DOMAIN}/caddy-health"
echo ""
echo "To migrate legacy data:"
echo "  1. Copy legacy_data.sql to the server"
echo "  2. Run: bash $DEPLOY_DIR/deploy/migrate-legacy-data.sh legacy_data.sql"

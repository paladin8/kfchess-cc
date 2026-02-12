# Production Deployment

Kung Fu Chess runs on a single AWS Lightsail instance (Ubuntu 24.04 LTS) with Caddy handling HTTPS via Let's Encrypt.

## Architecture

```
Internet (HTTPS :443)
    │
    ▼
Caddy (native, ports 80/443 — auto Let's Encrypt)
├── /              → static files from client/dist/
├── /api/*         → round-robin to workers
├── /ws/game/*     → ?server=workerN routing (or round-robin)
├── /ws/lobby/*    → round-robin
└── /ws/replay/*   → round-robin
    │
    ▼
systemd services
├── kfchess@worker1 → uvicorn :8001
└── kfchess@worker2 → uvicorn :8002
    │
    ▼
Docker Compose
├── postgres:15 → 127.0.0.1:5432
└── redis:7     → 127.0.0.1:6379
```

## Prerequisites

- AWS Lightsail instance running **Ubuntu 24.04 LTS**
- DNS A record: `kfchess.com` → instance public IP
- Lightsail firewall: ports **80** and **443** open
- SSH access to the instance

## Files

All deployment files live in `deploy/`:

| File | Purpose |
|------|---------|
| `config.sh` | Configuration (worker count, domain, repo URL) — tracked in git |
| `.env.example` | Template for deploy secrets — tracked in git |
| `.env` | Actual deploy secrets (POSTGRES_PASSWORD) — **gitignored** |
| `bootstrap.sh` | One-time machine setup |
| `deploy.sh` | Deploy latest code (repeatable) |
| `docker-compose.prod.yml` | Postgres + Redis containers |
| `generate-caddyfile.sh` | Generates Caddyfile from worker count |
| `Caddyfile` | Generated Caddy config (do not edit manually) |
| `kfchess-worker.sh` | Worker wrapper (derives port from ID) |
| `systemd/kfchess@.service` | Systemd template unit |
| `migrate-legacy-data.sh` | Legacy database migration |

## Initial Setup

### 1. Get the deploy scripts onto the instance

SSH in and clone the repo to a temporary location (or scp the `deploy/` directory):

```bash
ssh user@<instance-ip>
git clone https://github.com/paladin8/kfchess-cc /tmp/kfchess-setup
cd /tmp/kfchess-setup/deploy
```

### 2. Configure

Create `deploy/.env` from the template and set a real Postgres password:

```bash
cp .env.example .env
vim .env   # set POSTGRES_PASSWORD to something strong
```

Review `config.sh` — the defaults should be fine for most setups:

```bash
NUM_WORKERS=2                                     # uvicorn worker processes
DEPLOY_DIR=/var/www/kfchess                       # where the repo lives on the server
DOMAIN=kfchess.com                                # your domain
REPO_URL=https://github.com/paladin8/kfchess-cc.git  # git remote
```

### 3. Bootstrap

```bash
sudo bash bootstrap.sh
```

This installs everything (Docker, Caddy, Python 3.12, uv, Node.js 20), creates the `kfchess` user, clones the repo to `/var/www/kfchess`, starts Postgres/Redis, builds the frontend, runs migrations, and starts all services.

The bootstrap script also:
- Creates `server/.env` with production defaults (DEV_MODE=false, random SECRET_KEY, correct DATABASE_URL password)
- Creates `client/.env` with a placeholder for the Amplitude key

### 4. Configure optional services

The core site works after bootstrap. For full functionality, edit the server env:

```bash
sudo -u kfchess vim /var/www/kfchess/server/.env
```

Optional:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — Google OAuth login
- `RESEND_API_KEY` — email verification and password reset
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_BUCKET` — profile picture uploads

Also set the Amplitude key in `client/.env` if using analytics:

```bash
sudo -u kfchess vim /var/www/kfchess/client/.env
```

### 5. Test before DNS cutover (optional)

If DNS still points to the old server, use HTTP-only mode to test:

```bash
sudo bash /var/www/kfchess/deploy/generate-caddyfile.sh --http-only --install
sudo systemctl reload caddy
```

Then visit `http://<instance-ip>/` in your browser or:

```bash
curl http://<instance-ip>/caddy-health      # should return "ok"
curl http://<instance-ip>/api/replays       # test API routing
```

When ready to go live, switch to production mode and flip DNS:

```bash
sudo bash /var/www/kfchess/deploy/generate-caddyfile.sh --install
sudo systemctl reload caddy
# Then update DNS A records for kfchess.com (and www) to the instance IP
```

Caddy will automatically obtain Let's Encrypt certificates once DNS resolves to the instance.

### 6. Redeploy after config changes

```bash
sudo bash /var/www/kfchess/deploy/deploy.sh
```

### 7. Verify

```bash
curl https://kfchess.com/caddy-health     # should return "ok"
curl http://127.0.0.1:8001/health          # should return {"status":"ok"}
curl http://127.0.0.1:8002/health          # should return {"status":"ok"}
```

## Deploying Updates

```bash
sudo bash /var/www/kfchess/deploy/deploy.sh
```

This does:
1. `git fetch && git reset --hard origin/main`
2. `uv sync --frozen` (backend deps)
3. `npm ci && npm run build` (frontend)
4. `alembic upgrade head` (migrations)
5. Regenerate Caddyfile and reload Caddy
6. Rolling restart: restarts each worker one at a time, waiting for its `/health` endpoint to return 200 before proceeding to the next

The rolling restart is safe because workers save game state snapshots to Redis during graceful shutdown (SIGTERM → drain mode). After restarting, workers pick up orphaned games from Redis. Clients auto-reconnect with jitter.

Caddy actively health-checks each backend (`/health` every 5s) and stops routing to unhealthy workers, so there are no dropped requests during restarts.

**Note:** `config.sh` is tracked in git and safe to pull — it contains no secrets. Secrets live in `deploy/.env` and `server/.env`, both of which are gitignored and preserved across deploys.

## Migrating Legacy Data

To import users and data from the original kfchess database:

**1. Export from old database:**

```bash
pg_dump --data-only --inserts --column-inserts \
  -t users -t campaign_progress -t game_history -t user_game_history \
  old_db_name > legacy_data.sql
```

**2. Copy to new server and run:**

```bash
bash /var/www/kfchess/deploy/migrate-legacy-data.sh legacy_data.sql
```

This creates staging tables, loads the dump, transforms the data (mapping old columns to new schema), resets sequences, and prints row counts. No host `psql` needed — it runs inside the Docker Postgres container.

**User migration notes:**
- Old users have no password but their `google_id` is set to their email, so Google OAuth login works immediately
- Users who want to use email/password login can use "forgot password" to set one
- `join_time` maps to `created_at`; `current_game` is dropped (transient state)
- User IDs are preserved so campaign progress and game history stay linked

## Operations

### Logs

Each worker logs to systemd journal. Log lines include the server ID (`[worker1]`, `[worker2]`) so you can tell workers apart even when tailing multiple units.

```bash
# Follow logs
journalctl -u kfchess@worker1 -f              # single worker
journalctl -u 'kfchess@*' -f                  # all workers
journalctl -u caddy -f                        # Caddy access/error logs

# Recent logs
journalctl -u kfchess@worker1 --since "5 min ago"
journalctl -u kfchess@worker1 --since today

# Filter by severity
journalctl -u 'kfchess@*' -p err              # errors only
journalctl -u 'kfchess@*' -p warning          # warnings and above

# Search for a specific game or user
journalctl -u 'kfchess@*' --since today | grep "game_id_here"
```

Log level is controlled by `LOG_LEVEL` in `server/.env` (default: `INFO`). Set to `DEBUG` for troubleshooting.

### Service management

```bash
systemctl status kfchess@worker1           # check worker status
systemctl restart kfchess@worker1          # restart a single worker
systemctl stop kfchess@worker1             # stop a worker

docker compose -f /var/www/kfchess/deploy/docker-compose.prod.yml ps      # check Postgres/Redis
docker compose -f /var/www/kfchess/deploy/docker-compose.prod.yml logs -f  # follow DB logs
```

### Changing worker count

1. Edit `NUM_WORKERS` in `deploy/config.sh`
2. Run `sudo bash deploy/deploy.sh`
3. Enable/start or disable/stop worker units as needed:

```bash
# Adding worker3
systemctl enable kfchess@worker3
systemctl start kfchess@worker3

# Removing worker3
systemctl stop kfchess@worker3
systemctl disable kfchess@worker3
```

### Cleaning up stale/orphaned games

The cleanup script removes stale `active_games` DB rows and orphaned Redis snapshots (snapshots with no matching DB row, which can cause zombie games on restart).

Dry run is the default — it shows what would be removed without deleting anything:

```bash
cd /var/www/kfchess/server

# Preview: games older than 30 minutes (default)
sudo -u kfchess uv run python scripts/cleanup_active_games.py

# Preview: all active games
sudo -u kfchess uv run python scripts/cleanup_active_games.py --all

# Preview: games older than 5 minutes
sudo -u kfchess uv run python scripts/cleanup_active_games.py --minutes 5

# Actually delete (add --commit)
sudo -u kfchess uv run python scripts/cleanup_active_games.py --all --commit
```

This cleans up both the PostgreSQL `active_games` table and the corresponding Redis keys (snapshots + routing), preventing zombie games from being restored on the next deploy.

### Database access

```bash
docker compose -f /var/www/kfchess/deploy/docker-compose.prod.yml exec postgres \
  psql -U kfchess -d kfchess
```

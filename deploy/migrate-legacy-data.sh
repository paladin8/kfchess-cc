#!/usr/bin/env bash
# Migrate legacy kfchess data into the new database.
#
# Prerequisites:
#   1. New database is running and migrations have been applied (alembic upgrade head)
#   2. Export data from old database:
#      pg_dump --data-only --inserts --column-inserts \
#        -t users -t campaign_progress -t game_history -t user_game_history \
#        old_db_name > legacy_data.sql
#
# Usage: bash migrate-legacy-data.sh legacy_data.sql
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# ─── Helpers ──────────────────────────────────────────────────

log() { echo -e "\n\033[1;34m==>\033[0m \033[1m$*\033[0m"; }
die() { echo -e "\033[1;31mERROR:\033[0m $*" >&2; exit 1; }

DUMP_FILE="${1:-}"
[[ -n "$DUMP_FILE" ]] || die "Usage: $0 <legacy_data.sql>"
[[ -f "$DUMP_FILE" ]] || die "File not found: $DUMP_FILE"

# Use psql inside the Docker postgres container (no host psql needed)
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"

psql_cmd() {
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U kfchess -d kfchess -v ON_ERROR_STOP=1 "$@"
}

# ─── 1. Create staging tables ────────────────────────────────

log "Creating staging tables"
psql_cmd << 'SQL'
-- Staging tables match the OLD schema exactly
CREATE TABLE IF NOT EXISTS _legacy_users (
    id bigint PRIMARY KEY,
    email text,
    username text,
    picture_url text,
    ratings jsonb,
    join_time timestamp without time zone,
    last_online timestamp without time zone,
    current_game jsonb
);

CREATE TABLE IF NOT EXISTS _legacy_campaign_progress (
    id bigint PRIMARY KEY,
    user_id bigint,
    progress jsonb
);

CREATE TABLE IF NOT EXISTS _legacy_game_history (
    id bigint PRIMARY KEY,
    replay jsonb
);

CREATE TABLE IF NOT EXISTS _legacy_user_game_history (
    id bigint PRIMARY KEY,
    user_id bigint,
    game_time timestamp without time zone,
    game_info jsonb
);

-- Truncate in case of re-run
TRUNCATE _legacy_users, _legacy_campaign_progress, _legacy_game_history, _legacy_user_game_history;
SQL

# ─── 2. Load dump into staging tables ────────────────────────

log "Loading dump into staging tables"

# Rewrite table names to staging tables and strip SET/SELECT/ALTER/CREATE statements
sed \
    -e 's/INSERT INTO public\.users /INSERT INTO _legacy_users /g' \
    -e 's/INSERT INTO public\.campaign_progress /INSERT INTO _legacy_campaign_progress /g' \
    -e 's/INSERT INTO public\.game_history /INSERT INTO _legacy_game_history /g' \
    -e 's/INSERT INTO public\.user_game_history /INSERT INTO _legacy_user_game_history /g' \
    -e '/^SET /d' \
    -e '/^SELECT /d' \
    -e '/^ALTER /d' \
    -e '/^CREATE /d' \
    -e '/^COMMENT /d' \
    -e '/^--/d' \
    -e '/^$/d' \
    -e '/INSERT INTO public\.active_games /d' \
    "$DUMP_FILE" | psql_cmd

# ─── 3. Transform and insert into new tables ─────────────────

log "Migrating users"
psql_cmd << 'SQL'
INSERT INTO users (id, email, username, picture_url, ratings, created_at, last_online,
                   hashed_password, google_id, is_active, is_verified, is_superuser)
SELECT
    id,
    email,
    username,
    picture_url,
    COALESCE(ratings, '{}'::jsonb),
    COALESCE(join_time, NOW()),
    COALESCE(last_online, NOW()),
    NULL,       -- hashed_password: users must use OAuth or forgot-password
    email,      -- google_id: set to email so legacy Google OAuth login works
    true,       -- is_active
    true,       -- is_verified (they authenticated via Google originally)
    false       -- is_superuser
FROM _legacy_users
ON CONFLICT (id) DO NOTHING;
SQL

log "Migrating campaign progress"
psql_cmd << 'SQL'
INSERT INTO campaign_progress (id, user_id, progress)
SELECT
    id,
    user_id,
    COALESCE(progress, '{}'::jsonb)
FROM _legacy_campaign_progress
WHERE user_id IN (SELECT id FROM users)
ON CONFLICT (id) DO NOTHING;
SQL

log "Migrating game history (legacy replays)"
psql_cmd << 'SQL'
INSERT INTO game_history (id, replay)
SELECT id, replay
FROM _legacy_game_history
ON CONFLICT (id) DO NOTHING;
SQL

log "Migrating user game history"
psql_cmd << 'SQL'
INSERT INTO user_game_history (id, user_id, game_time, game_info)
SELECT id, user_id, game_time, game_info
FROM _legacy_user_game_history
WHERE user_id IN (SELECT id FROM users)
ON CONFLICT (id) DO NOTHING;
SQL

# ─── 4. Reset sequences ──────────────────────────────────────

log "Resetting sequences"
# Use pg_get_serial_sequence() to find actual sequence names (safer than guessing).
psql_cmd << 'SQL'
DO $$
DECLARE
    tbl TEXT;
    seq TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['users', 'campaign_progress', 'game_history', 'user_game_history']
    LOOP
        seq := pg_get_serial_sequence(tbl, 'id');
        IF seq IS NOT NULL THEN
            EXECUTE format('SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I), 1))', seq, tbl);
            RAISE NOTICE 'Reset sequence % for table %', seq, tbl;
        ELSE
            RAISE NOTICE 'No sequence found for %.id (table may use IDENTITY or no auto-increment)', tbl;
        END IF;
    END LOOP;
END $$;
SQL

# ─── 5. Clean up staging tables ──────────────────────────────

log "Dropping staging tables"
psql_cmd << 'SQL'
DROP TABLE IF EXISTS _legacy_users;
DROP TABLE IF EXISTS _legacy_campaign_progress;
DROP TABLE IF EXISTS _legacy_game_history;
DROP TABLE IF EXISTS _legacy_user_game_history;
SQL

# ─── 6. Print summary ────────────────────────────────────────

log "Migration complete! Row counts:"
psql_cmd << 'SQL'
SELECT 'users' AS table_name, COUNT(*) AS rows FROM users
UNION ALL
SELECT 'campaign_progress', COUNT(*) FROM campaign_progress
UNION ALL
SELECT 'game_history', COUNT(*) FROM game_history
UNION ALL
SELECT 'user_game_history', COUNT(*) FROM user_game_history
ORDER BY table_name;
SQL

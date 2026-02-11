# Multi-Server Design

> **Note:** This document describes the abstract multi-server architecture (game routing, crash recovery, drain mode). For the current production deployment setup using Caddy + Lightsail, see [DEPLOYMENT.md](DEPLOYMENT.md). The nginx/ALB references below reflect the original design; the production implementation uses Caddy with equivalent routing.

This document describes the design for running multiple Kung Fu Chess server instances behind a load balancer, supporting rolling deploys and crash recovery with minimal game disruption.

---

## Table of Contents

1. [Current Architecture](#current-architecture)
2. [Goals & Constraints](#goals--constraints)
3. [Deployment Topology](#deployment-topology)
4. [Game Routing](#game-routing)
5. [Game State Persistence & Recovery](#game-state-persistence--recovery)
6. [Lobby System](#lobby-system)
7. [Replay System](#replay-system)
8. [Rolling Deploys](#rolling-deploys)
9. [Crash Recovery](#crash-recovery)
10. [Live Games List](#live-games-list)
11. [Campaign & Quickplay](#campaign--quickplay)
12. [Redis Key Schema](#redis-key-schema)
13. [nginx Configuration](#nginx-configuration)
14. [Deployment Script](#deployment-script)
15. [Migration Path](#migration-path)

---

## Current Architecture

Everything that matters for multi-server runs in-memory on a single process:

| Component | Storage | Multi-Server Impact |
|-----------|---------|-------------------|
| `GameService.games` | In-memory dict | Game state lives on one server only |
| `ConnectionManager.connections` | In-memory dict | WebSocket connections are process-local |
| `LobbyManager._lobbies` | In-memory dict (+ optional DB) | Lobbies invisible to other servers |
| `_game_loop_locks` | In-memory dict | Game loop coordination is process-local |
| Game loop tasks | `asyncio.Task` per game | Cannot migrate between processes |
| `active_games` table | PostgreSQL | Already cross-server (has `server_id`) |
| Replays | PostgreSQL | Already cross-server |
| Auth (JWT cookies) | Stateless | Already cross-server |

### Request Flow Today

```
Client ──POST /api/games──> Server ──creates ManagedGame in memory
Client ──WS /ws/game/{id}──> Same Server ──finds game in memory, starts loop
```

The client always talks to the same server because there's only one. With multiple servers, we need routing.

---

## Goals & Constraints

### Must Have
1. Multiple server processes on a single machine, different ports, behind nginx
2. WebSocket connections routed to the server hosting the game
3. Rolling deploys with fast forced game migration, <1s blip
4. Crash recovery: in-progress games can resume on another server
5. Lobbies visible and joinable across all servers

### Nice to Have
6. Servers on different machines (each with own nginx), behind AWS ALB
7. Horizontal scaling by adding more server processes

### Non-Goals
- Splitting a single game across multiple servers
- Real-time cross-server communication during gameplay (pub/sub for game ticks)
- Zero-downtime deploys (a brief blip is acceptable)

---

## Deployment Topology

### Single Machine (Primary Target)

```
                    ┌─────────────────┐
                    │   AWS ALB       │
                    │ (HTTPS/WSS)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     nginx       │
                    │  (reverse proxy)│
                    └──┬────┬────┬───┘
                       │    │    │
              ┌────────▼┐ ┌▼────────┐ ┌▼────────┐
              │ Server 1│ │ Server 2│ │ Server 3│
              │ :8001   │ │ :8002   │ │ :8003   │
              └────┬────┘ └────┬────┘ └────┬────┘
                   │           │           │
              ┌────▼───────────▼───────────▼────┐
              │         PostgreSQL + Redis       │
              └─────────────────────────────────┘
```

Each server has a stable `KFCHESS_SERVER_ID` (e.g., `worker1`, `worker2`, `worker3`).

### Multi-Machine Extension

Each machine runs its own nginx. The ALB routes to machines; machine nginx routes to local server processes. All coordination goes through PostgreSQL and Redis.

**Open design question**: Worker IDs (e.g., `worker1`) and the nginx `$arg_server` map are currently local to a single machine. For multi-machine, worker IDs would need to be globally unique (e.g., `m1-worker1`) and the routing layer would need to resolve them across machines (e.g., ALB sticky routing or a global nginx map). This needs further design when multi-machine becomes a priority. The single-machine design works as-is.

---

## Game Routing

### The Core Problem

A game's state lives in-memory on one server. WebSocket connections for that game must reach that server. But:
- Game creation (REST) and WebSocket connection are separate requests
- Reconnecting clients don't know which server hosts their game
- After a crash or deploy, the game may move to a different server

### Solution: Application-Level Redirect via nginx

We use **application-level redirects**: a WS connection can land on any server (via nginx round-robin). If the server doesn't own the game, it checks Redis, tells the client which server to reconnect to, and the client reconnects with a routing hint that nginx uses to proxy to the correct upstream.

#### How It Works

```
1. Client connects: wss://kfchess.com/ws/game/{game_id}?player_key=xxx
   → nginx round-robins to Server 2

2. Server 2 checks local GameService.games → not found

3. Server 2 checks Redis game:{game_id}:server → "worker1"

4. Server 2 closes WS with code 4302, reason: "worker1"

5. Client reconnects: wss://kfchess.com/ws/game/{game_id}?player_key=xxx&server=worker1
   → nginx sees server=worker1 query param, routes to Server 1

6. Server 1 has the game → accepts connection, proceeds normally
```

The client never needs to know internal server addresses - it always connects through `kfchess.com`. The `server` query parameter is an opaque routing hint that nginx resolves to the correct upstream.

#### Registration Flow

When a game is created, the server:
1. Stores the game in memory (as today)
2. Writes to Redis: `game:{game_id}:server → server_id` (with TTL)
3. Writes to `active_games` table (as today, already has `server_id`)

```python
async def register_game_routing(game_id: str, server_id: str):
    await redis.set(f"game:{game_id}:server", server_id, ex=7200)  # 2hr TTL
```

The Redis entry is refreshed periodically by the game loop and deleted when the game ends.

#### Full WebSocket Connection Flow

```
1. Client connects: WS /ws/game/{game_id}?player_key=xxx

2. Server checks local GameService.games
   → Found locally? Accept connection, proceed as today.

3. Not found locally → Check Redis for game:{game_id}:server
   → Found on another server?
     Close with code 4302, reason = target server_id.
   → Not in Redis? Check active_games table in PostgreSQL.
     → Found in DB? Attempt game recovery (see Crash Recovery).
     → Not in DB either? Close with 4004 "Game not found".
```

---

## Game State Persistence & Recovery

### The Problem

Game state is in-memory. If a server crashes or is shut down for a deploy, all games on that server are lost unless we persist state.

### Solution: Periodic State Snapshots to Redis

The game loop already runs at 30 Hz. We add a **state snapshot** at a lower frequency:

```python
SNAPSHOT_INTERVAL_TICKS = 30  # Once per second at 30 Hz

async def _run_game_loop(game_id: str) -> None:
    # ... existing loop ...
    while True:
        # ... existing tick logic ...

        # Periodic state snapshot (every ~1 second)
        if state.current_tick % SNAPSHOT_INTERVAL_TICKS == 0:
            await _snapshot_game_state(game_id, managed_game)

        # ... rest of loop ...
```

#### What Gets Snapshotted

```python
@dataclass
class GameSnapshot:
    """Serializable game state for persistence."""
    game_id: str
    state: dict           # GameState serialized to dict
    player_keys: dict     # {player_num: key}
    ai_config: dict       # {player_num: ai_type} (AI instances recreated from config)
    campaign_level_id: int | None
    campaign_user_id: int | None
    initial_board_str: str | None
    resigned_piece_ids: list[str]  # King IDs captured via resignation (4-player)
    draw_offers: set[int]          # Players who have offered a draw
    force_broadcast: bool          # Force state broadcast on next tick
    server_id: str
    snapshot_tick: int
    snapshot_time: float   # time.time()
```

**Storage**: Redis key `game:{game_id}:snapshot` (JSON string)
- TTL: 2 hours (same as stale game cleanup)
- Size: ~5-20 KB for short games, growing with `replay_moves` over time (~50 bytes/move). A 10-minute game with ~200 moves is ~15-25 KB. A 1-hour game could reach ~80-100 KB. Still well within Redis comfort.

#### GameState Serialization

`GameState` needs `to_snapshot_dict()` and `from_snapshot_dict()` methods:

```python
class GameState:
    def to_snapshot_dict(self) -> dict:
        """Serialize state for persistence."""
        return {
            "game_id": self.game_id,
            "speed": self.speed.value,
            "board_type": self.board.board_type.value,
            "board_width": self.board.width,
            "board_height": self.board.height,
            "players": {str(k): v for k, v in self.players.items()},
            "current_tick": self.current_tick,
            "status": self.status.value,
            "winner": self.winner,
            "win_reason": self.win_reason.value if self.win_reason else None,
            "ready_players": list(self.ready_players),
            "pieces": [piece.to_dict() for piece in self.board.pieces],
            "active_moves": [move.to_dict() for move in self.active_moves],
            "cooldowns": [cd.to_dict() for cd in self.cooldowns],
            "replay_moves": [m.to_dict() for m in self.replay_moves],
            "last_move_tick": self.last_move_tick,
            "last_capture_tick": self.last_capture_tick,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_snapshot_dict(cls, data: dict) -> "GameState":
        """Deserialize state from persistence."""
        # ... reconstruct full state (see game/state.py) ...
```

Note: `players` dict keys are converted to strings for JSON compatibility and back to ints on deserialization. `board_width`/`board_height` are stored explicitly for robustness (with fallback derivation from `board_type`).

AI instances are **not** serialized - only the AI config (type name, e.g. `"novice"`) is stored. On recovery, fresh AI instances are created. Since AI is already non-deterministic (noise parameter), this is transparent to the player.

#### Cost Analysis

- **Serialization**: ~0.1ms for a typical game state
- **Redis write**: ~0.2ms on localhost
- **Frequency**: Once per second per game
- **With 100 concurrent games**: 100 writes/sec to Redis, ~100-500 KB/sec bandwidth (varies with game length)
- **Acceptable**: Well within Redis capacity

---

## Lobby System

### The Problem

Lobbies are fully in-memory singletons. Two servers have two separate `LobbyManager` instances with no shared state.

### Solution: Redis-Backed State + Stateless Pub/Sub WebSockets

All lobby state moves to Redis. The existing in-memory `LobbyManager` is **replaced entirely** by a `RedisLobbyManager` with an all-async interface.

Lobby WebSocket connections become **stateless subscribers**: each server with connected lobby clients subscribes to that lobby's Redis Pub/Sub channel and forwards events to local WebSocket connections.

This means:
- **No lobby WS routing needed** - any server can handle lobby WS connections
- **No single "owner" server** for a lobby - connections can be spread across servers
- Lobby state changes (REST or WS actions) write to Redis and publish events
- All servers with subscribers receive events and broadcast to their local connections
- **No one-lobby-per-player restriction** - players can be in multiple lobbies simultaneously

#### Architecture

```
                    ┌──────────────────┐
                    │   Redis          │
                    │   - Lobby state  │
                    │   - Pub/Sub      │
                    └──┬────┬────┬────┘
                       │    │    │
         subscribe  subscribe  subscribe
                       │    │    │
              ┌────────▼┐ ┌▼────────┐ ┌▼────────┐
              │ Server 1│ │ Server 2│ │ Server 3│
              │ WS: P1  │ │ WS: P2  │ │         │
              └─────────┘ └─────────┘ └─────────┘

Player 1 on Server 1, Player 2 on Server 2.
P1 readies up → Server 1 writes to Redis, publishes event.
Server 2 receives event via pub/sub → broadcasts to P2's WS.
```

#### Redis Data Model

```
lobby:{code}              → JSON string: full lobby state
                            {settings, status, host_slot, players, ...}
lobby:{code}:keys         → Hash: {slot → player_key}
lobby:public_index        → Sorted Set: {code → created_at_timestamp}
```

#### Pub/Sub Channel

```
Channel: lobby_events:{code}
Messages:
  {"type": "player_joined", "slot": 2, "player": {...}, "lobby": {...}}
  {"type": "player_left", "slot": 2, "reason": "left"}
  {"type": "player_ready", "slot": 1, "ready": true}
  {"type": "player_disconnected", "slot": 2}
  {"type": "player_reconnected", "slot": 2, "player": {...}}
  {"type": "settings_updated", "settings": {...}}
  {"type": "host_changed", "newHostSlot": 2}
  {"type": "game_starting", "gameId": "...", "playerKeys": {slot: key}}
  {"type": "game_ended", "winner": 1, "reason": "king_captured"}
  {"type": "lobby_state", "lobby": {...}}  // Full state sync
```

The `game_starting` message includes all player keys. Each server filters to only send a player their own key. This is safe because pub/sub is server-to-server (never exposed to clients).

#### WebSocket Handler

The lobby WebSocket handler becomes a thin pub/sub relay:

```python
async def handle_lobby_websocket(websocket, code, player_key):
    # 1. Validate player_key against Redis
    slot = await redis_lobby.validate_key(code, player_key)
    if slot is None:
        await websocket.close(code=4001)
        return

    # 2. Mark player connected in Redis, publish reconnection event
    await redis_lobby.set_connected(code, slot, True)

    # 3. Accept WS, send current lobby state from Redis
    await websocket.accept()
    lobby = await redis_lobby.get_lobby(code)
    await websocket.send_json({"type": "lobby_state", "lobby": lobby})

    # 4. Subscribe to lobby events channel
    # Note: at scale, optimize to one subscription per lobby per server
    # (shared across all local connections) instead of per-connection.
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"lobby_events:{code}")

    # 5. Run two concurrent tasks:
    #    a) Forward pub/sub events to WebSocket
    #    b) Handle incoming WS messages (ready, start, etc.)
    async with asyncio.TaskGroup() as tg:
        tg.create_task(_relay_pubsub_to_ws(pubsub, websocket))
        tg.create_task(_handle_ws_messages(websocket, code, slot))

    # 6. On disconnect: mark disconnected, unsubscribe
    await redis_lobby.set_connected(code, slot, False)
    await pubsub.unsubscribe(f"lobby_events:{code}")
```

#### RedisLobbyManager

Replaces the current in-memory `LobbyManager` entirely. All operations are async:

```python
class RedisLobbyManager:
    """Lobby manager backed by Redis. Replaces in-memory LobbyManager."""

    async def create_lobby(self, ...) -> tuple[dict, str]:
        # Atomic write to Redis (MULTI/EXEC or Lua script)
        # Add to lobby:public_index if public
        # Publish "lobby_state" event
        ...

    async def join_lobby(self, code, ...) -> tuple[dict, str, int]:
        # Atomic read-modify-write in Redis
        # Publish "player_joined" event
        ...

    async def get_lobby(self, code) -> dict | None:
        # Read lobby:{code} from Redis
        ...

    async def get_public_lobbies(self, ...) -> list[dict]:
        # Read from lobby:public_index sorted set
        # Fetch each lobby's state
        ...

    async def set_ready(self, code, player_key, ready) -> dict:
        # Update player ready state in Redis
        # Publish "player_ready" event
        ...

    async def start_game(self, code, host_key) -> tuple[str, dict[int, str]]:
        # Validate all ready, transition to IN_GAME
        # Generate game player keys
        # Publish "game_starting" event with all player keys
        ...

    # ... etc for all lobby operations
```

#### Lobby → Game Transition

When the host starts a game via WebSocket:

1. Server validates all players ready (from Redis state)
2. Server creates the game locally via `GameService.create_lobby_game()`
3. Server registers game routing in Redis (`game:{id}:server`)
4. Server publishes `game_starting` event with game_id and all player keys
5. Each server with lobby WS connections receives the event and sends `game_starting` to its local players (each player gets only their own player_key)
6. Players open game WebSocket connections (routed to the game's server via redirect)

The game is always created on the server where the host's WS connection lives, since the host triggers `start_game`. This naturally distributes games across servers.

#### Lobby Cleanup

Disconnected player cleanup uses timestamps in the lobby state:
- When a player disconnects, `disconnected_at` is set in Redis
- On any lobby access (REST or WS message), check for expired disconnections (>30s)
- Lobbies with no human players and status != IN_GAME are deleted
- Stale lobbies cleaned up on server startup (scan `lobby:public_index`)

---

## Replay System

Replays are already database-backed and mostly stateless. The WebSocket playback session (`ReplaySession`) is in-memory but doesn't need cross-server coordination.

### Reconnection

If a replay WS disconnects:
1. Client reconnects (possibly to a different server)
2. Client sends `{"type": "resume", "tick": N, "was_playing": true}`
3. New server loads replay from DB, seeks to tick N, resumes playback

This is already described in the TODO comments in `replay_handler.py` and `replay/session.py`. No Redis needed - the seek cost (O(n) in ticks) is acceptable since replays are short.

---

## Rolling Deploys

Deploys should be fast - immediately force-migrate all games rather than waiting.

### Deploy Sequence

```
1. Deploy signal received (SIGTERM)

2. Server enters DRAINING state:
   a. Health check returns unhealthy → nginx stops sending new requests
   b. Stop accepting new game creation (return 503)

3. Force-migrate all active games (immediately, don't wait):
   a. For each running game:
      - Write final snapshot to Redis synchronously (no data loss)
      - Stop heartbeat (let it expire, making this server look "dead")
      - Close all game WS connections with code 4301 ("server shutting down")
      - Leave game:{id}:server pointing to this server (NOT deleted)
      - Clients reconnect → new server sees stale routing, checks heartbeat,
        claims via CAS (same as crash recovery)

4. Close all lobby WS connections:
   a. Mark all locally-connected lobby players as disconnected in Redis
   b. Close connections (clients reconnect to any server via round-robin)

5. Shutdown

Note: deploy and crash recovery use the **same claim path**. The only difference is that deploy writes a fresh snapshot first (zero data loss), while a crash may have a snapshot up to 1 second stale. The `active_games` table entries are cleaned up by the claiming server as part of the recovery flow (step 8).
```

### Client-Side Handling

```typescript
// In GameWebSocketClient
private handleClose(event: CloseEvent): void {
    if (event.code === 4301) {
        // Server shutting down - reconnect with small random jitter
        // to avoid thundering herd when many clients reconnect at once
        this.reconnectAttempts = 0;
        setTimeout(() => this.connect(), Math.random() * 500);
        return;
    }
    if (event.code === 4302) {
        // Redirect to specific server
        const serverId = event.reason;
        this.connectWithServerHint(serverId);
        return;
    }
    // ... existing reconnect logic with backoff ...
}

private connectWithServerHint(serverId: string): void {
    // Add server= query param so nginx routes correctly
    const url = new URL(this.wsUrl);
    url.searchParams.set('server', serverId);
    this.ws = new WebSocket(url.toString());
    // ...
}
```

### Disruption Budget

- **Planned deploy**: Zero data loss (final snapshot written synchronously before closing connections)
- **Reconnection time**: ~200-500ms (WS close + reconnect + snapshot restore)
- **Total blip**: ~500ms

---

## Crash Recovery

### Detection

Each server writes a heartbeat to Redis every second:

```
server:{server_id}:heartbeat → timestamp    TTL: 5s
```

If a server's heartbeat expires, it's considered dead. Crash detection happens in two ways:
1. **Client reconnection**: client's WS drops, it reconnects to any server
2. **Other servers**: can check heartbeat when they see a game routed to a dead server

**Trade-off**: A 5s TTL means a severely overloaded (but alive) server could be falsely declared dead. The Lua CAS claim (below) limits the blast radius: only one server can claim, and if the "dead" server is actually alive, it will notice its games were claimed (its game loop will find the routing key changed) and can stop gracefully. For a game server, this brief confusion is acceptable - no financial transactions are at stake.

### Recovery Flow

When a client reconnects after a crash (or deploy):

```
1. Client WS reconnects (any server, via nginx round-robin)
2. Server checks local games → not found
3. Server checks Redis game:{id}:server → "worker2" (the dead/draining server)
4. Server checks Redis server:worker2:heartbeat → expired/missing
5. Server atomically claims game via Lua compare-and-swap:
     if GET game:{id}:server == "worker2" then SET game:{id}:server "worker1"
   If claim fails (another server already claimed it), redirect to winner.
6. Server loads game:{id}:snapshot from Redis
7. Server restores game state, recreates AI instances, starts game loop
8. Server updates active_games table with new server_id
9. Client receives state update, game continues
```

The Lua CAS script ensures only one server can claim a game. Two servers racing to claim will both check the current value, but only the first `SET` matches - the second sees the value has already changed and fails. The loser redirects to the winner.

```lua
-- KEYS[1] = game:{id}:server
-- ARGV[1] = expected current owner (dead server)
-- ARGV[2] = new owner (claiming server)
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[2])
    return 1
else
    return 0
end
```

### Data Loss on Crash

- **Worst case**: Up to 1 second of game state (last snapshot to crash)
- **Effect**: Pieces may "jump back" slightly, players may need to re-issue moves
- **Replay**: Last ~30 ticks of replay data not recorded
- **Ratings**: Not affected (ratings only update on game completion)
- **Acceptable**: Yes - with 10s cooldowns, losing 1s of state is minor

### Countdown Phase

If a recovered game is at tick 0, the countdown replays when the game loop restarts. This is acceptable — the countdown is brief (3 seconds) and re-establishes client synchronization after reconnection. Snapshots fire at tick 0 to ensure games that crash during or just after countdown are recoverable.

### Unrecoverable Scenarios

If Redis itself crashes (losing snapshots), games in progress are lost. Players see an error and the game does not count for ratings.

---

## Live Games List

### Current Behavior

- Games register in `active_games` with `server_id` and `started_at` on creation
- Games deregister on completion
- `GET /api/games/live` queries the table, currently enriches with in-memory tick count

### Multi-Server Change

Instead of enriching with tick count (which only works for games on the responding server), use the `started_at` timestamp from PostgreSQL and display relative time in the UI (e.g., "2 minutes ago", "30 seconds ago").

This is simpler, works across servers with no additional infrastructure, and provides a good enough user experience for the live games list.

---

## Campaign & Quickplay

Both create games via REST then connect via WebSocket.

### Current Flow

```
POST /api/games         → creates game on this server, returns game_id + player_key
WS /ws/game/{game_id}  → connects to this server (same server, so game is found)
```

### Multi-Server Flow

```
POST /api/games         → creates game on this server, returns game_id + player_key
                          Also writes game:{id}:server to Redis
WS /ws/game/{game_id}  → any server via round-robin
                          If wrong server → redirect to correct one (one extra round-trip)
```

Since the REST response includes the `game_id`, and the Redis routing entry is written during creation, the WebSocket connection will be correctly routed on the first or second attempt. The client never needs to know about the server topology.

Game is always created on the server that handles the REST request. The load balancer distributes requests roughly evenly, so game distribution is roughly even across servers.

---

## Redis Key Schema

All Redis keys used by the multi-server system:

```
# Game routing & state
game:{game_id}:server       → String: "worker1"             TTL: 2h (refreshed by game loop)
game:{game_id}:snapshot      → String: JSON game snapshot    TTL: 2h (refreshed by game loop)

# Lobby state
lobby:{code}                 → String: JSON lobby state      TTL: 24h
lobby:{code}:keys            → Hash: {slot → player_key}     TTL: 24h
lobby:public_index           → Sorted Set: {code → timestamp} (no TTL, lazy cleanup: stale entries removed when lobby key is found missing during reads)
lobby:next_id                → Counter (INCR for sequential lobby IDs, no TTL)
lobby:game:{game_id}         → String: lobby_code            TTL: 2h (maps game back to its lobby)

# Lobby pub/sub
lobby_events:{code}          → Pub/Sub channel (no storage)

# Server heartbeat
server:{server_id}:heartbeat → String: timestamp             TTL: 5s (refreshed every 1s)
server:{server_id}:addr      → String: "127.0.0.1:8001"     TTL: 10s (refreshed every 5s)
```

---

## nginx Configuration

Full production nginx config for `kfchess.com`. SSL is terminated at the ALB, so nginx handles plain HTTP/WS from the ALB.

### `/etc/nginx/conf.d/kfchess.conf`

```nginx
# ─── Upstreams ───────────────────────────────────────────────

upstream kfchess_default {
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
    server 127.0.0.1:8003;
}

# ─── Server routing map ─────────────────────────────────────
# Maps the ?server= query parameter to specific upstream addresses.
# Used for game WebSocket routing (redirect-based sticky sessions).
# Update this map when adding/removing server processes.

map $arg_server $kfchess_game_target {
    default   "";
    worker1   127.0.0.1:8001;
    worker2   127.0.0.1:8002;
    worker3   127.0.0.1:8003;
}

# ─── Connection upgrade map ─────────────────────────────────

map $http_upgrade $connection_upgrade {
    default upgrade;
    ""      close;
}

# ─── Server block ───────────────────────────────────────────

server {
    listen 80;
    server_name kfchess.com;

    # ── Health check (for ALB) ───────────────────────────────
    location = /nginx-health {
        return 200 "ok";
        add_header Content-Type text/plain;
    }

    # ── Static frontend assets ───────────────────────────────
    location / {
        root /var/www/kfchess/client/dist;
        try_files $uri $uri/ /index.html;

        # Cache static assets aggressively
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # ── API (round-robin to any server) ──────────────────────
    location /api/ {
        proxy_pass http://kfchess_default;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # ── Game WebSocket (routed by server hint) ───────────────
    # If ?server=workerN is present, route to that specific server.
    # Otherwise, round-robin to any server (which may redirect).
    location /ws/game/ {
        # Use game target if server hint is present, otherwise default upstream
        set $game_upstream kfchess_default;
        if ($kfchess_game_target != "") {
            set $game_upstream $kfchess_game_target;
        }

        proxy_pass http://$game_upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # WebSocket timeouts
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # ── Lobby WebSocket (round-robin, no routing needed) ─────
    location /ws/lobby/ {
        proxy_pass http://kfchess_default;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # ── Replay WebSocket (round-robin, no routing needed) ────
    location /ws/replay/ {
        proxy_pass http://kfchess_default;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

### Notes

- **SSL termination**: Handled by the ALB. nginx receives plain HTTP on port 80.
- **Static files**: Served directly by nginx from the built frontend. API and WS requests are proxied.
- **Lobby/Replay WS**: Round-robin to any server. No routing hint needed because lobby WS uses pub/sub (any server works) and replay sessions are stateless.
- **Game WS**: Uses `$arg_server` to route to specific servers when the client provides a `?server=workerN` hint. Falls back to round-robin if no hint is present.
- **Health checks**: The ALB checks `/nginx-health` on nginx (always 200 if nginx is up). Individual server processes expose `/health` which returns unhealthy during drain - but nginx doesn't use this for routing decisions. Server `/health` is used by the deploy script to confirm a worker is ready after restart.

---

## Deployment Script

Script to perform a rolling deploy across all server processes. Each server is stopped, updated, and restarted one at a time.

### `scripts/deploy.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────
WORKERS=(worker1 worker2 worker3)
PORTS=(8001 8002 8003)
APP_DIR="/var/www/kfchess"
SERVER_DIR="$APP_DIR/server"
VENV_CMD="uv run"
DEPLOY_PAUSE=2  # seconds between workers

# ─── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
err() { echo -e "${RED}[deploy]${NC} $1" >&2; }

# ─── Pre-deploy ──────────────────────────────────────────────
log "Starting rolling deploy..."

# Pull latest code
cd "$APP_DIR"
git pull origin main

# Build frontend
log "Building frontend..."
cd "$APP_DIR/client"
npm ci --production
npm run build

# Copy built frontend to nginx serving directory
cp -r dist/* /var/www/kfchess/client/dist/

# Install/update backend dependencies
cd "$SERVER_DIR"
uv sync

# Run database migrations
log "Running database migrations..."
$VENV_CMD alembic upgrade head

# ─── Rolling restart ─────────────────────────────────────────
for i in "${!WORKERS[@]}"; do
    worker="${WORKERS[$i]}"
    port="${PORTS[$i]}"

    log "Deploying $worker (port $port)..."

    # Send SIGTERM to the worker process (triggers graceful drain)
    # The server writes final snapshots and closes connections before exiting
    if systemctl is-active --quiet "kfchess@$worker"; then
        log "  Stopping $worker (graceful drain)..."
        systemctl stop "kfchess@$worker"

        # Wait for process to fully exit
        sleep 1
    else
        warn "  $worker was not running"
    fi

    # Start the worker with new code
    log "  Starting $worker..."
    systemctl start "kfchess@$worker"

    # Wait for health check
    for attempt in $(seq 1 10); do
        if curl -sf "http://127.0.0.1:$port/health" > /dev/null 2>&1; then
            log "  $worker is healthy"
            break
        fi
        if [ "$attempt" -eq 10 ]; then
            err "  $worker failed to start! Aborting deploy."
            exit 1
        fi
        sleep 1
    done

    # Pause before next worker to let games migrate
    if [ "$i" -lt $((${#WORKERS[@]} - 1)) ]; then
        log "  Waiting ${DEPLOY_PAUSE}s before next worker..."
        sleep "$DEPLOY_PAUSE"
    fi
done

log "Deploy complete! All workers running."
```

### systemd Unit Template

### `/etc/systemd/system/kfchess@.service`

```ini
[Unit]
Description=Kung Fu Chess Server (%i)
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=exec
User=kfchess
Group=kfchess
WorkingDirectory=/var/www/kfchess/server
Environment=KFCHESS_SERVER_ID=%i
EnvironmentFile=/var/www/kfchess/server/.env

# Uses wrapper script to derive port from worker number (worker1→8001, etc.)
ExecStart=/usr/local/bin/kfchess-worker

# Graceful shutdown: SIGTERM triggers drain, then SIGKILL after timeout
KillSignal=SIGTERM
TimeoutStopSec=15
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The wrapper script derives the port from the worker number:

```bash
# /usr/local/bin/kfchess-worker
#!/bin/bash
# Derive port from worker number: worker1→8001, worker2→8002, etc.
NUM="${KFCHESS_SERVER_ID//[!0-9]/}"
PORT=$((8000 + NUM))
exec uvicorn kfchess.main:app --host 127.0.0.1 --port "$PORT" --workers 1 --log-level info
```

---

## Migration Path

The migration from single-server to multi-server can be done incrementally:

### Phase 1: State Serialization (no behavior change) ✅ DONE
- `to_snapshot_dict()` / `from_snapshot_dict()` on `GameState` (`game/state.py`)
- `to_dict()` / `from_dict()` on `Piece`, `Move`, `Cooldown`, `ReplayMove` (`game/pieces.py`, `game/moves.py`, `game/state.py`)
- `GameSnapshot` dataclass with full `ManagedGame` metadata (`game/snapshot.py`)
- 43 round-trip tests covering individual types, full game states, JSON round-trips, 4-player with eliminations, and end-to-end pipeline (`tests/unit/game/test_snapshot.py`)
- **Zero risk**: No behavior changes, just new code paths

### Phase 2: Redis Integration (single server, no routing) ✅ DONE
- Async Redis client singleton (`redis/client.py`) using `settings.redis_url`
- Snapshot store (`redis/snapshot_store.py`): save/load/delete/list with `game:{id}:snapshot` keys (2h TTL); corrupted data handled gracefully (returns None)
- Server heartbeat (`redis/heartbeat.py`): `server:{id}:heartbeat` key (5s TTL, refreshed every 1s); `is_server_alive()` check for liveness
- Periodic snapshots in game loop: every 30 ticks (1/second at 30 Hz), including tick 0 for early crash coverage
- Startup restoration: scans all snapshots, claims games whose owning server has no live heartbeat (forward-compatible with multi-server failover); skips finished games; re-registers restored games in `active_games` table. Phase 5 added atomic CAS (`claim_game_routing()`) on `game:{id}:server` to prevent races during simultaneous multi-server restarts.
- `ManagedGame.ai_config: dict[int, str]` stores AI type names at creation time; `restore_game()` uses it to recreate AI instances via `_create_ai()`
- 74 tests (`tests/unit/redis/`, `tests/unit/test_game_restore.py`, `tests/unit/test_startup_restore.py`, `tests/unit/ws/test_handler_snapshot.py`)
- **Low risk**: Single server, Redis adds persistence but doesn't change behavior

### Phase 3: Game Routing (multi-server games) ✅ DONE
- Redis routing module (`redis/routing.py`): `game:{id}:server` key CRUD with 2h TTL
- Routing key registered synchronously (awaited) at all 3 game creation endpoints (quickplay, campaign, lobby) to guarantee the key exists before the client's WebSocket connection arrives; fire-and-forget used only for restored games on startup
- Game loop refreshes routing key alongside snapshots (same fire-and-forget task); deletes on game finish (both paths)
- WebSocket redirect: if game not in local memory, checks Redis `game:{id}:server` — redirects to other server with close code 4302 (reason = server_id); stale self-routing falls through to 4004
- Client handles close code 4301 (server shutdown: reconnect with jitter, no routing hint) and 4302 (redirect: reconnect immediately with `?server=` param, one-shot)
- nginx config (`deploy/nginx/kfchess.conf`): `$arg_server` map routes `?server=workerN` to correct upstream
- 30 new tests (11 Redis routing CRUD, 7 WS redirect logic, 12 client close code handling)
- **Medium risk**: Routing errors could cause extra round-trips but are self-correcting

### Phase 4: Lobby Migration to Redis ✅ DONE
- `RedisLobbyManager` (`redis/lobby_store.py`): all lobby operations backed by Redis with WATCH/MULTI/EXEC for atomic read-modify-write; max 3 retries on WatchError
- Lobby model serialization (`lobby/models.py`): `to_redis_dict()` / `from_redis_dict()` on `Lobby`, `LobbyPlayer`, `LobbySettings` with `player_id` field for game creation
- Singleton swap (`lobby/manager.py`): removed 1100-line `LobbyManager` class; `get_lobby_manager()` returns `RedisLobbyManager`; kept `LobbyError`, code/key generators, constants
- REST endpoints (`api/lobbies.py`): async-ified all calls to manager (method signatures unchanged)
- WS handler rewrite (`ws/lobby_handler.py`): pub/sub relay architecture — each connection runs two concurrent tasks via `asyncio.TaskGroup` (pub/sub relay + WS message handler); events published to `lobby_events:{code}` channel; `game_starting` published by WS handler after game creation + routing registration (ensures game exists before clients connect); direct error responses to originating WebSocket (not via pub/sub)
- Removed one-lobby-per-player restriction (disconnected-player cleanup handles stale memberships)
- Stale lobby cleanup on startup via `cleanup_stale_lobbies()`
- 68 tests in `tests/unit/redis/test_lobby_store.py` (CRUD, pub/sub events, WatchError retry, stale cleanup, ranked validation, corrupted data)
- 14 tests in `tests/unit/redis/test_lobby_serialization.py` (round-trip for all model types)
- 33 tests in `tests/unit/test_lobby_websocket.py` (WS operations, disconnect/reconnect, AI management, pub/sub relay)
- 29 tests in `tests/unit/test_api_lobbies.py` (REST endpoints with fakeredis)
- **Higher risk (mitigated)**: Comprehensive test coverage including WatchError retry, pub/sub delivery, and disconnect/reconnect flows

### Phase 5: Deploy & Recovery ✅
- **Drain mode**: `drain.py` module with `is_draining()`/`set_draining()` flag; SIGTERM handler wraps uvicorn's handler to set drain flag before lifespan shutdown
- **Health check 503**: `GET /health` returns 503 when draining (nginx stops routing new traffic)
- **Drain guards**: Game creation (`POST /api/games`, `POST /api/campaign/levels/.../start`) returns 503; lobby `start_game` WS message returns `server_draining` error
- **Drain shutdown sequence**: Save final snapshots synchronously for all active games → stop heartbeat → close all game WS (code 4301) → close all lobby WS (code 4301) → leave routing keys intact for crash recovery
- **Lua CAS claiming**: `claim_game_routing()` in `redis/routing.py` uses Lua script for atomic compare-and-swap on routing keys (prevents race conditions during multi-server restarts)
- **Startup restore with CAS**: Scans orphaned snapshots, uses `claim_game_routing()` to atomically claim from dead servers before restoring
- **On-demand crash recovery**: `handle_websocket()` detects dead server via heartbeat check → CAS claims game → loads snapshot → restores game in-memory → continues with normal join flow; CAS failure redirects to winner via 4302; orphaned routing key cleaned up on restore failure
- **Split-brain protection**: `_check_routing_ownership()` in game loop checks routing key every 90 ticks (~3s at 30 Hz); if another server has claimed the game, removes from local state and stops the loop; on Redis failure, continues running (avoids compounding transient issues)
- **Synchronous routing registration**: `register_routing()` in `redis/routing.py` is awaited in all game creation endpoints (quickplay, campaign, lobby) to guarantee the routing key exists before the game_id is returned to the client
- **Lobby WS registry**: Module-level `_active_lobby_websockets` set tracks connections; `close_all_lobby_websockets()` for drain shutdown
- **ConnectionManager.close_all()**: Closes all game WS connections with configurable code/reason
- **Files**: `drain.py` (new), `redis/routing.py`, `main.py`, `ws/handler.py`, `ws/lobby_handler.py`, `api/games.py`, `api/campaign.py`, `services/game_registry.py`
- **Unit tests**: 42 tests across 8 test files (drain flag, CAS routing, close_all, lobby WS registry, drain mode guards, drain shutdown sequence, startup restore with CAS, on-demand crash recovery)
- **Integration tests**: 18 tests in `tests/integration/test_multi_server.py` (snapshot round-trip, drain shutdown, crash recovery, startup restore, concurrent CAS, full failover cycle, split-brain protection, restore failure cleanup)

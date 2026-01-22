# Replay System Design

This document describes the design for replay recording, storage, and playback in Kung Fu Chess.

---

## Table of Contents

1. [Overview](#overview)
2. [Goals](#goals)
3. [Architecture](#architecture)
4. [Data Model](#data-model)
5. [WebSocket Protocol](#websocket-protocol)
6. [Backend Implementation](#backend-implementation)
7. [Frontend Implementation](#frontend-implementation)
8. [Implementation Plan](#implementation-plan)

---

## Overview

The replay system allows players to:
- **Record**: Automatically capture all moves during a game
- **Store**: Save completed games for later viewing
- **Playback**: Watch replays with play/pause and seeking controls

**Key Design Decision**: The server runs the replay simulation and streams state updates to the client via WebSocket—exactly like spectating a live game. The client has **no game engine logic**; it just renders what the server sends.

---

## Goals

1. **No client-side game logic**: Client only renders; server simulates
2. **Reuse existing infrastructure**: Same WebSocket protocol and rendering as live games
3. **Simple client implementation**: Replay viewer is nearly identical to spectator mode
4. **Backwards compatible**: Support loading replays from the original Kung Fu Chess format
5. **Efficient storage**: Store only moves, not full state at each tick

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLIENT                                │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Replay Page │───▶│ Replay Store │───▶│ Game Renderer    │   │
│  │ (controls)  │    │ (state only) │    │ (existing)       │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│         │                   ▲                                   │
│         │ WebSocket         │ state updates                     │
│         ▼                   │                                   │
└─────────┼───────────────────┼───────────────────────────────────┘
          │                   │
          ▼                   │
┌─────────────────────────────────────────────────────────────────┐
│                           SERVER                                │
│  ┌─────────────────┐    ┌──────────────────┐                   │
│  │ Replay WS       │───▶│ ReplaySession    │                   │
│  │ Handler         │    │ (runs simulation)│                   │
│  └─────────────────┘    └──────────────────┘                   │
│                                │                                │
│                                ▼                                │
│                         ┌──────────────┐                       │
│                         │ ReplayEngine │                       │
│                         │ (tick-by-tick│                       │
│                         │  simulation) │                       │
│                         └──────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

**Flow:**
1. Client connects to `/ws/replay/{game_id}`
2. Server loads replay from database
3. Server creates a `ReplaySession` that runs the `ReplayEngine`
4. Client sends playback commands: `play`, `pause`, `seek`
5. Server streams `state_update` messages (same format as live games)
6. Client renders using existing game components

---

## Data Model

### Replay Storage (Database)

```python
# server/src/kfchess/db/models.py

class GameReplay(Base):
    __tablename__ = "game_replays"

    id = Column(String, primary_key=True)  # Same as game_id
    speed = Column(String, nullable=False)
    board_type = Column(String, nullable=False)
    players = Column(JSON, nullable=False)
    moves = Column(JSON, nullable=False)
    total_ticks = Column(Integer, nullable=False)
    winner = Column(Integer, nullable=True)
    win_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
```

### Replay Data Structure

```python
# server/src/kfchess/game/replay.py

@dataclass
class ReplayMove:
    """A single move in a replay."""
    tick: int
    piece_id: str
    to_row: int
    to_col: int
    player: int

@dataclass
class Replay:
    """Complete replay data for a game."""
    version: int
    speed: Speed
    board_type: BoardType
    players: dict[int, str]
    moves: list[ReplayMove]
    total_ticks: int
    winner: int | None
    win_reason: str | None
    created_at: datetime | None
```

### Backwards Compatibility

The original replay format uses camelCase and different field names:

```json
{
  "speed": "standard",
  "players": {"1": "player1", "2": "player2"},
  "moves": [
    {"pieceId": "P:1:6:4", "player": 1, "row": 4, "col": 4, "tick": 5}
  ],
  "ticks": 1500
}
```

The `Replay.from_dict()` method detects and converts v1 format automatically.

---

## WebSocket Protocol

### Connection

```
WebSocket: /ws/replay/{game_id}
```

### Client → Server Messages

```typescript
// Start/resume playback
{ "type": "play" }

// Pause playback
{ "type": "pause" }

// Seek to specific tick
{ "type": "seek", "tick": 500 }
```

### Server → Client Messages

Uses the **same message types as live games**:

```typescript
// Replay metadata (sent on connect)
{
  "type": "replay_info",
  "game_id": "ABC123",
  "speed": "standard",
  "board_type": "standard",
  "players": { "1": "player1", "2": "player2" },
  "total_ticks": 1500,
  "winner": 1,
  "win_reason": "king_captured"
}

// State update (same as live game)
{
  "type": "state_update",
  "tick": 100,
  "pieces": [...],
  "active_moves": [...],
  "cooldowns": [...]
}

// Playback status
{
  "type": "playback_status",
  "is_playing": true,
  "current_tick": 100,
  "total_ticks": 1500
}

// Game over (when replay reaches end)
{
  "type": "game_over",
  "winner": 1,
  "reason": "king_captured"
}

// Error
{
  "type": "error",
  "message": "Replay not found"
}
```

---

## Backend Implementation

### ReplaySession

Manages playback state for a single replay viewer:

```python
# server/src/kfchess/replay/session.py

class ReplaySession:
    """Manages replay playback for a single client."""

    def __init__(self, replay: Replay, websocket: WebSocket):
        self.replay = replay
        self.websocket = websocket
        self.engine = ReplayEngine(replay)
        self.current_tick = 0
        self.is_playing = False
        self._playback_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Initialize session and send replay info."""
        await self._send_replay_info()
        await self._send_state_at_tick(0)

    async def handle_message(self, message: dict) -> None:
        """Handle incoming control message."""
        msg_type = message.get("type")

        if msg_type == "play":
            await self.play()
        elif msg_type == "pause":
            self.pause()
        elif msg_type == "seek":
            tick = message.get("tick", 0)
            await self.seek(tick)

    async def play(self) -> None:
        """Start or resume playback."""
        if self.is_playing:
            return

        self.is_playing = True
        await self._send_playback_status()
        self._playback_task = asyncio.create_task(self._playback_loop())

    def pause(self) -> None:
        """Pause playback."""
        self.is_playing = False
        if self._playback_task:
            self._playback_task.cancel()
            self._playback_task = None

    async def seek(self, tick: int) -> None:
        """Jump to a specific tick."""
        was_playing = self.is_playing
        self.pause()

        self.current_tick = max(0, min(tick, self.replay.total_ticks))
        await self._send_state_at_tick(self.current_tick)
        await self._send_playback_status()

        if was_playing and self.current_tick < self.replay.total_ticks:
            await self.play()

    async def _playback_loop(self) -> None:
        """Main playback loop - advances tick and sends state."""
        config = SPEED_CONFIGS[self.replay.speed]
        tick_interval = config.tick_period_ms / 1000.0

        while self.is_playing and self.current_tick < self.replay.total_ticks:
            await asyncio.sleep(tick_interval)

            if not self.is_playing:
                break

            self.current_tick += 1
            await self._send_state_at_tick(self.current_tick)

            if self.current_tick >= self.replay.total_ticks:
                self.is_playing = False
                await self._send_game_over()

        await self._send_playback_status()

    async def _send_state_at_tick(self, tick: int) -> None:
        """Compute and send state at the given tick."""
        state = self.engine.get_state_at_tick(tick)
        message = format_state_update(state)  # Same format as live games
        await self.websocket.send_json(message)

    async def _send_replay_info(self) -> None:
        """Send replay metadata."""
        await self.websocket.send_json({
            "type": "replay_info",
            "game_id": self.replay.game_id,
            "speed": self.replay.speed.value,
            "board_type": self.replay.board_type.value,
            "players": self.replay.players,
            "total_ticks": self.replay.total_ticks,
            "winner": self.replay.winner,
            "win_reason": self.replay.win_reason,
        })

    async def _send_playback_status(self) -> None:
        """Send current playback status."""
        await self.websocket.send_json({
            "type": "playback_status",
            "is_playing": self.is_playing,
            "current_tick": self.current_tick,
            "total_ticks": self.replay.total_ticks,
        })

    async def _send_game_over(self) -> None:
        """Send game over message."""
        await self.websocket.send_json({
            "type": "game_over",
            "winner": self.replay.winner,
            "reason": self.replay.win_reason,
        })
```

### ReplayEngine (Existing)

The existing `ReplayEngine` computes state at any tick:

```python
# server/src/kfchess/game/replay.py

class ReplayEngine:
    """Engine for replaying games tick-by-tick."""

    def __init__(self, replay: Replay):
        self.replay = replay
        # Pre-index moves by tick for fast lookup
        self._moves_by_tick: dict[int, list[ReplayMove]] = defaultdict(list)
        for move in replay.moves:
            self._moves_by_tick[move.tick].append(move)

    def get_state_at_tick(self, target_tick: int) -> GameState:
        """Compute game state at a specific tick."""
        # Creates fresh game and simulates all moves up to target_tick
        state = GameEngine.create_game(...)
        while state.current_tick < target_tick:
            # Apply moves at this tick
            for move in self._moves_by_tick.get(state.current_tick, []):
                GameEngine.apply_move(state, move)
            GameEngine.tick(state)
        return state
```

### WebSocket Handler

```python
# server/src/kfchess/ws/replay_handler.py

@router.websocket("/ws/replay/{game_id}")
async def replay_websocket(websocket: WebSocket, game_id: str):
    await websocket.accept()

    # Load replay from database
    replay = await replay_repository.get_by_id(game_id)
    if replay is None:
        await websocket.send_json({"type": "error", "message": "Replay not found"})
        await websocket.close()
        return

    # Create session and start
    session = ReplaySession(replay, websocket)
    await session.start()

    try:
        while True:
            data = await websocket.receive_json()
            await session.handle_message(data)
    except WebSocketDisconnect:
        session.pause()
```

---

## Frontend Implementation

### Replay Store (Simplified)

The replay store is much simpler—it just manages WebSocket connection and renders received state:

```typescript
// client/src/stores/replay.ts

interface ReplayState {
  // Connection
  gameId: string | null;
  connectionState: ConnectionState;
  error: string | null;

  // Replay metadata
  speed: GameSpeed | null;
  boardType: BoardType | null;
  players: Record<number, string> | null;
  totalTicks: number;
  winner: number | null;
  winReason: string | null;

  // Playback state (from server)
  currentTick: number;
  isPlaying: boolean;

  // Game state (from server, same as live game)
  pieces: Piece[];
  activeMoves: ActiveMove[];
  cooldowns: Cooldown[];

  // Actions
  connect: (gameId: string) => void;
  disconnect: () => void;
  play: () => void;
  pause: () => void;
  seek: (tick: number) => void;
}
```

### Replay WebSocket Client

```typescript
// client/src/ws/replayClient.ts

export class ReplayWebSocketClient {
  private ws: WebSocket | null = null;
  private gameId: string;
  private callbacks: ReplayCallbacks;

  constructor(gameId: string, callbacks: ReplayCallbacks) {
    this.gameId = gameId;
    this.callbacks = callbacks;
  }

  connect(): void {
    this.ws = new WebSocket(`/ws/replay/${this.gameId}`);

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };

    this.ws.onclose = () => {
      this.callbacks.onConnectionChange('disconnected');
    };
  }

  private handleMessage(message: any): void {
    switch (message.type) {
      case 'replay_info':
        this.callbacks.onReplayInfo(message);
        break;
      case 'state_update':
        this.callbacks.onStateUpdate(message);
        break;
      case 'playback_status':
        this.callbacks.onPlaybackStatus(message);
        break;
      case 'game_over':
        this.callbacks.onGameOver(message);
        break;
      case 'error':
        this.callbacks.onError(message);
        break;
    }
  }

  play(): void {
    this.ws?.send(JSON.stringify({ type: 'play' }));
  }

  pause(): void {
    this.ws?.send(JSON.stringify({ type: 'pause' }));
  }

  seek(tick: number): void {
    this.ws?.send(JSON.stringify({ type: 'seek', tick }));
  }

  disconnect(): void {
    this.ws?.close();
    this.ws = null;
  }
}
```

### Replay Page Component

The replay page reuses the existing game renderer:

```typescript
// client/src/pages/Replay.tsx

export function Replay() {
  const { replayId } = useParams<{ replayId: string }>();

  // All state comes from server via WebSocket
  const pieces = useReplayStore((s) => s.pieces);
  const activeMoves = useReplayStore((s) => s.activeMoves);
  const cooldowns = useReplayStore((s) => s.cooldowns);
  const boardType = useReplayStore((s) => s.boardType);
  const currentTick = useReplayStore((s) => s.currentTick);
  const totalTicks = useReplayStore((s) => s.totalTicks);
  const isPlaying = useReplayStore((s) => s.isPlaying);

  const connect = useReplayStore((s) => s.connect);
  const disconnect = useReplayStore((s) => s.disconnect);
  const play = useReplayStore((s) => s.play);
  const pause = useReplayStore((s) => s.pause);
  const seek = useReplayStore((s) => s.seek);

  useEffect(() => {
    if (replayId) {
      connect(replayId);
    }
    return () => disconnect();
  }, [replayId]);

  return (
    <div className="replay-page">
      {/* Reuse existing game board - no changes needed */}
      <GameBoard
        boardType={boardType}
        pieces={pieces}
        activeMoves={activeMoves}
        cooldowns={cooldowns}
        readOnly={true}
      />

      {/* Simple playback controls */}
      <ReplayControls
        currentTick={currentTick}
        totalTicks={totalTicks}
        isPlaying={isPlaying}
        onPlay={play}
        onPause={pause}
        onSeek={seek}
      />
    </div>
  );
}
```

### Replay Controls Component

```typescript
// client/src/components/replay/ReplayControls.tsx

interface ReplayControlsProps {
  currentTick: number;
  totalTicks: number;
  isPlaying: boolean;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (tick: number) => void;
}

export function ReplayControls(props: ReplayControlsProps) {
  const { currentTick, totalTicks, isPlaying, onPlay, onPause, onSeek } = props;

  const progress = totalTicks > 0 ? (currentTick / totalTicks) * 100 : 0;
  const timeDisplay = formatTicksAsTime(currentTick);
  const totalTimeDisplay = formatTicksAsTime(totalTicks);

  return (
    <div className="replay-controls">
      {/* Seek slider */}
      <input
        type="range"
        min={0}
        max={totalTicks}
        value={currentTick}
        onChange={(e) => onSeek(parseInt(e.target.value))}
      />

      {/* Time display */}
      <span>{timeDisplay} / {totalTimeDisplay}</span>

      {/* Play/Pause button */}
      {isPlaying ? (
        <button onClick={onPause}>Pause</button>
      ) : (
        <button onClick={onPlay}>Play</button>
      )}
    </div>
  );
}

function formatTicksAsTime(ticks: number): string {
  const seconds = Math.floor(ticks / 10);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}
```

---

## Implementation Plan

### Phase 1: Database & Backend (COMPLETED)

1. ~~Create database model for `GameReplay`~~
2. ~~Create Alembic migration for the table~~
3. ~~Create `replay.py` module with `Replay` dataclass~~
4. ~~Create replay repository for database operations~~
5. ~~Add auto-save when games finish~~
6. ~~Add replay export endpoint (`GET /api/games/{game_id}/replay`)~~
7. ~~Add backwards compatibility for v1 replay format~~
8. ~~Write tests for replay loading/conversion/storage~~

### Phase 2: Replay WebSocket & Session (NEW)

1. **Create `ReplaySession` class** that manages playback for one client
2. **Create WebSocket handler** at `/ws/replay/{game_id}`
3. **Implement playback commands**: play, pause, seek
4. **Stream state updates** using same format as live games
5. **Write tests** for replay session

**Files to create/modify:**
- `server/src/kfchess/replay/session.py` (new)
- `server/src/kfchess/ws/replay_handler.py` (new)
- `server/src/kfchess/main.py` (add WebSocket route)
- `server/tests/unit/replay/test_session.py` (new)

### Phase 3: Frontend Replay Client (REWRITE)

1. **Delete client-side replay engine** (`replayEngine.ts`)
2. **Create `ReplayWebSocketClient`** class
3. **Simplify replay store** to just manage connection + received state
4. **Add replay types** to API types

**Files to create/modify:**
- `client/src/ws/replayClient.ts` (new)
- `client/src/stores/replay.ts` (rewrite - much simpler)
- `client/src/api/types.ts` (add replay message types)
- `client/src/game/replayEngine.ts` (DELETE)

### Phase 4: Replay Viewer UI

1. **Create Replay page** component
2. **Create ReplayControls** component (play/pause/seek only)
3. **Add route** for `/replay/:replayId`
4. **Add "Watch Replay" button** to game over screen

**Files to create/modify:**
- `client/src/pages/Replay.tsx` (new)
- `client/src/pages/Replay.css` (new)
- `client/src/components/replay/ReplayControls.tsx` (new)
- `client/src/App.tsx` (add route)

### Future Enhancements

- **Speed controls**: Allow 0.5x, 2x, 4x playback (requires server-side support)
- **Replay browser**: List and search saved replays
- **Replay sharing**: Generate shareable links
- **Export/Import**: Download/upload replay JSON files
- **Keyboard shortcuts**: Space=play/pause, arrows=seek

---

## Design Decisions

1. **Server-side simulation only**: Single source of truth, no logic duplication on client. Trade-off is ~100ms latency on seeking, which is acceptable for a replay viewer.

2. **Reuse live game protocol**: The `state_update` message format is identical to live games, so the client renderer works unchanged.

3. **No speed controls (initially)**: Simplifies implementation. Can be added later by having server adjust tick interval.

4. **WebSocket per viewer**: Each replay viewer has its own WebSocket connection and playback state. This allows multiple people to watch the same replay at different positions.

5. **Compute state on demand**: Server computes state at requested tick (O(n) from tick 0). For typical games (few thousand ticks), this is fast enough. Could add caching/keyframes later if needed.

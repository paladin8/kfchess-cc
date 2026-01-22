# Replay System Design

This document describes the design for replay recording, storage, and playback in Kung Fu Chess.

---

## Table of Contents

1. [Overview](#overview)
2. [Goals](#goals)
3. [Backwards Compatibility](#backwards-compatibility)
4. [Data Model](#data-model)
5. [Backend Implementation](#backend-implementation)
6. [Frontend Implementation](#frontend-implementation)
7. [API Endpoints](#api-endpoints)
8. [Implementation Plan](#implementation-plan)

---

## Overview

The replay system allows players to:
- **Record**: Automatically capture all moves during a game
- **Store**: Save completed games for later viewing
- **Playback**: Watch replays with play/pause and seeking controls

The replay viewer is similar to the game client but read-only, with additional playback controls.

---

## Goals

1. **Backwards compatible**: Support loading replays from the original Kung Fu Chess format
2. **Efficient storage**: Store only the minimal data needed to reconstruct gameplay
3. **Full playback fidelity**: Replays should look identical to the original game
4. **Smooth seeking**: Users can jump to any point in the game
5. **Simple implementation**: Reuse existing game rendering infrastructure

---

## Backwards Compatibility

### Original Replay Format

The original `Replay` class (from `../kfchess/lib/replay.py`) stores:

```python
class Replay:
    speed: str                    # "standard" or "lightning"
    players: dict[int, str]       # {1: "player1_name", 2: "player2_name"}
    moves: list[ReplayMove]       # List of all moves
    ticks: int                    # Total game duration in ticks

class ReplayMove:
    piece_id: str                 # e.g., "P:1:6:0"
    player: int                   # Player who made the move
    row: int                      # Destination row
    col: int                      # Destination column
    tick: int                     # Tick when move was initiated
```

JSON format (camelCase):
```json
{
  "speed": "standard",
  "players": {"1": "player1", "2": "player2"},
  "moves": [
    {"pieceId": "P:1:6:4", "player": 1, "row": 4, "col": 4, "tick": 5},
    {"pieceId": "P:2:1:4", "player": 2, "row": 3, "col": 4, "tick": 8}
  ],
  "ticks": 1500
}
```

### New Replay Format

The new format extends the original with additional metadata while maintaining compatibility:

```json
{
  "version": 2,
  "speed": "standard",
  "board_type": "standard",
  "players": {"1": "player1", "2": "player2"},
  "moves": [
    {"piece_id": "P:1:6:4", "player": 1, "to_row": 4, "to_col": 4, "tick": 5},
    {"piece_id": "P:2:1:4", "player": 2, "to_row": 3, "to_col": 4, "tick": 8}
  ],
  "total_ticks": 1500,
  "winner": 1,
  "win_reason": "king_captured",
  "created_at": "2025-01-21T12:00:00Z"
}
```

### Migration Strategy

The replay loader will detect format version and convert as needed:

```python
def load_replay(data: dict) -> Replay:
    version = data.get("version", 1)

    if version == 1:
        return convert_v1_to_v2(data)
    elif version == 2:
        return Replay.from_dict(data)
    else:
        raise ValueError(f"Unknown replay version: {version}")

def convert_v1_to_v2(data: dict) -> Replay:
    """Convert original format to new format."""
    moves = []
    for m in data["moves"]:
        moves.append(ReplayMove(
            tick=m["tick"],
            piece_id=m["pieceId"],
            to_row=m["row"],
            to_col=m["col"],
            player=m["player"],
        ))

    return Replay(
        version=2,
        speed=Speed(data["speed"]),
        board_type=BoardType.STANDARD,  # Original only supported standard
        players=data["players"],
        moves=moves,
        total_ticks=data["ticks"],
        winner=None,  # Original didn't store this
        win_reason=None,
        created_at=None,
    )
```

---

## Data Model

### Backend (Python)

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
    winner: int | None          # 0=draw, 1-4=player, None=unknown
    win_reason: str | None
    created_at: datetime | None

    @staticmethod
    def from_game_state(state: GameState) -> "Replay":
        """Create a replay from a completed game state."""
        return Replay(
            version=2,
            speed=state.speed,
            board_type=state.board.board_type,
            players=state.players,
            moves=list(state.replay_moves),
            total_ticks=state.current_tick,
            winner=state.winner,
            win_reason=None,  # TODO: track win reason
            created_at=state.finished_at,
        )

    @staticmethod
    def from_dict(data: dict) -> "Replay":
        """Load replay from dictionary (handles both v1 and v2 formats)."""
        version = data.get("version", 1)
        if version == 1:
            return _convert_v1(data)
        return _parse_v2(data)

    def to_dict(self) -> dict:
        """Serialize replay to dictionary."""
        return {
            "version": self.version,
            "speed": self.speed.value,
            "board_type": self.board_type.value,
            "players": self.players,
            "moves": [
                {
                    "tick": m.tick,
                    "piece_id": m.piece_id,
                    "to_row": m.to_row,
                    "to_col": m.to_col,
                    "player": m.player,
                }
                for m in self.moves
            ],
            "total_ticks": self.total_ticks,
            "winner": self.winner,
            "win_reason": self.win_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def get_moves_at_tick(self, tick: int) -> list[ReplayMove]:
        """Get all moves that started at a specific tick."""
        return [m for m in self.moves if m.tick == tick]

    def get_moves_in_range(self, start_tick: int, end_tick: int) -> list[ReplayMove]:
        """Get all moves in a tick range (inclusive)."""
        return [m for m in self.moves if start_tick <= m.tick <= end_tick]
```

### Frontend (TypeScript)

```typescript
// client/src/stores/replay.ts

interface ReplayMove {
  tick: number;
  pieceId: string;
  toRow: number;
  toCol: number;
  player: number;
}

interface Replay {
  version: number;
  speed: GameSpeed;
  boardType: BoardType;
  players: Record<number, string>;
  moves: ReplayMove[];
  totalTicks: number;
  winner: number | null;
  winReason: string | null;
  createdAt: string | null;
}

interface ReplayState {
  // Replay data
  replay: Replay | null;
  isLoading: boolean;
  error: string | null;

  // Playback state
  currentTick: number;
  isPlaying: boolean;
  playbackSpeed: number;  // 1.0 = normal, 2.0 = 2x, 0.5 = half speed

  // Derived game state (computed from replay + currentTick)
  pieces: Piece[];
  activeMoves: ActiveMove[];
  cooldowns: Cooldown[];

  // Actions
  loadReplay: (replayId: string) => Promise<void>;
  loadReplayFromData: (data: Replay) => void;
  play: () => void;
  pause: () => void;
  seek: (tick: number) => void;
  setPlaybackSpeed: (speed: number) => void;
  stepForward: () => void;
  stepBackward: () => void;
  reset: () => void;
}
```

---

## Backend Implementation

### Replay Playback Engine

The `ReplayEngine` simulates game state at any given tick by replaying moves from the start:

```python
# server/src/kfchess/game/replay.py

class ReplayEngine:
    """Engine for replaying games tick-by-tick."""

    def __init__(self, replay: Replay):
        self.replay = replay
        self.config = SPEED_CONFIGS[replay.speed]

        # Pre-index moves by tick for fast lookup
        self._moves_by_tick: dict[int, list[ReplayMove]] = defaultdict(list)
        for move in replay.moves:
            self._moves_by_tick[move.tick].append(move)

    def get_state_at_tick(self, target_tick: int) -> GameState:
        """
        Compute the game state at a specific tick.

        This creates a fresh game and simulates all moves up to target_tick.
        For seeking, the frontend can cache states at key intervals.
        """
        # Create initial game state
        state = GameEngine.create_game(
            speed=self.replay.speed,
            players=self.replay.players,
            board_type=self.replay.board_type,
        )
        state.status = GameStatus.PLAYING

        # Simulate all ticks up to target
        while state.current_tick < target_tick:
            # Apply any moves at this tick
            for replay_move in self._moves_by_tick.get(state.current_tick, []):
                move = GameEngine.validate_move(
                    state,
                    replay_move.player,
                    replay_move.piece_id,
                    replay_move.to_row,
                    replay_move.to_col,
                )
                if move:
                    GameEngine.apply_move(state, move)

            # Advance tick
            GameEngine.tick(state)

        return state

    def get_initial_state(self) -> GameState:
        """Get the state at tick 0."""
        return self.get_state_at_tick(0)
```

### Replay Storage

Replays are automatically saved to the database when games finish.

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
    is_public = Column(Boolean, default=True)
```

### Auto-Save on Game End

When a game finishes, the `GameService` automatically saves the replay:

```python
# server/src/kfchess/services/game_service.py

async def _on_game_finished(self, game_id: str, state: GameState) -> None:
    """Called when a game ends. Saves replay to database."""
    replay = Replay.from_game_state(state)
    await self.replay_repository.save(replay)
```

---

## Frontend Implementation

### Replay Store

The replay store manages playback state and computes derived game state:

```typescript
// client/src/stores/replay.ts

export const useReplayStore = create<ReplayState>((set, get) => ({
  // Initial state
  replay: null,
  isLoading: false,
  error: null,
  currentTick: 0,
  isPlaying: false,
  playbackSpeed: 1.0,
  pieces: [],
  activeMoves: [],
  cooldowns: [],

  loadReplay: async (replayId) => {
    set({ isLoading: true, error: null });
    try {
      const replay = await api.getReplay(replayId);
      get().loadReplayFromData(replay);
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  loadReplayFromData: (replay) => {
    // Initialize playback engine
    const engine = new ReplayPlaybackEngine(replay);
    const initialState = engine.getStateAtTick(0);

    set({
      replay,
      isLoading: false,
      currentTick: 0,
      isPlaying: false,
      pieces: initialState.pieces,
      activeMoves: [],
      cooldowns: [],
      _engine: engine,
    });
  },

  play: () => {
    const { isPlaying, replay } = get();
    if (isPlaying || !replay) return;

    set({ isPlaying: true });
    get()._startPlaybackLoop();
  },

  pause: () => {
    set({ isPlaying: false });
  },

  seek: (tick) => {
    const { replay, _engine } = get();
    if (!replay || !_engine) return;

    const clampedTick = Math.max(0, Math.min(tick, replay.totalTicks));
    const state = _engine.getStateAtTick(clampedTick);

    set({
      currentTick: clampedTick,
      pieces: state.pieces,
      activeMoves: state.activeMoves,
      cooldowns: state.cooldowns,
    });
  },

  setPlaybackSpeed: (speed) => {
    set({ playbackSpeed: speed });
  },

  stepForward: () => {
    const { currentTick, replay } = get();
    if (!replay) return;
    get().seek(Math.min(currentTick + 1, replay.totalTicks));
  },

  stepBackward: () => {
    const { currentTick } = get();
    get().seek(Math.max(currentTick - 1, 0));
  },

  _startPlaybackLoop: () => {
    const tick = () => {
      const { isPlaying, currentTick, replay, playbackSpeed } = get();
      if (!isPlaying || !replay) return;

      if (currentTick >= replay.totalTicks) {
        set({ isPlaying: false });
        return;
      }

      get().seek(currentTick + 1);

      // Schedule next tick based on speed config and playback speed
      const tickMs = SPEED_CONFIGS[replay.speed].tickPeriodMs / playbackSpeed;
      setTimeout(tick, tickMs);
    };

    // Start the loop
    const { replay, playbackSpeed } = get();
    const tickMs = SPEED_CONFIGS[replay.speed].tickPeriodMs / playbackSpeed;
    setTimeout(tick, tickMs);
  },

  reset: () => {
    set({
      replay: null,
      isLoading: false,
      error: null,
      currentTick: 0,
      isPlaying: false,
      playbackSpeed: 1.0,
      pieces: [],
      activeMoves: [],
      cooldowns: [],
    });
  },
}));
```

### Client-Side Replay Engine

The frontend simulates game state by replaying from tick 0 to the target tick. This is simple and fast enough for typical game lengths (a few thousand ticks).

```typescript
// client/src/game/replayEngine.ts

export class ReplayPlaybackEngine {
  private replay: Replay;
  private movesByTick: Map<number, ReplayMove[]>;

  constructor(replay: Replay) {
    this.replay = replay;
    this.movesByTick = new Map();

    // Index moves by tick for fast lookup
    for (const move of replay.moves) {
      const existing = this.movesByTick.get(move.tick) || [];
      existing.push(move);
      this.movesByTick.set(move.tick, existing);
    }
  }

  getStateAtTick(targetTick: number): GameStateSnapshot {
    // Always simulate from the beginning - simple and fast enough
    let state = this.createInitialState();

    for (let tick = 0; tick <= targetTick; tick++) {
      state = this.simulateTick(state, tick);
    }

    return state;
  }

  private simulateTick(state: GameStateSnapshot, tick: number): GameStateSnapshot {
    // Apply moves at this tick
    const moves = this.movesByTick.get(tick) || [];
    for (const move of moves) {
      this.applyMove(state, move);
    }

    // Update active moves progress
    this.updateActiveMoves(state, tick);

    // Update cooldowns
    this.updateCooldowns(state, tick);

    state.currentTick = tick;
    return state;
  }

  // ... helper methods for move application, collision detection, etc.
}
```

### Replay Viewer Component

The replay viewer reuses the `GameBoard` component with a custom control panel:

```typescript
// client/src/pages/Replay.tsx

export function Replay() {
  const { replayId } = useParams<{ replayId: string }>();

  const replay = useReplayStore((s) => s.replay);
  const currentTick = useReplayStore((s) => s.currentTick);
  const isPlaying = useReplayStore((s) => s.isPlaying);
  const isLoading = useReplayStore((s) => s.isLoading);
  const error = useReplayStore((s) => s.error);
  const pieces = useReplayStore((s) => s.pieces);
  const activeMoves = useReplayStore((s) => s.activeMoves);
  const cooldowns = useReplayStore((s) => s.cooldowns);
  const playbackSpeed = useReplayStore((s) => s.playbackSpeed);

  const loadReplay = useReplayStore((s) => s.loadReplay);
  const play = useReplayStore((s) => s.play);
  const pause = useReplayStore((s) => s.pause);
  const seek = useReplayStore((s) => s.seek);
  const setPlaybackSpeed = useReplayStore((s) => s.setPlaybackSpeed);
  const stepForward = useReplayStore((s) => s.stepForward);
  const stepBackward = useReplayStore((s) => s.stepBackward);

  useEffect(() => {
    if (replayId) {
      loadReplay(replayId);
    }
    return () => useReplayStore.getState().reset();
  }, [replayId, loadReplay]);

  if (isLoading) {
    return <div className="replay-loading">Loading replay...</div>;
  }

  if (error) {
    return <div className="replay-error">{error}</div>;
  }

  if (!replay) {
    return <div className="replay-error">Replay not found</div>;
  }

  return (
    <div className="replay-page">
      <div className="replay-content">
        <div className="replay-board-wrapper">
          {/* Reuse GameBoard in read-only mode */}
          <GameBoard
            boardType={replay.boardType}
            squareSize={64}
            pieces={pieces}
            activeMoves={activeMoves}
            cooldowns={cooldowns}
            readOnly={true}
          />
        </div>

        <div className="replay-sidebar">
          <ReplayInfo replay={replay} />

          <ReplayControls
            currentTick={currentTick}
            totalTicks={replay.totalTicks}
            isPlaying={isPlaying}
            playbackSpeed={playbackSpeed}
            onPlay={play}
            onPause={pause}
            onSeek={seek}
            onSpeedChange={setPlaybackSpeed}
            onStepForward={stepForward}
            onStepBackward={stepBackward}
          />
        </div>
      </div>
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
  playbackSpeed: number;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (tick: number) => void;
  onSpeedChange: (speed: number) => void;
  onStepForward: () => void;
  onStepBackward: () => void;
}

export function ReplayControls(props: ReplayControlsProps) {
  const {
    currentTick,
    totalTicks,
    isPlaying,
    playbackSpeed,
    onPlay,
    onPause,
    onSeek,
    onSpeedChange,
    onStepForward,
    onStepBackward,
  } = props;

  const progress = totalTicks > 0 ? (currentTick / totalTicks) * 100 : 0;
  const timeDisplay = formatTicksAsTime(currentTick);
  const totalTimeDisplay = formatTicksAsTime(totalTicks);

  return (
    <div className="replay-controls">
      {/* Progress bar / seek slider */}
      <div className="replay-progress">
        <input
          type="range"
          min={0}
          max={totalTicks}
          value={currentTick}
          onChange={(e) => onSeek(parseInt(e.target.value))}
          className="replay-seek-bar"
        />
        <div className="replay-time">
          {timeDisplay} / {totalTimeDisplay}
        </div>
      </div>

      {/* Playback buttons */}
      <div className="replay-buttons">
        <button onClick={onStepBackward} title="Step back">
          ⏮
        </button>

        {isPlaying ? (
          <button onClick={onPause} title="Pause">
            ⏸
          </button>
        ) : (
          <button onClick={onPlay} title="Play">
            ▶
          </button>
        )}

        <button onClick={onStepForward} title="Step forward">
          ⏭
        </button>
      </div>

      {/* Speed selector */}
      <div className="replay-speed">
        <label>Speed:</label>
        <select
          value={playbackSpeed}
          onChange={(e) => onSpeedChange(parseFloat(e.target.value))}
        >
          <option value={0.25}>0.25x</option>
          <option value={0.5}>0.5x</option>
          <option value={1}>1x</option>
          <option value={2}>2x</option>
          <option value={4}>4x</option>
        </select>
      </div>
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

## API Endpoints

### Get Replay for Completed Game

```
GET /api/games/{game_id}/replay
```

Returns the replay data for a completed game.

**Response:**
```json
{
  "version": 2,
  "speed": "standard",
  "board_type": "standard",
  "players": {"1": "player1", "2": "player2"},
  "moves": [...],
  "total_ticks": 1500,
  "winner": 1,
  "win_reason": "king_captured",
  "created_at": "2025-01-21T12:00:00Z"
}
```

**Errors:**
- `404`: Game not found
- `400`: Game not finished yet

### Get Replay State at Tick (Optional)

For server-side seeking (alternative to client-side simulation):

```
GET /api/games/{game_id}/replay/state?tick={tick}
```

Returns the computed game state at a specific tick.

**Response:**
```json
{
  "tick": 500,
  "pieces": [...],
  "active_moves": [...],
  "cooldowns": [...]
}
```

---

## Implementation Plan

### Phase 1: Database & Backend

1. **Create database model** for `GameReplay`
2. **Create Alembic migration** for the table
3. **Create `replay.py` module** with `Replay` dataclass and conversion logic
4. **Create replay repository** for database operations
5. **Add auto-save** when games finish in `GameService`
6. **Add replay export endpoint** (`GET /api/games/{game_id}/replay`)
7. **Add backwards compatibility** for v1 replay format
8. **Write tests** for replay loading/conversion/storage

**Files to create/modify:**
- `server/src/kfchess/db/models.py` (new)
- `server/src/kfchess/db/session.py` (new)
- `server/alembic/versions/001_add_game_replays.py` (new migration)
- `server/src/kfchess/game/replay.py` (new)
- `server/src/kfchess/db/repositories/replays.py` (new)
- `server/src/kfchess/services/game_service.py` (add auto-save)
- `server/src/kfchess/api/games.py` (add endpoint)
- `server/tests/unit/game/test_replay.py` (new)

### Phase 2: Frontend Replay Store

1. **Create replay store** with playback state management
2. **Create client-side replay engine** for state simulation (no caching, simulate from tick 0)
3. **Add API client method** for fetching replays

**Files to create/modify:**
- `client/src/stores/replay.ts` (new)
- `client/src/game/replayEngine.ts` (new)
- `client/src/api/client.ts` (add method)
- `client/src/api/types.ts` (add types)

### Phase 3: Replay Viewer UI

1. **Create Replay page** component
2. **Create ReplayControls** component with play/pause/seek
3. **Modify GameBoard** to support read-only mode
4. **Add route** for `/replay/:replayId`
5. **Add "Watch Replay" button** to game over modal

**Files to create/modify:**
- `client/src/pages/Replay.tsx` (new)
- `client/src/pages/Replay.css` (new)
- `client/src/components/replay/ReplayControls.tsx` (new)
- `client/src/components/replay/ReplayInfo.tsx` (new)
- `client/src/components/replay/index.ts` (new)
- `client/src/components/game/GameBoard.tsx` (add readOnly prop)
- `client/src/App.tsx` (add route)
- `client/src/components/game/GameOverModal.tsx` (add button)

### Phase 4: Polish and Testing

1. **Keyboard shortcuts** (space=play/pause, arrows=step)
2. **Loading states and error handling**
3. **Integration tests**

### Future Enhancements

- **Replay browser**: List and search saved replays
- **Replay sharing**: Generate shareable links
- **Export**: Download replay as JSON file
- **Import**: Load replay from file (for v1 backwards compatibility)
- **Annotations**: Add comments at specific ticks
- **Multiple perspectives**: Switch between player views in 4-player

---

## Design Decisions

1. **No state caching**: Simulate from tick 0 to target tick on every seek. Simple and fast enough for typical game lengths.

2. **Client-side seeking**: Frontend simulates game state locally for responsiveness. Server just provides the replay data.

3. **Auto-save all games**: Every completed game is automatically saved. Provides consistent test data and complete history.

4. **4-player support**: The data model supports it, but UI considerations deferred to future.

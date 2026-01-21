# MVP Implementation Plan

This document defines the implementation plan for a minimum viable Kung Fu Chess game where a player can play against a dummy AI in the browser.

## MVP Scope

### In Scope
- Single-player vs AI (dummy AI that makes no moves initially)
- **Both board types**:
  - Standard 2-player board (8x8)
  - 4-player board (12x12 with cut corners)
- Standard speed mode (1 sec/square, 10 sec cooldown)
- Basic board rendering with PixiJS
- Click-to-move interaction
- Real-time game state updates
- Game end detection (win/draw)
- In-memory game storage (no persistence)

### Out of Scope (Future)
- Lightning speed mode
- User authentication
- Persistent game history
- Replay system
- Lobbies and matchmaking
- Multiple concurrent games per user
- Smart AI (MCTS)
- Campaign mode
- Mobile support

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (Client)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  React App  │  │   Zustand   │  │   PixiJS Game Canvas    │  │
│  │  (Router)   │◄─┤   (State)   │◄─┤   (Board Rendering)     │  │
│  └─────────────┘  └──────┬──────┘  └─────────────────────────┘  │
│                          │                                       │
│                   ┌──────▼──────┐                                │
│                   │  WebSocket  │                                │
│                   │   Client    │                                │
│                   └──────┬──────┘                                │
└──────────────────────────┼──────────────────────────────────────┘
                           │
                    ───────┼─────── HTTP / WebSocket
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                          │           Server (FastAPI)            │
│                   ┌──────▼──────┐                                │
│                   │  WebSocket  │                                │
│                   │   Handler   │                                │
│                   └──────┬──────┘                                │
│                          │                                       │
│  ┌───────────────────────▼───────────────────────────────────┐  │
│  │                    Game Service                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │  │
│  │  │ Game Loop   │  │ Game Store  │  │   AI Manager    │    │  │
│  │  │ (10 ticks/s)│  │ (In-Memory) │  │ (Dummy/Random)  │    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘    │  │
│  └───────────────────────┬───────────────────────────────────┘  │
│                          │                                       │
│                   ┌──────▼──────┐                                │
│                   │ Game Engine │                                │
│                   │  (Existing) │                                │
│                   └─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Design

### REST Endpoints

All endpoints are prefixed with `/api`.

#### Create Game
```
POST /api/games

Request:
{
  "speed": "standard",           // "standard" | "lightning" (MVP: standard only)
  "board_type": "standard",      // "standard" (8x8) | "four_player" (12x12)
  "opponent": "bot:dummy"        // "bot:dummy" | "bot:random" (MVP: dummy only)
}

Response:
{
  "game_id": "ABC12345",
  "player_key": "p1_xyz789",     // Secret key for player 1
  "player_number": 1,
  "board_type": "standard",
  "status": "waiting"
}

Notes:
- For "four_player" board, 3 bot opponents are created (players 2, 3, 4)
- For "standard" board, 1 bot opponent is created (player 2)
```

#### Get Game State
```
GET /api/games/{game_id}

Response:
{
  "game_id": "ABC12345",
  "status": "playing",           // "waiting" | "playing" | "finished"
  "current_tick": 150,
  "winner": null,                // null | 0 (draw) | 1 | 2
  "board": {
    "board_type": "standard",
    "width": 8,
    "height": 8,
    "pieces": [
      {
        "id": "P:1:6:4",
        "type": "P",
        "player": 1,
        "row": 5.5,              // Float for interpolation
        "col": 4.0,
        "captured": false,
        "moving": true,
        "on_cooldown": false
      },
      // ... more pieces
    ]
  },
  "active_moves": [
    {
      "piece_id": "P:1:6:4",
      "path": [[6, 4], [5, 4]],
      "start_tick": 140,
      "progress": 0.5            // 0.0 to 1.0
    }
  ],
  "cooldowns": [
    {
      "piece_id": "N:1:7:1",
      "remaining_ticks": 45
    }
  ]
}
```

#### Make Move
```
POST /api/games/{game_id}/move

Request:
{
  "player_key": "p1_xyz789",
  "piece_id": "P:1:6:4",
  "to_row": 4,
  "to_col": 4
}

Response (success):
{
  "success": true,
  "move": {
    "piece_id": "P:1:6:4",
    "path": [[6, 4], [5, 4], [4, 4]],
    "start_tick": 151
  }
}

Response (error):
{
  "success": false,
  "error": "invalid_move",       // "invalid_move" | "not_your_piece" | "piece_busy" | "game_over"
  "message": "Piece is on cooldown"
}
```

#### Get Legal Moves
```
GET /api/games/{game_id}/legal-moves?player_key={player_key}

Response:
{
  "moves": [
    {"piece_id": "P:1:6:0", "targets": [[5, 0], [4, 0]]},
    {"piece_id": "P:1:6:1", "targets": [[5, 1], [4, 1]]},
    {"piece_id": "N:1:7:1", "targets": [[5, 0], [5, 2]]},
    // ... more pieces with their legal targets
  ]
}
```

#### Mark Ready (Start Game)
```
POST /api/games/{game_id}/ready

Request:
{
  "player_key": "p1_xyz789"
}

Response:
{
  "success": true,
  "game_started": true,
  "status": "playing"
}
```

---

## WebSocket Protocol

### Connection
```
WS /ws/game/{game_id}?player_key={player_key}
```

The `player_key` is optional for spectators.

### Server → Client Messages

#### Game State Update (sent every tick while game is active)
```json
{
  "type": "state",
  "tick": 151,
  "pieces": [
    {"id": "P:1:6:4", "row": 5.3, "col": 4.0, "captured": false}
    // Only pieces that changed or are moving
  ],
  "active_moves": [...],
  "cooldowns": [...],
  "events": [
    {"type": "capture", "capturer": "Q:1:7:3", "captured": "P:2:1:4", "tick": 150}
  ]
}
```

#### Game Started
```json
{
  "type": "game_started",
  "tick": 0
}
```

#### Game Over
```json
{
  "type": "game_over",
  "winner": 1,
  "reason": "king_captured"      // "king_captured" | "draw_timeout" | "resignation"
}
```

#### Move Rejected
```json
{
  "type": "move_rejected",
  "piece_id": "P:1:6:4",
  "reason": "piece_on_cooldown"
}
```

### Client → Server Messages

#### Make Move
```json
{
  "type": "move",
  "piece_id": "P:1:6:4",
  "to_row": 4,
  "to_col": 4
}
```

#### Mark Ready
```json
{
  "type": "ready"
}
```

#### Ping (keepalive)
```json
{
  "type": "ping"
}
```

---

## Game Service Design

### GameService Class

```python
# server/src/kfchess/services/game_service.py

class GameService:
    """Manages active games and their tick loops."""

    def __init__(self):
        self.games: dict[str, ManagedGame] = {}
        self.connections: dict[str, set[WebSocket]] = {}  # game_id -> websockets

    async def create_game(self, speed: Speed, opponent: str) -> tuple[str, str]:
        """Create a new game. Returns (game_id, player_key)."""

    async def get_game(self, game_id: str) -> GameState | None:
        """Get current game state."""

    async def make_move(self, game_id: str, player_key: str,
                        piece_id: str, to_row: int, to_col: int) -> MoveResult:
        """Attempt to make a move."""

    async def mark_ready(self, game_id: str, player_key: str) -> bool:
        """Mark player as ready. Returns True if game started."""

    async def connect(self, game_id: str, websocket: WebSocket, player_key: str | None):
        """Add WebSocket connection to game."""

    async def disconnect(self, game_id: str, websocket: WebSocket):
        """Remove WebSocket connection from game."""


@dataclass
class ManagedGame:
    """A game being managed by the service."""
    state: GameState
    player_keys: dict[int, str]  # player_number -> secret key
    task: asyncio.Task | None    # The tick loop task
    last_activity: datetime
```

### Game Loop

```python
async def game_loop(self, game_id: str):
    """Run the game tick loop at 10 ticks/second."""
    game = self.games.get(game_id)
    if not game:
        return

    tick_interval = 0.1  # 100ms = 10 ticks/sec

    while game.state.status == GameStatus.PLAYING:
        start_time = time.monotonic()

        # 1. Process AI move (if it's AI's turn and AI wants to move)
        await self._process_ai_move(game)

        # 2. Advance game state
        game.state, events = GameEngine.tick(game.state)

        # 3. Broadcast state to connected clients
        await self._broadcast_state(game_id, game.state, events)

        # 4. Check for game over
        if game.state.status == GameStatus.FINISHED:
            await self._broadcast_game_over(game_id, game.state)
            break

        # 5. Sleep for remainder of tick interval
        elapsed = time.monotonic() - start_time
        if elapsed < tick_interval:
            await asyncio.sleep(tick_interval - elapsed)

    # Cleanup
    del self.games[game_id]
```

---

## AI Design

### AI Interface

```python
# server/src/kfchess/ai/base.py

from abc import ABC, abstractmethod

class AIPlayer(ABC):
    """Base class for AI implementations."""

    @abstractmethod
    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        """Return True if AI wants to make a move this tick."""

    @abstractmethod
    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        """Return (piece_id, to_row, to_col) or None if no move."""
```

### Dummy AI (MVP)

```python
# server/src/kfchess/ai/dummy.py

class DummyAI(AIPlayer):
    """AI that never moves. For testing basic gameplay."""

    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        return False

    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        return None
```

### Random AI (Post-MVP)

```python
# server/src/kfchess/ai/random_ai.py

class RandomAI(AIPlayer):
    """AI that makes random legal moves periodically."""

    def __init__(self, move_interval_ticks: int = 30):  # Move every 3 seconds
        self.move_interval = move_interval_ticks
        self.last_move_tick: dict[str, int] = {}  # game_id -> last move tick

    def should_move(self, state: GameState, player: int, current_tick: int) -> bool:
        last = self.last_move_tick.get(state.game_id, 0)
        return current_tick - last >= self.move_interval

    def get_move(self, state: GameState, player: int) -> tuple[str, int, int] | None:
        legal_moves = GameEngine.get_legal_moves(state, player)
        if not legal_moves:
            return None
        return random.choice(legal_moves)
```

---

## Frontend Design

### Component Structure

```
client/src/
├── App.tsx                 # Router setup
├── main.tsx               # Entry point
│
├── pages/
│   ├── Home.tsx           # Landing page with "Play vs AI" button
│   └── Game.tsx           # Game page (board + UI)
│
├── components/
│   └── game/
│       ├── GameBoard.tsx      # PixiJS canvas wrapper
│       ├── GameStatus.tsx     # Shows current game status, whose turn, etc.
│       ├── CapturedPieces.tsx # Shows captured pieces
│       └── GameOverModal.tsx  # Win/lose/draw modal
│
├── game/
│   ├── renderer.ts        # PixiJS board rendering
│   ├── sprites.ts         # Piece sprite definitions
│   ├── input.ts           # Click handling, piece selection
│   └── interpolation.ts   # Piece position interpolation
│
├── stores/
│   └── game.ts            # Zustand game state store
│
├── api/
│   ├── client.ts          # HTTP client
│   └── types.ts           # API types
│
├── ws/
│   ├── client.ts          # WebSocket manager
│   └── types.ts           # Message types
│
└── utils/
    └── constants.ts       # Board size, colors, etc.

### Player Colors

```typescript
// client/src/utils/constants.ts

export const PLAYER_COLORS = {
  1: '#FFFFFF',  // White (East in 4-player)
  2: '#1A1A1A',  // Black (South in 4-player)
  3: '#E63946',  // Red (West in 4-player)
  4: '#457B9D',  // Blue (North in 4-player)
};

export const BOARD_COLORS = {
  light: '#F0D9B5',
  dark: '#B58863',
  highlight: '#FFFF00',
  legalMove: '#90EE90',
  selected: '#7FFF00',
  invalid: '#666666',  // For 4-player corner squares
};
```
```

### Zustand Game Store

```typescript
// client/src/stores/game.ts

interface GameState {
  // Connection state
  gameId: string | null;
  playerKey: string | null;
  playerNumber: number;  // 1 or 2, 0 for spectator
  connected: boolean;

  // Game state (from server)
  status: 'waiting' | 'playing' | 'finished';
  currentTick: number;
  winner: number | null;
  pieces: Piece[];
  activeMoves: ActiveMove[];
  cooldowns: Cooldown[];

  // UI state
  selectedPieceId: string | null;
  legalMoves: LegalMove[];

  // Actions
  createGame: (opponent: string) => Promise<void>;
  connect: () => void;
  disconnect: () => void;
  markReady: () => void;
  selectPiece: (pieceId: string | null) => void;
  makeMove: (pieceId: string, toRow: number, toCol: number) => void;

  // Internal
  updateFromServer: (data: ServerStateUpdate) => void;
}
```

### PixiJS Renderer

```typescript
// client/src/game/renderer.ts

export class GameRenderer {
  private app: PIXI.Application;
  private boardContainer: PIXI.Container;
  private piecesContainer: PIXI.Container;
  private highlightContainer: PIXI.Container;
  private boardType: 'standard' | 'four_player';

  constructor(canvas: HTMLCanvasElement, boardType: 'standard' | 'four_player') {
    // Initialize PixiJS application
    // Board size: 8x8 for standard, 12x12 for four_player
  }

  // Render the chess board squares
  // For four_player: skip corner squares (2x2 in each corner)
  renderBoard(): void;

  // Render all pieces at their current positions
  renderPieces(pieces: Piece[], activeMoves: ActiveMove[], currentTick: number): void;

  // Highlight legal move targets for selected piece
  highlightLegalMoves(moves: {row: number, col: number}[]): void;

  // Highlight selected piece
  highlightSelectedPiece(pieceId: string | null): void;

  // Convert screen coordinates to board coordinates
  // For four_player: return null for corner squares
  screenToBoard(x: number, y: number): {row: number, col: number} | null;

  // Check if a square is valid (for four_player corner handling)
  isValidSquare(row: number, col: number): boolean;

  // Cleanup
  destroy(): void;
}
```

### Board Rendering Details

#### Standard Board (8x8)
- 64 squares in alternating colors
- Player 1 (white) at bottom, Player 2 (black) at top

#### Four-Player Board (12x12 with corners)
- 128 valid squares (144 - 16 corner squares)
- Corner squares (2x2 in each corner) are not rendered or are visually distinct
- Player positions:
  - Player 1 (East): right side, pieces in cols 10-11
  - Player 2 (South): bottom, pieces in rows 10-11
  - Player 3 (West): left side, pieces in cols 0-1
  - Player 4 (North): top, pieces in rows 0-1
- Four distinct piece colors needed

```typescript
// Corner detection for 4-player board
function isCornerSquare(row: number, col: number): boolean {
  const isTopLeft = row < 2 && col < 2;
  const isTopRight = row < 2 && col >= 10;
  const isBottomLeft = row >= 10 && col < 2;
  const isBottomRight = row >= 10 && col >= 10;
  return isTopLeft || isTopRight || isBottomLeft || isBottomRight;
}
```
```

### Piece Position Interpolation

```typescript
// client/src/game/interpolation.ts

/**
 * Calculate piece position based on active move progress.
 *
 * @param piece - The piece data
 * @param activeMove - The active move (if any)
 * @param currentTick - Current game tick
 * @param ticksPerSquare - Ticks to move one square (10 for standard)
 */
export function interpolatePiecePosition(
  piece: Piece,
  activeMove: ActiveMove | null,
  currentTick: number,
  ticksPerSquare: number
): { row: number; col: number } {
  if (!activeMove) {
    return { row: piece.row, col: piece.col };
  }

  const elapsed = currentTick - activeMove.startTick;
  const totalTicks = (activeMove.path.length - 1) * ticksPerSquare;
  const progress = Math.min(elapsed / totalTicks, 1.0);

  // Find which segment we're on
  const segmentProgress = progress * (activeMove.path.length - 1);
  const segmentIndex = Math.floor(segmentProgress);
  const segmentFraction = segmentProgress - segmentIndex;

  if (segmentIndex >= activeMove.path.length - 1) {
    const end = activeMove.path[activeMove.path.length - 1];
    return { row: end[0], col: end[1] };
  }

  const start = activeMove.path[segmentIndex];
  const end = activeMove.path[segmentIndex + 1];

  return {
    row: start[0] + (end[0] - start[0]) * segmentFraction,
    col: start[1] + (end[1] - start[1]) * segmentFraction,
  };
}
```

---

## Data Flow

### Game Creation Flow

```
1. User clicks "Play vs AI" on Home page
2. User selects board type (Standard 2-player or 4-player)
3. Frontend calls POST /api/games {board_type: "standard"|"four_player", opponent: "bot:dummy"}
4. Server creates GameState with appropriate board
5. Server creates bot player(s):
   - Standard: 1 bot (player 2)
   - Four-player: 3 bots (players 2, 3, 4)
6. Server marks all bots as ready (bots auto-ready)
7. Server returns game_id, player_key, board_type to frontend
8. Frontend stores player_key, navigates to /game/{game_id}
9. Frontend connects WebSocket: /ws/game/{game_id}?player_key={key}
10. User clicks "Ready" button
11. Frontend sends {type: "ready"} over WebSocket
12. Server marks player 1 as ready, game starts
13. Server starts game loop (tick processing)
14. Server broadcasts {type: "game_started"} to all connections
```

### Move Flow

```
1. User clicks on their piece
2. Frontend fetches legal moves (or uses cached)
3. Frontend highlights legal targets
4. User clicks target square
5. Frontend sends {type: "move", piece_id, to_row, to_col} via WebSocket
6. Server validates move via GameEngine.validate_move()
7. If valid: Server applies move via GameEngine.apply_move()
8. If invalid: Server sends {type: "move_rejected", reason}
9. Server broadcasts updated state on next tick
10. Frontend updates piece positions from state update
```

### Tick Update Flow

```
1. Game loop fires every 100ms
2. Server calls GameEngine.tick(state)
3. Engine processes: collisions, move completions, promotions, cooldowns
4. Engine returns events (captures, promotions, game_over)
5. Server builds state update message
6. Server broadcasts to all WebSocket connections
7. Frontend receives update, updates Zustand store
8. PixiJS renderer re-renders pieces at new positions
```

---

## File Structure (Server)

```
server/src/kfchess/
├── __init__.py
├── main.py                    # FastAPI app entry point
├── settings.py                # Configuration
│
├── api/
│   ├── __init__.py
│   ├── router.py              # Main API router
│   └── games.py               # Game endpoints
│
├── ws/
│   ├── __init__.py
│   ├── handler.py             # WebSocket handler
│   └── protocol.py            # Message types
│
├── services/
│   ├── __init__.py
│   └── game_service.py        # Game management + tick loop
│
├── ai/
│   ├── __init__.py
│   ├── base.py                # AI interface
│   ├── dummy.py               # Dummy AI (no moves)
│   └── random_ai.py           # Random move AI
│
└── game/                      # (existing - no changes needed)
    ├── __init__.py
    ├── engine.py
    ├── board.py
    ├── pieces.py
    ├── moves.py
    ├── collision.py
    └── state.py
```

---

## Implementation Order

### Phase 1: Backend Foundation
1. **Game Service** (`services/game_service.py`)
   - In-memory game storage
   - Create game, get game, make move methods
   - Player key generation and validation

2. **REST API** (`api/games.py`)
   - POST /api/games (create)
   - GET /api/games/{id} (get state)
   - POST /api/games/{id}/move
   - POST /api/games/{id}/ready

3. **Dummy AI** (`ai/dummy.py`, `ai/base.py`)
   - AI interface
   - Dummy implementation (never moves)

### Phase 2: Real-Time Communication
4. **WebSocket Handler** (`ws/handler.py`)
   - Connection management
   - Message parsing
   - Integration with game service

5. **Game Loop** (in `game_service.py`)
   - Async tick loop
   - State broadcasting
   - AI move processing

### Phase 3: Frontend Core
6. **API Client** (`client/src/api/`)
   - HTTP client for REST endpoints
   - Type definitions

7. **WebSocket Client** (`client/src/ws/`)
   - Connection management
   - Message handling
   - Reconnection logic

8. **Game Store** (`client/src/stores/game.ts`)
   - State management
   - Actions for game flow

### Phase 4: Game Rendering
9. **PixiJS Setup** (`client/src/game/renderer.ts`)
   - Canvas initialization
   - Board rendering
   - Piece sprites

10. **Piece Rendering** (`client/src/game/`)
    - Position interpolation
    - Move animation
    - Capture effects

11. **Input Handling** (`client/src/game/input.ts`)
    - Click detection
    - Piece selection
    - Move submission

### Phase 5: UI Polish
12. **Game Page** (`client/src/pages/Game.tsx`)
    - Layout with board + status
    - Ready button
    - Game over handling

13. **Home Page** (`client/src/pages/Home.tsx`)
    - "Play vs AI" button
    - Game creation flow

---

## Testing Strategy

### Backend Tests
- Unit tests for game service methods
- Integration tests for API endpoints
- WebSocket connection tests

### Frontend Tests
- Zustand store unit tests
- Component rendering tests
- E2E test: create game → make moves → win

### Manual Testing Checklist

#### Standard Board (2-Player)
- [ ] Create game vs dummy AI (standard board)
- [ ] Mark ready, game starts
- [ ] Click piece, see legal moves
- [ ] Make valid move, see piece move
- [ ] Try invalid move, see rejection
- [ ] Move piece, wait for cooldown
- [ ] Capture opponent piece
- [ ] Promote pawn to queen (row 0)
- [ ] Capture opponent king, see win screen
- [ ] Refresh page, reconnect to game

#### Four-Player Board
- [ ] Create game vs dummy AI (4-player board)
- [ ] Board renders with corners cut off
- [ ] All 4 players have distinct colors
- [ ] Player 1 pawns move left (toward col 2)
- [ ] Capture pieces from any opponent
- [ ] Promote pawn at correct edge (col 2 for player 1)
- [ ] Eliminate all opponent kings, see win screen

---

## Configuration

### Environment Variables

```bash
# server/.env
DEV_MODE=true
HOST=0.0.0.0
PORT=8000

# client/.env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

### Game Constants

```python
# Standard speed (MVP default)
TICK_PERIOD_MS = 100        # 10 ticks per second
TICKS_PER_SQUARE = 10       # 1 second to move one square
COOLDOWN_TICKS = 100        # 10 second cooldown
```

---

## Success Criteria

The MVP is complete when:

### Core Gameplay
1. ✅ User can create a game vs dummy AI from home page
2. ✅ User can select board type (standard or 4-player)
3. ✅ User can see the chess board with all pieces
4. ✅ User can click a piece and see legal move highlights
5. ✅ User can make moves by clicking target squares
6. ✅ Pieces animate smoothly during movement
7. ✅ Cooldown is visually indicated (piece greyed out or timer)
8. ✅ Captures work correctly (piece disappears)
9. ✅ Pawn promotion works (becomes queen)
10. ✅ Game ends when king is captured (last king standing for 4-player)
11. ✅ Win/lose screen is shown

### 4-Player Specific
12. ✅ 4-player board renders correctly (12x12 with corners cut)
13. ✅ All 4 players have distinct piece colors
14. ✅ Pawns move in correct direction for each player
15. ✅ Pawns promote at correct edges for each player
16. ✅ Game ends when only one king remains

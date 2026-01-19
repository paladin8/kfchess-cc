# Kung Fu Chess - Original Implementation Documentation

This document provides a comprehensive reference of the original Kung Fu Chess implementation located at `/home/jeffr/code/kfchess`. Use this as a reference when rebuilding the game.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Python Backend Architecture](#python-backend-architecture)
4. [JavaScript Frontend Architecture](#javascript-frontend-architecture)
5. [Game Flow - Complete User Journey](#game-flow---complete-user-journey)
6. [Key Game Mechanics](#key-game-mechanics)
7. [API Reference](#api-reference)
8. [Dependencies](#dependencies)
9. [Deployment](#deployment)
10. [Key Algorithms](#key-algorithms)
11. [Known Limitations](#known-limitations)

---

## Project Overview

Kung Fu Chess is a **real-time, turn-free chess game** where players can move pieces simultaneously. Unlike traditional chess, there are no turns - both players can move any of their pieces at any time, subject to cooldown periods after each move.

### Key Features

- **Real-time multiplayer** via WebSockets
- **Simultaneous movement** - no turns, pieces move in real-time
- **Cooldown system** - pieces cannot move again immediately after moving
- **Campaign mode** - 64 levels organized into 8 belts
- **AI opponents** - multiple difficulty levels (novice, intermediate, advanced)
- **Elo rating system** - for ranked multiplayer games
- **Game replays** - watch previous games

### Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | Python Flask + Flask-SocketIO |
| Frontend | React.js + PIXI.js (canvas rendering) |
| Database | PostgreSQL |
| Real-time | WebSockets (Socket.IO) |
| Auth | Google OAuth 2.0 |
| Storage | AWS S3 (profile pictures) |

---

## Directory Structure

```
/home/jeffr/code/kfchess/
├── main.py                    # Flask app entry point
├── context.py                 # Server context constant
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
├── LICENSE                    # MIT License
├── favicon.ico
│
├── lib/                       # Game logic & AI
│   ├── __init__.py
│   ├── game.py               # Core game engine (moves, cooldowns, captures, win conditions)
│   ├── board.py              # Board representation and piece management
│   ├── ai.py                 # Bot AI with multiple difficulty levels
│   ├── campaign.py           # Campaign levels (64 levels, 8 belts)
│   ├── replay.py             # Game replay recording/playback
│   ├── elo.py                # Elo rating calculation
│   └── cli.py                # Command-line interface
│
├── web/                       # Flask blueprints & WebSocket handlers
│   ├── __init__.py           # game_states dictionary
│   ├── game.py               # Game creation, moves, ticking (main game loop)
│   ├── live.py               # API for live games listing
│   └── user.py               # User auth (Google OAuth), profile, history, campaign
│
├── db/                        # Database layer
│   ├── __init__.py           # db_service instance
│   ├── models.py             # Data models (User, UserGameHistory, ActiveGame, etc.)
│   ├── service.py            # DbService class for all database operations
│   ├── schema.sql            # PostgreSQL schema
│   └── s3.py                 # AWS S3 integration for profile pictures
│
├── ui/                        # React.js frontend
│   ├── index.js              # App entry point
│   ├── index.html            # HTML template
│   ├── package.json          # NPM dependencies
│   ├── postcss.config.js     # PostCSS configuration
│   │
│   ├── containers/           # React components
│   │   ├── App.js            # Root component, routing, state management
│   │   ├── Game.js           # Game container (game board + UI)
│   │   ├── GameBoard.js      # Canvas-based chess board (PIXI.js)
│   │   ├── Home.js           # Home page
│   │   ├── Campaign.js       # Campaign mode selector
│   │   ├── Replay.js         # Game replay viewer
│   │   ├── Live.js           # Live games listing
│   │   ├── Profile.js        # User profile
│   │   ├── Users.js          # User search/listing
│   │   ├── Header.js         # Navigation header
│   │   └── [other components]
│   │
│   ├── util/                 # Utility modules
│   │   ├── GameLogic.js      # Move validation & piece behavior
│   │   ├── GameState.js      # WebSocket client, game state management
│   │   ├── Listener.js       # Background listener for invites/online users
│   │   ├── Sprites.js        # Chess piece sprite definitions
│   │   ├── Speed.js          # Game speed utilities
│   │   ├── Time.js           # Time formatting utilities
│   │   └── CampaignLevels.js # Campaign level definitions
│   │
│   ├── styles/               # LESS stylesheets
│   │   ├── index.less        # Main stylesheet
│   │   ├── game.less         # Game board styling
│   │   └── [other .less files]
│   │
│   ├── assets/               # Game graphics
│   │   ├── chess-sprites.png # Sprite sheet for all pieces
│   │   ├── chessboard.png    # Light board
│   │   └── chessboard-black.png  # Dark board
│   │
│   ├── static/               # Static assets
│   │   ├── belt-*.png        # Belt achievement images
│   │   ├── kfchess-*.mp3     # Sound effects & music
│   │   └── logo.png          # Logo
│   │
│   └── webpack/              # Build configuration
│       ├── webpack.common.config.js
│       ├── webpack.dev.config.js
│       └── webpack.prod.config.js
│
└── deploy/                    # Deployment scripts
    ├── deploy.sh            # Main deployment script
    ├── buildpy.sh           # Build Python environment
    └── buildui.sh           # Build UI bundle
```

---

## Python Backend Architecture

### Core Game Engine (`lib/game.py`)

#### Speed Enum

```python
class Speed(Enum):
    STANDARD = 'standard'   # 10 ticks per move, 100 ticks cooldown
    LIGHTNING = 'lightning' # 2 ticks per move, 20 ticks cooldown

# Tick period: 0.1 seconds (100 ticks per second)
```

#### Key Classes

**`Move`** - Represents a piece movement:
- `piece`: The piece being moved
- `move_seq`: Path of squares (list of (row, col) tuples)
- `start_tick`: When the move started

**`Cooldown`** - Represents piece cooldown period:
- `piece`: The piece on cooldown
- `start_tick`: When cooldown started

**`Game`** - Main game state machine:
- Manages board state, active moves, cooldowns
- Updates occur every tick via `tick()` method
- Supports multiple game modes: standard play, campaign, replay

#### Game Rules

1. **Simultaneous Movement**: Multiple pieces can move at once
2. **Move Ticks**: Each piece travels at speed-dependent rate (1 square per move_tick)
3. **Cooldowns**: After completing a move, piece cannot move again for cooldown_ticks
4. **Capturing**: Pieces capture when they get within 0.4 squares of opponent piece
5. **Pawn Promotion**: Pawns promote to Queens when reaching opposite end
6. **Castling**: King + unmoved rook can castle (special two-move)
7. **Knight Jumps**: Knights have special path (floating for half move)

#### Win Conditions

- **King captured**: Opponent wins
- **Draw conditions**:
  - STANDARD: No moves for 2+ minutes AND no captures for 3+ minutes
  - LIGHTNING: No moves for 30+ seconds AND no captures for 45+ seconds
  - CAMPAIGN: No moves for 2+ minutes (no capture timeout)

#### Key Methods

```python
def move(piece_id, player, to_row, to_col):
    """Attempt to move piece, returns Move object or None"""

def tick():
    """Advance game state by one tick, return (status, updates)"""

def _compute_move_seq(piece, to_row, to_col):
    """Calculate path for piece to destination"""

def _get_interp_position(piece):
    """Get interpolated position during movement (for collision detection)"""
```

### Board Representation (`lib/board.py`)

**`Piece` Class:**
```python
Piece(
    type,      # 'P', 'N', 'B', 'R', 'Q', 'K'
    player,    # 1 (white) or 2 (black)
    row,       # 0-7
    col,       # 0-7
    captured,  # bool
    moved,     # bool (for castling eligibility)
    id         # Format: "TYPE:PLAYER:ROW:COL"
)
```

**`Board` Class:**
```python
pieces: List[Piece]  # All pieces including captured ones

def get_piece_by_id(id)
def get_piece_by_location(row, col)
def get_location_to_piece_map()
```

**Initial Board Layout:**
```
Row 0: R2 N2 B2 Q2 K2 B2 N2 R2  (Black back row)
Row 1: P2 P2 P2 P2 P2 P2 P2 P2  (Black pawns)
Row 2-5: Empty
Row 6: P1 P1 P1 P1 P1 P1 P1 P1  (White pawns)
Row 7: R1 N1 B1 Q1 K1 B1 N1 R1  (White back row)
```

### AI System (`lib/ai.py`)

**Difficulty Levels:**

| Level | Move Delay | Search Depth |
|-------|------------|--------------|
| novice | 39 ticks | 5 moves |
| intermediate | 26 ticks | 2 moves |
| advanced | 13 ticks | 1 move |
| campaign | 10 ticks | 1 move |

**Scoring Algorithm:**
- Weighted factors: Capture (32x), Pressure (16x), Vulnerability (16x), Protection (8x)
- Row/column advancement weights
- Selects moves by score; randomizes with jitter for variety

### Campaign Mode (`lib/campaign.py`)

**64 Levels** organized in **8 Belts** (8 levels per belt):
- Each level has specific board configuration
- Player fights AI opponent ("c:{level}" format)
- Wins unlock next belt
- Belts: White, Yellow, Green, Purple, Orange, Blue, Brown, Red, Black

### WebSocket Events (`main.py`)

**Client → Server:**

| Event | Purpose |
|-------|---------|
| `listen` | Register user for online notifications |
| `join` | Join a game |
| `ready` | Signal player is ready to start |
| `move` | Send move command |
| `reset` | Reset game (campaign/finished only) |
| `cancel` | Cancel unstarted game |
| `difficulty` | Change bot difficulty |
| `leave` | Leave game |

**Server → Client:**

| Event | Purpose |
|-------|---------|
| `joinack` | Confirm join with game state |
| `moveack` | Confirm move |
| `readyack` | Confirm ready |
| `update` | Game state update (piece movement, capture, etc.) |
| `newratings` | Elo rating change |
| `newbelt` | Campaign belt completion |
| `online` | List of online users |
| `invite` | Incoming game invite |

### Game Loop (`web/game.py`)

**Tick Process** (100 ticks/second):

1. Check bot moves: If game tick >= 10, AI players make decisions
2. Check replay moves: If replaying, apply recorded moves
3. Tick game: Advance game state (movement, collision, capture, cooldown)
4. Emit updates: Send game state to all connected players
5. Post-game:
   - Remove from active_games table
   - Save replay to game_history
   - Add to player game history
   - Update Elo ratings (if 2 logged-in users)
   - Update campaign progress

**Active Game Timeout**: 10 minutes without tick activity

### Database Schema (`db/schema.sql`)

**Tables:**

1. **users**
   - id, email (unique), username (unique), picture_url
   - ratings (JSONB: {speed → elo_score})
   - join_time, last_online, current_game (JSONB with gameId + playerKey)

2. **user_game_history**
   - id, user_id, game_time
   - game_info (JSONB: speed, player, winner, historyId, ticks, opponents)

3. **game_history**
   - id, replay (JSONB: full game replay data)

4. **active_games**
   - id, server, game_id, game_info (JSONB: players, speed, startTime)

5. **campaign_progress**
   - id, user_id (unique), progress (JSONB: levelsCompleted, beltsCompleted)

### Authentication (`web/user.py`)

- Google OAuth 2.0 integration
- Users registered on first login
- Random username generation: "[Animal] [ChessPiece] [3-digit number]"
- CSRF token validation on POST requests
- Session-based authentication with Flask-Login

---

## JavaScript Frontend Architecture

### React Component Hierarchy

```
App (root component, state management)
├── Header (navigation)
├── Router
│   ├── Home
│   ├── Game
│   │   └── GameBoard (PIXI canvas)
│   ├── Campaign
│   ├── Replay
│   ├── Live
│   ├── Profile
│   ├── Users
│   ├── About
│   └── PrivacyPolicy
└── Alert (error/success messages)
```

### Core Components

**App.js** - Root component:
- Manages global state: user, known users, online users, csrf token
- Handles login/logout
- Routes to all pages
- Initializes Listener for real-time online user updates
- Creates new games and manages game invites

**Game.js** - Game view:
- Renders GameBoard component
- Manages game lifecycle (init, play, finish)
- Handles audio (background music, capture sounds)
- Updates UI with game status
- Manages modal dialogs (invite, game options)

**GameBoard.js** - Canvas rendering (PIXI.js):
- Renders 8x8 chessboard with piece sprites
- Handles click/drag for move selection
- Animates piece movement in real-time
- Shows valid move indicators
- Renders cooldown/active move states

**Home.js** - Landing page:
- Create new game vs AI (select difficulty)
- Play multiplayer (find opponent)
- Play campaign

**Campaign.js** - Campaign selector:
- Shows all 64 levels organized by belt
- Displays completion status
- Shows level descriptions
- Launches campaign games

### Game State Management (`ui/util/GameState.js`)

```javascript
class GameState {
    constructor(gameId, playerKey, fetchUserInfo, endCallback,
                ratingCallback, beltCallback)

    // Socket.IO events handled:
    // - joinack: Game joined, receive initial state
    // - moveack: Move confirmed
    // - update: Game state update
    // - newratings: Elo rating change
    // - newbelt: Campaign belt completed

    move(pieceId, toRow, toCol)  // Send move to server
    ready()                       // Signal ready to start
    reset()                       // Reset game
    registerListener(callback)    // Receive update events
}
```

### Move Validation (`ui/util/GameLogic.js`)

Client-side validation (mirrors server validation):
- `isLegalMoveNoCross()`: Check piece path for obstacles
- `isPawnLegalMove()`, `isKnightLegalMove()`, etc.: Piece-specific rules
- `isMoving()`, `isCooldown()`: Check piece state
- `getPieceById()`, `getPieceByLocation()`: Board queries

### Real-Time Communication (`ui/util/Listener.js`)

```javascript
class Listener {
    // Maintains persistent WebSocket connection
    // Listens for:
    //   - Game invites from other users
    //   - Online user list updates
    // Pings server every 5 minutes to stay "online"
    // Auto-reconnects on disconnect
}
```

### Sprite Sheet (`ui/util/Sprites.js`)

Chess piece sprites stored in single sprite sheet:
- `chess-sprites.png`: 650x230px, contains all pieces
- Pieces indexed by type + player: `P1`, `P2`, `N1`, `N2`, etc.
- Loaded dynamically via PIXI.js

---

## Game Flow - Complete User Journey

### Campaign Flow

```
User clicks "Campaign"
    ↓
Campaign.js loads user's progress from /api/user/campaign
    ↓
Shows all 64 levels, current belt achievement
    ↓
User selects level (must have completed previous belt)
    ↓
POST /api/game/startcampaign
    → Creates Game with campaign AI
    → Returns gameId + playerKey
    ↓
Redirects to /game/{gameId}
    ↓
Game.js initializes GameState
    ↓
WebSocket 'join' event sent with gameId + playerKey
    ↓
Server returns initial game state via 'joinack'
    ↓
GameBoard.js renders board
    ↓
Game starts automatically (no ready needed vs AI)
    ↓
User makes moves → WebSocket 'move' events
    ↓
Server ticks game 100 times/second
    ↓
Game updates broadcast via 'update' events
    ↓
GameBoard animates pieces
    ↓
When king captured or draw:
    → Game ends
    → Update campaign_progress
    → Emit 'newbelt' if belt completed
    ↓
Game over modal appears
```

### Play vs AI Flow

```
User clicks "Play vs AI", selects difficulty
    ↓
POST /api/game/new with bots: {2: difficulty}
    → Creates Game with AI bot in player 2 slot
    → Returns gameId + playerKeys
    ↓
Redirects to /game/{gameId}
    ↓
[Same as Campaign from here]
```

### Multiplayer Flow

```
User A clicks "Play Multiplayer"
    ↓
POST /api/game/new with no opponent
    → Creates game with player 2 = 'o' (open)
    → Returns gameId + playerKey[1]
    ↓
Displays invite link/code
    ↓
User A presses SPACE to mark ready
    ↓
[User B joins via link or invite]
    ↓
User B's GameState connects via WebSocket
    ↓
Both users press SPACE to ready
    ↓
Game starts when both ready
    ↓
Players make simultaneous moves
    ↓
When game finishes:
    → Both players' ELO ratings updated
    → Game saved to game_history
    ↓
Game over modal with stats
```

---

## Key Game Mechanics

### Movement Timing & Interpolation

Pieces move across the board in discrete "move ticks":
- **STANDARD**: 10 ticks per square = 1 second per square
- **LIGHTNING**: 2 ticks per square = 0.2 seconds per square

Movement is interpolated client-side for smooth animation:
```javascript
weight = (tick_delta % move_ticks) / move_ticks
interpolated_position = old_pos * weight + new_pos * (1 - weight)
```

### Collision Detection

Pieces detect collisions during movement:
- **Distance threshold**: 0.4 squares (max is 0.71 diagonal)
- **Knights**: Only capture at end of move
- **Pawns moving straight**: Cannot capture (vulnerable to other pieces)
- **Pawn vs Pawn**: Earlier move wins on collision

### Cooldown System

After piece completes move:
1. Piece enters "cooldown" state
2. Cannot make new move for cooldown_ticks
3. UI shows cooldown indicator with remaining time
4. Must wait before piece can move again

| Speed | Cooldown Duration |
|-------|-------------------|
| STANDARD | 100 ticks (10 seconds) |
| LIGHTNING | 20 ticks (2 seconds) |

### Pawn Promotion

When pawn reaches opposite end (row 0 for player 1, row 7 for player 2):
- Piece type changes from 'P' to 'Q' (Queen)
- Happens automatically at end of movement
- Full queen movement power granted

### Castling

Special two-move sequence:
- Requires king + rook both unmoved
- King moves 2 squares toward rook
- Rook automatically moves to other side of king
- Happens as single "move" command but applies 2 moves

### Capture Resolution

```python
for moving_piece in active_moves:
    for opponent_piece in board.pieces:
        dist = hypot(moving_piece.pos - opponent_piece.pos)

        if dist < 0.4:  # Capture range
            if moving_piece.started_earlier:
                opponent_piece.captured = True
            else:
                moving_piece.captured = True
```

---

## API Reference

### Game Endpoints

**POST /api/game/new**
```json
Request: {
  "speed": "standard" | "lightning",
  "bots": {"1": "novice", "2": "intermediate"},  // optional
  "username": "opponent_username"  // optional
}
Response: {
  "success": true,
  "gameId": "ABCDEF",
  "playerKeys": {"1": "uuid-1", "2": "uuid-2"}
}
```

**GET /api/game/check?gameId=ABCDEF**
```json
Response: { "success": true | false }
```

**POST /api/game/startcampaign**
```json
Request: { "level": 0-63 }
Response: {
  "success": true,
  "gameId": "ABCDEF",
  "playerKeys": {"1": "uuid-1"}
}
```

**POST /api/game/startreplay**
```json
Request: { "historyId": 12345 }
Response: {
  "success": true,
  "gameId": "ABCDEF"
}
```

**POST /api/game/invite**
```json
Request: {
  "gameId": "ABCDEF",
  "player": 1 | 2,
  "username": "target_user"
}
Response: { "success": true, "message": "..." }
```

### User Endpoints

**GET /api/user/info?userId=123,456**
```json
Response: {
  "users": {
    "123": { "userId": "123", "username": "Tiger Pawn 456", ... }
  }
}
```

**GET /api/user/info** (authenticated)
```json
Response: {
  "loggedIn": true,
  "csrfToken": "...",
  "user": { ... }
}
```

**POST /api/user/update**
```json
Request: { "username": "new_username" }
Response: { "success": true, "user": { ... } }
```

**POST /api/user/uploadPic**
- Binary image data
- Uploads to S3, updates user.picture_url

**GET /api/user/history?userId=123&offset=0&count=20**
```json
Response: {
  "history": [
    {
      "gameTime": "2023-01-01T12:00:00",
      "gameInfo": {
        "speed": "standard",
        "winner": 1,
        "ticks": 2400,
        "historyId": 99999,
        "opponents": ["u:456"]
      }
    }
  ],
  "users": { "456": { ... } }
}
```

**GET /api/user/campaign?userId=123**
```json
Response: {
  "progress": {
    "levelsCompleted": {"0": true, "1": true},
    "beltsCompleted": {"1": true}
  }
}
```

### Live Games

**GET /api/live**
```json
Response: {
  "games": [
    {
      "gameId": "ABCDEF",
      "gameInfo": {
        "players": {"1": "u:123", "2": "u:456"},
        "speed": "standard",
        "startTime": "2023-01-01T12:00:00"
      }
    }
  ],
  "users": { "123": {...}, "456": {...} }
}
```

---

## Dependencies

### Backend (`requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | 1.0 | Web framework |
| Flask-Login | 0.4.1 | Session authentication |
| Flask-OAuth | 0.12 | Google OAuth |
| Flask-SocketIO | 2.9.4 | WebSocket support |
| python-socketio | 1.9.0 | SocketIO protocol |
| python-engineio | 2.0.3 | EngineIO dependency |
| eventlet | 0.22.1 | Async networking |
| psycopg2 | 2.7.4 | PostgreSQL adapter |
| SQLAlchemy | 1.3.13 | ORM |
| boto3 | 1.6.9 | AWS SDK |
| Werkzeug | 0.14.1 | WSGI utilities |

### Frontend (`ui/package.json`)

**Core:**
- react 16.2.0
- react-dom 16.2.0
- react-router-dom 4.2.2
- socket.io-client 2.0.4
- pixi.js 4.7.0 (Canvas graphics)

**UI Components:**
- react-modal 3.3.1
- react-tippy 1.2.2
- react-transition-group 2.2.1

**Utilities:**
- moment 2.21.0
- query-string 5.1.0

**Build Tools:**
- webpack 4.0.1
- babel 6.26.0
- less 3.0.1

---

## Deployment

### Build Process

**buildpy.sh:**
- Creates Python virtual environment
- Installs dependencies from requirements.txt
- Sets up local database

**buildui.sh:**
- Runs `npm install` in ui/
- Runs `npm run prod` to build webpack bundle
- Minifies and compresses output to `ui/dist/bundle.js`

### Production Setup

1. **Database**: PostgreSQL with schema initialized
2. **Flask**: Running on port 5001, fronted by nginx
3. **WebSocket**: Eventlet serving SocketIO connections
4. **Static Assets**: S3 bucket for profile pictures
5. **Frontend**: Webpack bundle served via Flask

### Environment Configuration

```python
# config.py
FLASK_SECRET_KEY = 'secret_key'
GOOGLE_CLIENT_ID = 'xxx.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = 'xxx'
AWS_REGION = 'us-west-2'
AWS_ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'
AWS_SECRET_KEY = 'wJalrXUtnFEMI/...'
```

---

## Key Algorithms

### Move Validation (`game.py::_compute_move_seq`)

1. Call piece-type-specific validation function
2. Each function returns move sequence or None
3. Move sequence validated for:
   - No pieces in path (except capture target)
   - No same-player pieces blocking
   - No same-player piece future paths blocking
4. Return tuple of (move_sequence, extra_move) or None

### Collision Resolution

```python
for moving_piece in active_moves:
    for opponent_piece in board.pieces:
        dist = hypot(moving_piece.pos - opponent_piece.pos)

        if dist < 0.4:  # Capture range
            # Determine winner
            if moving_piece.started_earlier:
                opponent_piece.captured = True
            else:
                moving_piece.captured = True
```

### Elo Rating Update (`lib/elo.py`)

```python
ea = 1.0 / (1 + 10^((rating_b - rating_a) / 400))
eb = 1.0 / (1 + 10^((rating_a - rating_b) / 400))

if draw:
    new_a = rating_a + 32 * (0.5 - ea)
    new_b = rating_b + 32 * (0.5 - eb)
elif player_a_won:
    new_a = rating_a + 32 * (1 - ea)
    new_b = rating_b + 32 * (0 - eb)
```

---

## Known Limitations

1. **Pawn Moving Straight**: Cannot capture pieces moving diagonally
2. **Knight Rendering**: Invisible during flight (between start and land)
3. **Simultaneous Captures**: Earlier-moving piece wins
4. **Draw Timeout**: Based on last_move_time + last_capture_tick, not precise
5. **Campaign**: Only supports player 1 win (no draws recorded)
6. **Replay**: No seek/pause functionality, plays full game in real-time
7. **Performance**: Active games kept in memory (game_states dict)
8. **Expired Games**: Cleared after 10 minutes of inactivity

---

## File Quick Reference

| Purpose | File Location |
|---------|---------------|
| Flask entry point | `main.py` |
| Game logic | `lib/game.py` |
| Board/pieces | `lib/board.py` |
| AI bot | `lib/ai.py` |
| Campaign levels | `lib/campaign.py` |
| Elo ratings | `lib/elo.py` |
| WebSocket handlers | `web/game.py` |
| User auth | `web/user.py` |
| Database models | `db/models.py` |
| Database service | `db/service.py` |
| React entry | `ui/index.js` |
| Main React app | `ui/containers/App.js` |
| Game component | `ui/containers/Game.js` |
| Canvas board | `ui/containers/GameBoard.js` |
| WebSocket client | `ui/util/GameState.js` |
| Move validation | `ui/util/GameLogic.js` |
| Piece sprites | `ui/assets/chess-sprites.png` |

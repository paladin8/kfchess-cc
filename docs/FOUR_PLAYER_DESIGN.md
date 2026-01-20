# 4-Player Mode - Design Document

This document outlines the implementation plan for extending the Kung Fu Chess game engine to support 4-player mode.

## Current State Summary

After reviewing the engine code, the architecture is **well-suited for 4-player extension**:

| Component | 4-Player Ready? | Notes |
|-----------|----------------|-------|
| `GameState.players` | Yes | Already `dict[int, str]` supporting 1-4 players |
| `Piece.player` | Yes | Uses player number (1-4) |
| `Board.board_type` | Yes | `BoardType.FOUR_PLAYER` enum exists |
| `Board.is_valid_square()` | Yes | Corner-cutting logic implemented |
| Collision detection | Yes | Checks `piece.player != other.player` |
| Win condition | Yes | Checks all kings via `state.players.keys()` |
| **Pawn direction** | **No** | Hardcoded for players 1 & 2 |
| **Starting positions** | **No** | Only 2-player setup implemented |
| **Promotion rows** | **No** | Hardcoded to rows 0/7 |

## Board Layout

```
         0 1 2   3 4 5 6 7 8   9 10 11
       ┌───────┬─────────────┬─────────┐
    0  │  XXX  │ R N B Q K B N R │  XXX  │  Player 4 (North)
    1  │  XXX  │ P P P P P P P P │  XXX  │
       ├───────┼─────────────────┼───────┤
    2  │ R P   │                 │   P R │
    3  │ N P   │                 │   P N │
    4  │ B P   │                 │   P B │  P3        P1
    5  │ K P   │     8x8 core    │   P Q │  (West)    (East)
    6  │ Q P   │                 │   P K │
    7  │ B P   │                 │   P B │
    8  │ N P   │                 │   P N │
    9  │ R P   │                 │   P R │
       ├───────┼─────────────────┼───────┤
   10  │  XXX  │ P P P P P P P P │  XXX  │
   11  │  XXX  │ R N B K Q B N R │  XXX  │  Player 2 (South)
       └───────┴─────────────────┴───────┘

XXX = Invalid squares (corners cut off)
```

**Dimensions**: 12x12 grid with 2x2 corners removed = 128 valid squares

## Key Design Decisions

### 1. Player Orientations

Each player faces the center from their side:

| Player | Position | Pawn Direction | Home Rows | Promotion Target |
|--------|----------|----------------|-----------|------------------|
| 1 | East (right) | Left (-col) | cols 10-11 | col 2 |
| 2 | South (bottom) | Up (-row) | rows 10-11 | row 2 |
| 3 | West (left) | Right (+col) | cols 0-1 | col 9 |
| 4 | North (top) | Down (+row) | rows 0-1 | row 9 |

### 2. Pawn Movement Axis

Pawns move along different axes depending on player:

```python
# Proposed player orientation config
@dataclass
class PlayerOrientation:
    """Defines movement directions relative to board for a player position."""
    forward: tuple[int, int]  # (row_delta, col_delta) for "forward"
    pawn_start_offset: int     # Rows/cols from home edge where pawns start
    promotion_edge: int        # Row or column index for promotion

ORIENTATIONS = {
    1: PlayerOrientation(forward=(0, -1), pawn_start_offset=2, promotion_edge=2),   # East → West
    2: PlayerOrientation(forward=(-1, 0), pawn_start_offset=2, promotion_edge=2),   # South → North
    3: PlayerOrientation(forward=(0, 1), pawn_start_offset=2, promotion_edge=9),    # West → East
    4: PlayerOrientation(forward=(1, 0), pawn_start_offset=2, promotion_edge=9),    # North → South
}
```

### 3. Collision Rules

No changes needed - existing collision detection already works for N players:
- Pieces of different players can capture each other
- Friendly fire is impossible (same player pieces pass through)
- Multi-way captures resolve by earliest-move-start-tick

### 4. Win Condition

Already implemented correctly - last king standing wins. If simultaneous king captures occur, it's a draw.

## Implementation Plan

### Phase 1: Board Factory

**File**: `server/src/kfchess/game/board.py`

Add `create_4player()` class method:

```python
@classmethod
def create_4player(cls) -> "Board":
    """Create a 12x12 board with 4-player starting positions."""
    pieces = []

    # Player 1 (East) - pieces on cols 10-11, rows 2-9
    pieces.extend(_create_player_pieces(player=1, orientation="east"))

    # Player 2 (South) - pieces on rows 10-11, cols 2-9
    pieces.extend(_create_player_pieces(player=2, orientation="south"))

    # Player 3 (West) - pieces on cols 0-1, rows 2-9
    pieces.extend(_create_player_pieces(player=3, orientation="west"))

    # Player 4 (North) - pieces on rows 0-1, cols 2-9
    pieces.extend(_create_player_pieces(player=4, orientation="north"))

    return cls(pieces=pieces, board_type=BoardType.FOUR_PLAYER)
```

### Phase 2: Pawn Logic Refactor

**File**: `server/src/kfchess/game/moves.py`

Current code (lines 157-158):
```python
direction = -1 if piece.player == 1 else 1
start_row = 6 if piece.player == 1 else 1
```

Proposed refactor:
```python
def _get_pawn_config(piece: Piece, board: Board) -> tuple[tuple[int, int], int, Callable]:
    """Get pawn movement config based on player and board type."""
    if board.board_type == BoardType.STANDARD:
        # 2-player: row-based movement
        direction = (-1, 0) if piece.player == 1 else (1, 0)
        start_dist = 1 if (piece.player == 1 and piece.row == 6) or \
                         (piece.player == 2 and piece.row == 1) else 0
        is_promotion = lambda r, c: r == 0 or r == 7
    else:
        # 4-player: orientation-based movement
        orient = ORIENTATIONS[piece.player]
        direction = orient.forward
        start_dist = _pawn_at_start_position(piece, orient)
        is_promotion = lambda r, c: _check_promotion(r, c, orient)

    return direction, start_dist, is_promotion
```

### Phase 3: Castling Updates

**File**: `server/src/kfchess/game/moves.py`

Castling logic needs to be rotation-aware:
- King always moves 2 squares toward the rook
- For side players (1, 3), castling is vertical
- For top/bottom players (2, 4), castling is horizontal

```python
def _get_castling_moves(piece: Piece, board: Board) -> list[tuple[int, int, Move]]:
    """Get available castling moves for a king."""
    if board.board_type == BoardType.STANDARD:
        return _get_standard_castling(piece, board)
    else:
        return _get_4player_castling(piece, board)
```

### Phase 4: Engine Integration

**File**: `server/src/kfchess/game/engine.py`

Update `create_game()` (line ~94, where TODO exists):

```python
def create_game(
    speed: Speed,
    players: dict[int, str],
    board_type: BoardType = BoardType.STANDARD,
) -> GameState:
    if board_type == BoardType.FOUR_PLAYER:
        if len(players) < 2 or len(players) > 4:
            raise ValueError("4-player board requires 2-4 players")
        board = Board.create_4player()
    else:
        if len(players) != 2:
            raise ValueError("Standard board requires exactly 2 players")
        board = Board.create_standard()

    return GameState(
        game_id=generate_game_id(),
        board=board,
        speed=speed,
        players=players,
        # ... rest unchanged
    )
```

### Phase 5: Tests

**File**: `server/tests/unit/game/test_4player.py`

Key test cases:
1. Board creation with correct piece positions
2. Pawn movement in all 4 directions
3. Pawn promotion at correct edges
4. Castling for side players (vertical)
5. Collision detection with 3+ players
6. Win condition with king eliminations
7. 3-player mode (one player slot empty)

## Files to Modify

| File | Changes |
|------|---------|
| `game/board.py` | Add `create_4player()`, piece positioning helpers |
| `game/moves.py` | Refactor pawn direction, add orientation config, update castling |
| `game/engine.py` | Update `create_game()` to support board type selection |
| `game/state.py` | No changes needed (already supports 4 players) |
| `game/collision.py` | No changes needed |
| `game/pieces.py` | No changes needed |

## Estimated Scope

- **Board setup**: ~100 lines (positioning all pieces correctly)
- **Pawn refactor**: ~50 lines (direction/promotion logic)
- **Castling refactor**: ~40 lines (rotation-aware)
- **Engine update**: ~20 lines
- **Tests**: ~200 lines

## Open Questions

1. **3-player support**: Should we allow games with 3 players (one corner empty)?
   - Suggestion: Yes, eliminated players' pieces simply get removed

2. **Team mode**: Should we support 2v2 (players 1+3 vs 2+4)?
   - Suggestion: Defer to future iteration, but keep collision logic flexible

3. **Rating**: Separate 4-player rating or shared with 2-player?
   - Suggestion: Separate ratings (`ratings.four_player`)

4. **AI**: How should AI handle 4-player games?
   - Suggestion: Start with simpler heuristic-based AI, MCTS can be adapted later

## Non-Goals (This Phase)

- Client-side board rotation (render from player's perspective)
- 4-player campaign levels
- 4-player matchmaking
- Team mode (2v2)

## Next Steps

1. Implement `Board.create_4player()` with piece positioning
2. Add `PlayerOrientation` dataclass and `ORIENTATIONS` config
3. Refactor pawn movement to use orientation
4. Update promotion detection
5. Add 4-player castling support
6. Update engine's `create_game()`
7. Write comprehensive tests
8. Manual testing with 4 clients

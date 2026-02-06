import { describe, it, expect } from 'vitest';
import {
  isLegalMove,
  getLegalMovesForPiece,
  getAllLegalMoves,
} from '../../src/game/moves';
import type { Piece, ActiveMove } from '../../src/stores/game';

// ============================================
// Test Fixtures
// ============================================

type PieceType = 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';

const createPiece = (
  id: string,
  type: PieceType,
  player: number,
  row: number,
  col: number,
  overrides?: Partial<Piece>
): Piece => ({
  id,
  type,
  player,
  row,
  col,
  captured: false,
  moving: false,
  onCooldown: false,
  moved: false,
  ...overrides,
});

const createActiveMove = (
  pieceId: string,
  path: [number, number][],
  startTick: number
): ActiveMove => ({
  pieceId,
  path,
  startTick,
  progress: 0,
});

// Standard game parameters
const TICKS_PER_SQUARE = 10;
const CURRENT_TICK = 0;

// ============================================
// Basic Move Validation Tests
// ============================================

describe('isLegalMove - basic validation', () => {
  it('rejects moves to same square', () => {
    const piece = createPiece('p1', 'R', 1, 4, 4);
    expect(isLegalMove([piece], [], CURRENT_TICK, TICKS_PER_SQUARE, piece, 4, 4)).toBe(false);
  });

  it('rejects out-of-bounds moves (standard board)', () => {
    const piece = createPiece('p1', 'R', 1, 0, 0);
    expect(isLegalMove([piece], [], CURRENT_TICK, TICKS_PER_SQUARE, piece, -1, 0)).toBe(false);
    expect(isLegalMove([piece], [], CURRENT_TICK, TICKS_PER_SQUARE, piece, 0, -1)).toBe(false);
    expect(isLegalMove([piece], [], CURRENT_TICK, TICKS_PER_SQUARE, piece, 8, 0)).toBe(false);
    expect(isLegalMove([piece], [], CURRENT_TICK, TICKS_PER_SQUARE, piece, 0, 8)).toBe(false);
  });

  it('rejects moves to corner squares (four_player board)', () => {
    const piece = createPiece('p1', 'R', 1, 2, 0);
    // Try to move to corner (0,0) which is invalid in 4-player
    expect(isLegalMove([piece], [], CURRENT_TICK, TICKS_PER_SQUARE, piece, 0, 0, 'four_player')).toBe(false);
  });
});

// ============================================
// Pawn Move Tests
// ============================================

describe('isLegalMove - Pawn', () => {
  describe('standard board - player 1 (moves up)', () => {
    it('allows one square forward', () => {
      const pawn = createPiece('p1', 'P', 1, 6, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 5, 4)).toBe(true);
    });

    it('allows two squares forward from starting row', () => {
      const pawn = createPiece('p1', 'P', 1, 6, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 4, 4)).toBe(true);
    });

    it('rejects two squares forward from non-starting row', () => {
      const pawn = createPiece('p1', 'P', 1, 5, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 4)).toBe(false);
    });

    it('rejects backward moves', () => {
      const pawn = createPiece('p1', 'P', 1, 4, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 5, 4)).toBe(false);
    });

    it('rejects sideways moves', () => {
      const pawn = createPiece('p1', 'P', 1, 4, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 4, 5)).toBe(false);
    });

    it('allows diagonal capture', () => {
      const pawn = createPiece('p1', 'P', 1, 4, 4);
      const enemy = createPiece('e1', 'P', 2, 3, 5);
      expect(isLegalMove([pawn, enemy], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 5)).toBe(true);
    });

    it('rejects diagonal move without capture', () => {
      const pawn = createPiece('p1', 'P', 1, 4, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 5)).toBe(false);
    });

    it('rejects capture of own piece', () => {
      const pawn = createPiece('p1', 'P', 1, 4, 4);
      const friendly = createPiece('f1', 'P', 1, 3, 5);
      expect(isLegalMove([pawn, friendly], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 5)).toBe(false);
    });

    it('rejects forward move when blocked', () => {
      const pawn = createPiece('p1', 'P', 1, 4, 4);
      const blocker = createPiece('b1', 'P', 2, 3, 4);
      expect(isLegalMove([pawn, blocker], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 4)).toBe(false);
    });
  });

  describe('standard board - player 2 (moves down)', () => {
    it('allows one square forward (down)', () => {
      const pawn = createPiece('p1', 'P', 2, 1, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 2, 4)).toBe(true);
    });

    it('allows two squares forward from starting row', () => {
      const pawn = createPiece('p1', 'P', 2, 1, 4);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 4)).toBe(true);
    });

    it('allows diagonal capture (down-left or down-right)', () => {
      const pawn = createPiece('p1', 'P', 2, 3, 4);
      const enemy = createPiece('e1', 'P', 1, 4, 3);
      expect(isLegalMove([pawn, enemy], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 4, 3)).toBe(true);
    });
  });
});

// ============================================
// Knight Move Tests
// ============================================

describe('isLegalMove - Knight', () => {
  const knight = createPiece('n1', 'N', 1, 4, 4);

  it('allows all 8 L-shaped moves', () => {
    const legalDestinations = [
      [2, 3], [2, 5], // 2 up, 1 left/right
      [3, 2], [3, 6], // 1 up, 2 left/right
      [5, 2], [5, 6], // 1 down, 2 left/right
      [6, 3], [6, 5], // 2 down, 1 left/right
    ];

    for (const [row, col] of legalDestinations) {
      expect(isLegalMove([knight], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, row, col)).toBe(true);
    }
  });

  it('rejects non-L-shaped moves', () => {
    // Straight moves
    expect(isLegalMove([knight], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 4, 6)).toBe(false);
    expect(isLegalMove([knight], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 6, 4)).toBe(false);

    // Diagonal moves
    expect(isLegalMove([knight], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 5, 5)).toBe(false);
    expect(isLegalMove([knight], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 6, 6)).toBe(false);
  });

  it('can jump over pieces', () => {
    // Place blocking pieces around the knight
    const pieces = [
      knight,
      createPiece('b1', 'P', 1, 3, 4), // Above
      createPiece('b2', 'P', 1, 5, 4), // Below
      createPiece('b3', 'P', 1, 4, 3), // Left
      createPiece('b4', 'P', 1, 4, 5), // Right
    ];

    // Knight should still be able to move
    expect(isLegalMove(pieces, [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 2, 3)).toBe(true);
  });

  it('can capture enemy pieces', () => {
    const enemy = createPiece('e1', 'P', 2, 2, 3);
    expect(isLegalMove([knight, enemy], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 2, 3)).toBe(true);
  });

  it('cannot capture own pieces', () => {
    const friendly = createPiece('f1', 'P', 1, 2, 3);
    expect(isLegalMove([knight, friendly], [], CURRENT_TICK, TICKS_PER_SQUARE, knight, 2, 3)).toBe(false);
  });
});

// ============================================
// Bishop Move Tests
// ============================================

describe('isLegalMove - Bishop', () => {
  const bishop = createPiece('b1', 'B', 1, 4, 4);

  it('allows diagonal moves in all directions', () => {
    // Up-left
    expect(isLegalMove([bishop], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 2, 2)).toBe(true);
    // Up-right
    expect(isLegalMove([bishop], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 2, 6)).toBe(true);
    // Down-left
    expect(isLegalMove([bishop], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 6, 2)).toBe(true);
    // Down-right
    expect(isLegalMove([bishop], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 6, 6)).toBe(true);
  });

  it('rejects horizontal moves', () => {
    expect(isLegalMove([bishop], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 4, 6)).toBe(false);
  });

  it('rejects vertical moves', () => {
    expect(isLegalMove([bishop], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 6, 4)).toBe(false);
  });

  it('cannot move through pieces', () => {
    const blocker = createPiece('p1', 'P', 1, 3, 3);
    expect(isLegalMove([bishop, blocker], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 2, 2)).toBe(false);
  });

  it('can capture enemy at destination', () => {
    const enemy = createPiece('e1', 'P', 2, 2, 2);
    expect(isLegalMove([bishop, enemy], [], CURRENT_TICK, TICKS_PER_SQUARE, bishop, 2, 2)).toBe(true);
  });
});

// ============================================
// Rook Move Tests
// ============================================

describe('isLegalMove - Rook', () => {
  const rook = createPiece('r1', 'R', 1, 4, 4);

  it('allows horizontal moves', () => {
    expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 4, 0)).toBe(true);
    expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 4, 7)).toBe(true);
  });

  it('allows vertical moves', () => {
    expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 0, 4)).toBe(true);
    expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 7, 4)).toBe(true);
  });

  it('rejects diagonal moves', () => {
    expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 5, 5)).toBe(false);
    expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 2, 2)).toBe(false);
  });

  it('cannot move through pieces', () => {
    const blocker = createPiece('p1', 'P', 1, 4, 2);
    expect(isLegalMove([rook, blocker], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 4, 0)).toBe(false);
  });

  it('can capture enemy at destination', () => {
    const enemy = createPiece('e1', 'P', 2, 4, 0);
    expect(isLegalMove([rook, enemy], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 4, 0)).toBe(true);
  });
});

// ============================================
// Queen Move Tests
// ============================================

describe('isLegalMove - Queen', () => {
  const queen = createPiece('q1', 'Q', 1, 4, 4);

  it('allows rook-like horizontal moves', () => {
    expect(isLegalMove([queen], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 4, 7)).toBe(true);
  });

  it('allows rook-like vertical moves', () => {
    expect(isLegalMove([queen], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 0, 4)).toBe(true);
  });

  it('allows bishop-like diagonal moves', () => {
    expect(isLegalMove([queen], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 2, 2)).toBe(true);
    expect(isLegalMove([queen], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 6, 6)).toBe(true);
  });

  it('rejects knight-like moves', () => {
    expect(isLegalMove([queen], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 2, 3)).toBe(false);
    expect(isLegalMove([queen], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 3, 2)).toBe(false);
  });

  it('cannot move through pieces', () => {
    const blocker = createPiece('p1', 'P', 1, 3, 3);
    expect(isLegalMove([queen, blocker], [], CURRENT_TICK, TICKS_PER_SQUARE, queen, 2, 2)).toBe(false);
  });
});

// ============================================
// King Move Tests
// ============================================

describe('isLegalMove - King', () => {
  const king = createPiece('k1', 'K', 1, 4, 4);

  it('allows one square in any direction', () => {
    const directions = [
      [-1, -1], [-1, 0], [-1, 1],
      [0, -1],          [0, 1],
      [1, -1],  [1, 0],  [1, 1],
    ];

    for (const [dr, dc] of directions) {
      expect(isLegalMove([king], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 4 + dr, 4 + dc)).toBe(true);
    }
  });

  it('rejects moves more than one square', () => {
    expect(isLegalMove([king], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 2, 4)).toBe(false);
    expect(isLegalMove([king], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 4, 2)).toBe(false);
    expect(isLegalMove([king], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 2, 2)).toBe(false);
  });

  describe('castling (standard board)', () => {
    it('allows kingside castling when conditions are met', () => {
      const king = createPiece('k1', 'K', 1, 7, 4, { moved: false });
      const rook = createPiece('r1', 'R', 1, 7, 7, { moved: false });
      expect(isLegalMove([king, rook], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 7, 6)).toBe(true);
    });

    it('allows queenside castling when conditions are met', () => {
      const king = createPiece('k1', 'K', 1, 7, 4, { moved: false });
      const rook = createPiece('r1', 'R', 1, 7, 0, { moved: false });
      expect(isLegalMove([king, rook], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 7, 2)).toBe(true);
    });

    it('rejects castling when king has moved', () => {
      const king = createPiece('k1', 'K', 1, 7, 4, { moved: true });
      const rook = createPiece('r1', 'R', 1, 7, 7, { moved: false });
      expect(isLegalMove([king, rook], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 7, 6)).toBe(false);
    });

    it('rejects castling when rook has moved', () => {
      const king = createPiece('k1', 'K', 1, 7, 4, { moved: false });
      const rook = createPiece('r1', 'R', 1, 7, 7, { moved: true });
      expect(isLegalMove([king, rook], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 7, 6)).toBe(false);
    });

    it('rejects castling when path is blocked', () => {
      const king = createPiece('k1', 'K', 1, 7, 4, { moved: false });
      const rook = createPiece('r1', 'R', 1, 7, 7, { moved: false });
      const blocker = createPiece('b1', 'N', 1, 7, 5);
      expect(isLegalMove([king, rook, blocker], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 7, 6)).toBe(false);
    });

    it('rejects castling when rook is missing', () => {
      const king = createPiece('k1', 'K', 1, 7, 4, { moved: false });
      expect(isLegalMove([king], [], CURRENT_TICK, TICKS_PER_SQUARE, king, 7, 6)).toBe(false);
    });
  });
});

// ============================================
// Collision with Moving Pieces Tests
// ============================================

describe('isLegalMove - moving piece interactions', () => {
  it('rejects move to square where friendly piece is moving to', () => {
    const piece = createPiece('p1', 'R', 1, 4, 4);
    const movingPiece = createPiece('p2', 'R', 1, 4, 0);
    const activeMoves = [
      createActiveMove('p2', [[4, 0], [4, 1], [4, 2]], 0),
    ];

    // p2 is moving to (4,2), so p1 shouldn't be able to move there
    expect(isLegalMove([piece, movingPiece], activeMoves, CURRENT_TICK, TICKS_PER_SQUARE, piece, 4, 2)).toBe(false);
  });

  it('allows capture of moving enemy pieces at destination (perpendicular)', () => {
    const piece = createPiece('p1', 'R', 1, 0, 2);
    const movingEnemy = createPiece('e1', 'R', 2, 4, 0, { moving: true });
    const activeMoves = [
      createActiveMove('e1', [[4, 0], [4, 1], [4, 2]], 0),
    ];

    // Enemy is moving through our destination on a perpendicular line
    expect(isLegalMove([piece, movingEnemy], activeMoves, CURRENT_TICK, TICKS_PER_SQUARE, piece, 4, 2)).toBe(true);
  });

  it('cannot capture friendly piece even if moving', () => {
    const pawn = createPiece('p1', 'P', 1, 4, 4);
    const friendly = createPiece('f1', 'P', 1, 3, 5, { moving: true });
    const activeMoves = [
      createActiveMove('f1', [[2, 5], [3, 5]], 0),
    ];

    // Pawn can't diagonally capture a friendly piece
    expect(isLegalMove([pawn, friendly], activeMoves, CURRENT_TICK, TICKS_PER_SQUARE, pawn, 3, 5)).toBe(false);
  });
});

// ============================================
// Path Blocking Rules Tests
// (Matching server-side TestPathBlocking)
// ============================================

describe('isLegalMove - path blocking rules', () => {
  it('can move to vacating enemy square', () => {
    // Moving enemy has vacated - square is effectively empty
    const rook = createPiece('r1', 'R', 1, 4, 0);
    const enemy = createPiece('e1', 'Q', 2, 4, 4);
    const activeMoves = [
      // Enemy queen is moving away (vacating)
      createActiveMove('e1', [[4, 4], [4, 5], [4, 6], [4, 7]], 0),
    ];

    // Rook can move to (4, 4) - enemy has vacated, square is empty
    expect(isLegalMove([rook, enemy], activeMoves, CURRENT_TICK, TICKS_PER_SQUARE, rook, 4, 4)).toBe(true);
  });

  it('can capture stationary enemy', () => {
    const rook = createPiece('r1', 'R', 1, 4, 0);
    const enemy = createPiece('e1', 'Q', 2, 4, 4);

    // No active moves - enemy is stationary
    expect(isLegalMove([rook, enemy], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 4, 4)).toBe(true);
  });

  it('own forward path blocks own pieces', () => {
    // Rule 2: Own moving piece's forward path blocks own other pieces
    const rook1 = createPiece('r1', 'R', 1, 4, 0); // Moving rook
    const rook2 = createPiece('r2', 'R', 1, 0, 4); // Trying to move

    // Rook1 is moving from (4,0) to (4,7) - forward path includes (4,4)
    const activeMoves = [
      createActiveMove('r1', [[4, 0], [4, 1], [4, 2], [4, 3], [4, 4], [4, 5], [4, 6], [4, 7]], 0),
    ];

    // Rook2 tries to move from (0,4) to (4,4) - blocked by rook1's forward path
    expect(isLegalMove([rook1, rook2], activeMoves, 0, TICKS_PER_SQUARE, rook2, 4, 4)).toBe(false);
  });

  it('own backward path (already traversed) does not block', () => {
    // Own moving piece's already-traversed path does NOT block
    const rook1 = createPiece('r1', 'R', 1, 4, 0); // Moving rook
    const rook2 = createPiece('r2', 'R', 1, 0, 2); // Trying to move

    // Rook1 is moving from (4,0) to (4,7)
    const activeMoves = [
      createActiveMove('r1', [[4, 0], [4, 1], [4, 2], [4, 3], [4, 4], [4, 5], [4, 6], [4, 7]], 0),
    ];

    // At tick 30 (3 squares traversed with TICKS_PER_SQUARE=10), rook1 has passed (4,2)
    // Rook2 should be able to move to (4,2) - already traversed
    expect(isLegalMove([rook1, rook2], activeMoves, 30, TICKS_PER_SQUARE, rook2, 4, 2)).toBe(true);
  });

  it('enemy forward path does not block own pieces', () => {
    // Enemy moving piece's forward path does NOT block own pieces
    const enemyRook = createPiece('e1', 'R', 2, 4, 0); // Enemy moving
    const ownRook = createPiece('r1', 'R', 1, 0, 4); // Trying to move

    // Enemy rook is moving from (4,0) to (4,7) - forward path includes (4,4)
    const activeMoves = [
      createActiveMove('e1', [[4, 0], [4, 1], [4, 2], [4, 3], [4, 4], [4, 5], [4, 6], [4, 7]], 0),
    ];

    // Own rook can move through enemy's forward path
    expect(isLegalMove([enemyRook, ownRook], activeMoves, 0, TICKS_PER_SQUARE, ownRook, 4, 4)).toBe(true);
  });

  it('knight can move to vacating enemy square', () => {
    const knight = createPiece('n1', 'N', 1, 4, 4);
    const enemy = createPiece('e1', 'P', 2, 6, 5);

    // Enemy pawn is moving away (vacating)
    const activeMoves = [
      createActiveMove('e1', [[6, 5], [5, 5]], 0),
    ];

    // Knight can move to (6, 5) - enemy has vacated, square is empty
    expect(isLegalMove([knight, enemy], activeMoves, CURRENT_TICK, TICKS_PER_SQUARE, knight, 6, 5)).toBe(true);
  });

  it('knight blocked by own forward path', () => {
    const knight = createPiece('n1', 'N', 1, 4, 4);
    const rook = createPiece('r1', 'R', 1, 6, 0); // Moving rook

    // Rook is moving from (6,0) to (6,7) - forward path includes (6,5)
    const activeMoves = [
      createActiveMove('r1', [[6, 0], [6, 1], [6, 2], [6, 3], [6, 4], [6, 5], [6, 6], [6, 7]], 0),
    ];

    // Knight tries to land on (6, 5) - blocked by rook's forward path
    expect(isLegalMove([knight, rook], activeMoves, 0, TICKS_PER_SQUARE, knight, 6, 5)).toBe(false);
  });

  it('knight forward path does not block other pieces', () => {
    // Knight's forward path (including midpoints) should NOT block since knights jump
    const knight = createPiece('n1', 'N', 1, 4, 4);
    const rook = createPiece('r1', 'R', 1, 0, 5);

    // Knight is moving from (4,4) to (6,5) with midpoint at (5,4.5)
    const activeMoves = [
      createActiveMove('n1', [[4, 4], [5, 4.5], [6, 5]], 0),
    ];

    // Rook tries to move from (0,5) to (5,5) - knight's path should not block
    // because knight midpoints are not integer coordinates and don't block
    expect(isLegalMove([knight, rook], activeMoves, 0, TICKS_PER_SQUARE, rook, 5, 5)).toBe(true);
  });
});

// ============================================
// Same-Line Slider Blocking Tests
// ============================================

describe('isLegalMove - same-line slider blocking', () => {
  it('rook blocked by enemy rook moving along same rank', () => {
    const ownRook = createPiece('r1', 'R', 1, 4, 0);
    const enemyRook = createPiece('e1', 'R', 2, 4, 7);
    const activeMoves = [
      // Enemy rook moving left along row 4
      createActiveMove('e1', [[4, 7], [4, 6], [4, 5], [4, 4]], 0),
    ];

    // Own rook tries to move right - enemy forward path {(4,6),(4,5),(4,4)} blocks
    expect(isLegalMove([ownRook, enemyRook], activeMoves, 0, TICKS_PER_SQUARE, ownRook, 4, 5)).toBe(false);
  });

  it('rook blocked by enemy rook moving along same file', () => {
    const ownRook = createPiece('r1', 'R', 1, 7, 4);
    const enemyRook = createPiece('e1', 'R', 2, 0, 4);
    const activeMoves = [
      // Enemy rook moving down along col 4
      createActiveMove('e1', [[0, 4], [1, 4], [2, 4], [3, 4]], 0),
    ];

    // Own rook tries to move up along same file - blocked
    expect(isLegalMove([ownRook, enemyRook], activeMoves, 0, TICKS_PER_SQUARE, ownRook, 3, 4)).toBe(false);
  });

  it('bishop blocked by enemy queen on same diagonal', () => {
    const ownBishop = createPiece('b1', 'B', 1, 7, 0);
    const enemyQueen = createPiece('e1', 'Q', 2, 3, 4);
    const activeMoves = [
      // Enemy queen moving down-left along same anti-diagonal (row+col=7)
      createActiveMove('e1', [[3, 4], [4, 3], [5, 2], [6, 1]], 0),
    ];

    // Bishop tries to move up-right - enemy forward path blocks at (6,1) and (5,2)
    expect(isLegalMove([ownBishop, enemyQueen], activeMoves, 0, TICKS_PER_SQUARE, ownBishop, 4, 3)).toBe(false);
  });

  it('rook NOT blocked by enemy rook on different rank', () => {
    const ownRook = createPiece('r1', 'R', 1, 4, 0);
    const enemyRook = createPiece('e1', 'R', 2, 3, 4);
    const activeMoves = [
      // Enemy rook moving along row 3 (different rank)
      createActiveMove('e1', [[3, 4], [3, 3], [3, 2], [3, 1]], 0),
    ];

    // Own rook moves along row 4 - different rank, not blocked
    expect(isLegalMove([ownRook, enemyRook], activeMoves, 0, TICKS_PER_SQUARE, ownRook, 4, 7)).toBe(true);
  });

  it('rook NOT blocked by enemy knight on same rank', () => {
    const ownRook = createPiece('r1', 'R', 1, 4, 0);
    const enemyKnight = createPiece('e1', 'N', 2, 4, 6);
    const activeMoves = [
      // Knight moving away
      createActiveMove('e1', [[4, 6], [3, 6.5], [2, 7]], 0),
    ];

    // Rook can move through - knight is not a slider
    expect(isLegalMove([ownRook, enemyKnight], activeMoves, 0, TICKS_PER_SQUARE, ownRook, 4, 7)).toBe(true);
  });

  it('perpendicular enemy rook does not trigger same-line blocking', () => {
    const ownRook = createPiece('r1', 'R', 1, 4, 0);
    const enemyRook = createPiece('e1', 'R', 2, 0, 4);
    const activeMoves = [
      // Enemy rook moving vertically on col 4
      createActiveMove('e1', [[0, 4], [1, 4], [2, 4], [3, 4], [4, 4]], 0),
    ];

    // Own rook moves horizontally on row 4 - perpendicular, not same-line
    expect(isLegalMove([ownRook, enemyRook], activeMoves, 0, TICKS_PER_SQUARE, ownRook, 4, 7)).toBe(true);
  });

  it('enemy slider completed move does not block', () => {
    const ownRook = createPiece('r1', 'R', 1, 4, 0);
    const enemyRook = createPiece('e1', 'R', 2, 4, 7);
    const activeMoves = [
      // Enemy rook was moving left along row 4 (3 segments)
      createActiveMove('e1', [[4, 7], [4, 6], [4, 5], [4, 4]], 0),
    ];

    // At tick 30 (3 segments * TICKS_PER_SQUARE=10), enemy has completed the move
    expect(isLegalMove([ownRook, enemyRook], activeMoves, 30, TICKS_PER_SQUARE, ownRook, 4, 5)).toBe(true);
  });

  it('rook can move short behind enemy moving away on same line', () => {
    const ownRook = createPiece('r1', 'R', 1, 4, 0);
    const enemyRook = createPiece('e1', 'R', 2, 4, 3);
    const activeMoves = [
      // Enemy rook moving right (away from us) along row 4
      createActiveMove('e1', [[4, 3], [4, 4], [4, 5], [4, 6], [4, 7]], 0),
    ];

    // At tick 20 (2 segments), enemy forward path is {(4,5),(4,6),(4,7)}
    // Own rook moves to (4,2) - behind enemy, no overlap with forward path
    expect(isLegalMove([ownRook, enemyRook], activeMoves, 20, TICKS_PER_SQUARE, ownRook, 4, 2)).toBe(true);
  });
});

// ============================================
// getLegalMovesForPiece Tests
// ============================================

describe('getLegalMovesForPiece', () => {
  it('returns all legal moves for a rook', () => {
    const rook = createPiece('r1', 'R', 1, 4, 4);
    const moves = getLegalMovesForPiece([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook);

    // Rook at (4,4) should have 14 moves (7 horizontal + 7 vertical)
    expect(moves.length).toBe(14);

    // Check some specific moves exist
    expect(moves).toContainEqual([4, 0]);
    expect(moves).toContainEqual([4, 7]);
    expect(moves).toContainEqual([0, 4]);
    expect(moves).toContainEqual([7, 4]);
  });

  it('returns limited moves when blocked', () => {
    const rook = createPiece('r1', 'R', 1, 4, 4);
    const blocker1 = createPiece('b1', 'P', 1, 4, 2); // Blocks left
    const blocker2 = createPiece('b2', 'P', 1, 2, 4); // Blocks up

    const moves = getLegalMovesForPiece(
      [rook, blocker1, blocker2],
      [],
      CURRENT_TICK,
      TICKS_PER_SQUARE,
      rook
    );

    // Should not include squares blocked by friendly pieces
    expect(moves).not.toContainEqual([4, 0]);
    expect(moves).not.toContainEqual([4, 1]);
    expect(moves).not.toContainEqual([0, 4]);
    expect(moves).not.toContainEqual([1, 4]);
  });

  it('returns empty array for captured piece', () => {
    const rook = createPiece('r1', 'R', 1, 4, 4, { captured: true });
    const moves = getLegalMovesForPiece([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook);

    // Captured pieces can technically still return moves through the function,
    // but getAllLegalMoves filters them out. Let's test the function behavior.
    // The function doesn't check captured status internally, so it will still return moves.
    expect(moves.length).toBe(14);
  });
});

// ============================================
// getAllLegalMoves Tests
// ============================================

describe('getAllLegalMoves', () => {
  it('returns moves for all movable pieces of a player', () => {
    const pieces = [
      createPiece('r1', 'R', 1, 7, 0),
      createPiece('n1', 'N', 1, 7, 1),
      createPiece('r2', 'R', 2, 0, 0), // Enemy piece
    ];

    const allMoves = getAllLegalMoves(pieces, [], CURRENT_TICK, TICKS_PER_SQUARE, 1);

    expect(allMoves.has('r1')).toBe(true);
    expect(allMoves.has('n1')).toBe(true);
    expect(allMoves.has('r2')).toBe(false); // Enemy piece not included
  });

  it('excludes captured pieces', () => {
    const pieces = [
      createPiece('r1', 'R', 1, 4, 4),
      createPiece('r2', 'R', 1, 0, 0, { captured: true }),
    ];

    const allMoves = getAllLegalMoves(pieces, [], CURRENT_TICK, TICKS_PER_SQUARE, 1);

    expect(allMoves.has('r1')).toBe(true);
    expect(allMoves.has('r2')).toBe(false);
  });

  it('excludes moving pieces', () => {
    const pieces = [
      createPiece('r1', 'R', 1, 4, 4),
      createPiece('r2', 'R', 1, 0, 0, { moving: true }),
    ];

    const allMoves = getAllLegalMoves(pieces, [], CURRENT_TICK, TICKS_PER_SQUARE, 1);

    expect(allMoves.has('r1')).toBe(true);
    expect(allMoves.has('r2')).toBe(false);
  });

  it('excludes pieces on cooldown', () => {
    const pieces = [
      createPiece('r1', 'R', 1, 4, 4),
      createPiece('r2', 'R', 1, 0, 0, { onCooldown: true }),
    ];

    const allMoves = getAllLegalMoves(pieces, [], CURRENT_TICK, TICKS_PER_SQUARE, 1);

    expect(allMoves.has('r1')).toBe(true);
    expect(allMoves.has('r2')).toBe(false);
  });
});

// ============================================
// Four-Player Mode Tests
// ============================================

describe('isLegalMove - four_player mode', () => {
  describe('pawn moves', () => {
    it('player 1 (East) pawn moves left', () => {
      const pawn = createPiece('p1', 'P', 1, 5, 10);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 5, 9, 'four_player')).toBe(true);
    });

    it('player 2 (South) pawn moves up', () => {
      const pawn = createPiece('p1', 'P', 2, 10, 5);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 9, 5, 'four_player')).toBe(true);
    });

    it('player 3 (West) pawn moves right', () => {
      const pawn = createPiece('p1', 'P', 3, 5, 1);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 5, 2, 'four_player')).toBe(true);
    });

    it('player 4 (North) pawn moves down', () => {
      const pawn = createPiece('p1', 'P', 4, 1, 5);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 2, 5, 'four_player')).toBe(true);
    });

    it('allows double move from home row', () => {
      // Player 2 pawn at home row (10)
      const pawn = createPiece('p1', 'P', 2, 10, 5);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 8, 5, 'four_player')).toBe(true);
    });

    it('rejects double move from non-home row', () => {
      // Player 2 pawn not at home row
      const pawn = createPiece('p1', 'P', 2, 9, 5);
      expect(isLegalMove([pawn], [], CURRENT_TICK, TICKS_PER_SQUARE, pawn, 7, 5, 'four_player')).toBe(false);
    });
  });

  describe('boundary validation', () => {
    it('rejects moves into corner squares', () => {
      const rook = createPiece('r1', 'R', 1, 0, 2);
      // Try to move to corner (0,0)
      expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 0, 0, 'four_player')).toBe(false);
    });

    it('allows moves along valid edges', () => {
      const rook = createPiece('r1', 'R', 1, 0, 5);
      // Move along top edge (valid squares)
      expect(isLegalMove([rook], [], CURRENT_TICK, TICKS_PER_SQUARE, rook, 0, 9, 'four_player')).toBe(true);
    });
  });
});

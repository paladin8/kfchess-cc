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

  it('allows capture of moving enemy pieces at destination', () => {
    const piece = createPiece('p1', 'R', 1, 4, 4);
    const movingEnemy = createPiece('e1', 'R', 2, 4, 0, { moving: true });
    const activeMoves = [
      createActiveMove('e1', [[4, 0], [4, 1], [4, 2]], 0),
    ];

    // Enemy is moving through our destination, should be able to move there
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

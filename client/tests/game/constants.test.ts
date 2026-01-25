import { describe, it, expect } from 'vitest';
import {
  isCornerSquare,
  isValidSquare,
  getSquareColor,
  getPieceRotation,
  transformToViewCoords,
  transformToGameCoords,
  BOARD_COLORS,
  BOARD_DIMENSIONS,
  type Coords,
} from '../../src/game/constants';

// ============================================
// isCornerSquare Tests
// ============================================

describe('isCornerSquare', () => {
  describe('top-left corner (2x2)', () => {
    it('returns true for (0,0)', () => {
      expect(isCornerSquare(0, 0)).toBe(true);
    });

    it('returns true for (0,1)', () => {
      expect(isCornerSquare(0, 1)).toBe(true);
    });

    it('returns true for (1,0)', () => {
      expect(isCornerSquare(1, 0)).toBe(true);
    });

    it('returns true for (1,1)', () => {
      expect(isCornerSquare(1, 1)).toBe(true);
    });

    it('returns false for (0,2) - just outside corner', () => {
      expect(isCornerSquare(0, 2)).toBe(false);
    });

    it('returns false for (2,0) - just outside corner', () => {
      expect(isCornerSquare(2, 0)).toBe(false);
    });
  });

  describe('top-right corner (2x2)', () => {
    it('returns true for (0,10)', () => {
      expect(isCornerSquare(0, 10)).toBe(true);
    });

    it('returns true for (0,11)', () => {
      expect(isCornerSquare(0, 11)).toBe(true);
    });

    it('returns true for (1,10)', () => {
      expect(isCornerSquare(1, 10)).toBe(true);
    });

    it('returns true for (1,11)', () => {
      expect(isCornerSquare(1, 11)).toBe(true);
    });

    it('returns false for (0,9) - just outside corner', () => {
      expect(isCornerSquare(0, 9)).toBe(false);
    });
  });

  describe('bottom-left corner (2x2)', () => {
    it('returns true for (10,0)', () => {
      expect(isCornerSquare(10, 0)).toBe(true);
    });

    it('returns true for (10,1)', () => {
      expect(isCornerSquare(10, 1)).toBe(true);
    });

    it('returns true for (11,0)', () => {
      expect(isCornerSquare(11, 0)).toBe(true);
    });

    it('returns true for (11,1)', () => {
      expect(isCornerSquare(11, 1)).toBe(true);
    });

    it('returns false for (9,0) - just outside corner', () => {
      expect(isCornerSquare(9, 0)).toBe(false);
    });
  });

  describe('bottom-right corner (2x2)', () => {
    it('returns true for (10,10)', () => {
      expect(isCornerSquare(10, 10)).toBe(true);
    });

    it('returns true for (10,11)', () => {
      expect(isCornerSquare(10, 11)).toBe(true);
    });

    it('returns true for (11,10)', () => {
      expect(isCornerSquare(11, 10)).toBe(true);
    });

    it('returns true for (11,11)', () => {
      expect(isCornerSquare(11, 11)).toBe(true);
    });
  });

  describe('non-corner squares', () => {
    it('returns false for center squares', () => {
      expect(isCornerSquare(5, 5)).toBe(false);
      expect(isCornerSquare(6, 6)).toBe(false);
    });

    it('returns false for edge squares (not corners)', () => {
      expect(isCornerSquare(0, 5)).toBe(false);
      expect(isCornerSquare(5, 0)).toBe(false);
      expect(isCornerSquare(11, 5)).toBe(false);
      expect(isCornerSquare(5, 11)).toBe(false);
    });
  });
});

// ============================================
// isValidSquare Tests
// ============================================

describe('isValidSquare', () => {
  describe('standard board (8x8)', () => {
    it('returns true for all corners', () => {
      expect(isValidSquare(0, 0, 'standard')).toBe(true);
      expect(isValidSquare(0, 7, 'standard')).toBe(true);
      expect(isValidSquare(7, 0, 'standard')).toBe(true);
      expect(isValidSquare(7, 7, 'standard')).toBe(true);
    });

    it('returns true for center squares', () => {
      expect(isValidSquare(3, 3, 'standard')).toBe(true);
      expect(isValidSquare(4, 4, 'standard')).toBe(true);
    });

    it('returns false for out-of-bounds coordinates', () => {
      expect(isValidSquare(-1, 0, 'standard')).toBe(false);
      expect(isValidSquare(0, -1, 'standard')).toBe(false);
      expect(isValidSquare(8, 0, 'standard')).toBe(false);
      expect(isValidSquare(0, 8, 'standard')).toBe(false);
    });
  });

  describe('four_player board (12x12)', () => {
    it('returns false for corner squares', () => {
      // Top-left corner
      expect(isValidSquare(0, 0, 'four_player')).toBe(false);
      expect(isValidSquare(1, 1, 'four_player')).toBe(false);

      // Top-right corner
      expect(isValidSquare(0, 10, 'four_player')).toBe(false);
      expect(isValidSquare(1, 11, 'four_player')).toBe(false);

      // Bottom-left corner
      expect(isValidSquare(10, 0, 'four_player')).toBe(false);
      expect(isValidSquare(11, 1, 'four_player')).toBe(false);

      // Bottom-right corner
      expect(isValidSquare(10, 10, 'four_player')).toBe(false);
      expect(isValidSquare(11, 11, 'four_player')).toBe(false);
    });

    it('returns true for valid edge squares (outside corners)', () => {
      // Top edge (not corners)
      expect(isValidSquare(0, 2, 'four_player')).toBe(true);
      expect(isValidSquare(0, 5, 'four_player')).toBe(true);
      expect(isValidSquare(0, 9, 'four_player')).toBe(true);

      // Left edge (not corners)
      expect(isValidSquare(2, 0, 'four_player')).toBe(true);
      expect(isValidSquare(5, 0, 'four_player')).toBe(true);
    });

    it('returns true for center squares', () => {
      expect(isValidSquare(5, 5, 'four_player')).toBe(true);
      expect(isValidSquare(6, 6, 'four_player')).toBe(true);
    });

    it('returns false for out-of-bounds coordinates', () => {
      expect(isValidSquare(-1, 0, 'four_player')).toBe(false);
      expect(isValidSquare(12, 0, 'four_player')).toBe(false);
      expect(isValidSquare(0, 12, 'four_player')).toBe(false);
    });
  });
});

// ============================================
// getSquareColor Tests
// ============================================

describe('getSquareColor', () => {
  describe('standard board', () => {
    it('returns light color for (0,0)', () => {
      expect(getSquareColor(0, 0, 'standard')).toBe(BOARD_COLORS.light);
    });

    it('returns dark color for (0,1)', () => {
      expect(getSquareColor(0, 1, 'standard')).toBe(BOARD_COLORS.dark);
    });

    it('returns dark color for (1,0)', () => {
      expect(getSquareColor(1, 0, 'standard')).toBe(BOARD_COLORS.dark);
    });

    it('returns light color for (1,1)', () => {
      expect(getSquareColor(1, 1, 'standard')).toBe(BOARD_COLORS.light);
    });

    it('follows checkerboard pattern', () => {
      // Check a few squares follow (row + col) % 2 pattern
      expect(getSquareColor(3, 5, 'standard')).toBe(BOARD_COLORS.light); // 3+5=8, even
      expect(getSquareColor(3, 4, 'standard')).toBe(BOARD_COLORS.dark);  // 3+4=7, odd
    });
  });

  describe('four_player board', () => {
    it('returns invalid color for corner squares', () => {
      expect(getSquareColor(0, 0, 'four_player')).toBe(BOARD_COLORS.invalid);
      expect(getSquareColor(1, 1, 'four_player')).toBe(BOARD_COLORS.invalid);
      expect(getSquareColor(10, 10, 'four_player')).toBe(BOARD_COLORS.invalid);
    });

    it('returns checkerboard colors for non-corner squares', () => {
      expect(getSquareColor(0, 2, 'four_player')).toBe(BOARD_COLORS.light);
      expect(getSquareColor(0, 3, 'four_player')).toBe(BOARD_COLORS.dark);
    });
  });
});

// ============================================
// getPieceRotation Tests
// ============================================

describe('getPieceRotation', () => {
  describe('standard board', () => {
    it('returns 0 for player 1 (bottom, faces up)', () => {
      expect(getPieceRotation(1, 'standard')).toBe(0);
    });

    it('returns PI for player 2 (top, faces down)', () => {
      expect(getPieceRotation(2, 'standard')).toBe(Math.PI);
    });
  });

  describe('four_player board', () => {
    it('returns -PI/2 for player 1 (East, faces left)', () => {
      expect(getPieceRotation(1, 'four_player')).toBe(-Math.PI / 2);
    });

    it('returns 0 for player 2 (South, faces up)', () => {
      expect(getPieceRotation(2, 'four_player')).toBe(0);
    });

    it('returns PI/2 for player 3 (West, faces right)', () => {
      expect(getPieceRotation(3, 'four_player')).toBe(Math.PI / 2);
    });

    it('returns PI for player 4 (North, faces down)', () => {
      expect(getPieceRotation(4, 'four_player')).toBe(Math.PI);
    });

    it('returns 0 for unknown player', () => {
      expect(getPieceRotation(5, 'four_player')).toBe(0);
    });
  });
});

// ============================================
// transformToViewCoords Tests
// ============================================

describe('transformToViewCoords', () => {
  describe('standard board', () => {
    it('returns unchanged coords for player 1 (no rotation)', () => {
      const coords: Coords = { row: 3, col: 4 };
      expect(transformToViewCoords(coords, 1, 'standard')).toEqual({ row: 3, col: 4 });
    });

    it('rotates 180° for player 2', () => {
      // (0,0) -> (7,7), (3,4) -> (4,3), (7,7) -> (0,0)
      expect(transformToViewCoords({ row: 0, col: 0 }, 2, 'standard')).toEqual({ row: 7, col: 7 });
      expect(transformToViewCoords({ row: 3, col: 4 }, 2, 'standard')).toEqual({ row: 4, col: 3 });
      expect(transformToViewCoords({ row: 7, col: 7 }, 2, 'standard')).toEqual({ row: 0, col: 0 });
    });

    it('keeps center relatively stable for 180° rotation', () => {
      // Center of 8x8 is around (3.5, 3.5)
      // (3,3) -> (4,4), (4,4) -> (3,3)
      expect(transformToViewCoords({ row: 3, col: 3 }, 2, 'standard')).toEqual({ row: 4, col: 4 });
      expect(transformToViewCoords({ row: 4, col: 4 }, 2, 'standard')).toEqual({ row: 3, col: 3 });
    });
  });

  describe('four_player board', () => {
    it('returns unchanged coords for player 2 (no rotation)', () => {
      const coords: Coords = { row: 5, col: 6 };
      expect(transformToViewCoords(coords, 2, 'four_player')).toEqual({ row: 5, col: 6 });
    });

    it('rotates 90° CW for player 1 (East)', () => {
      // (row, col) -> (col, maxIndex - row)
      expect(transformToViewCoords({ row: 0, col: 0 }, 1, 'four_player')).toEqual({ row: 0, col: 11 });
      expect(transformToViewCoords({ row: 0, col: 11 }, 1, 'four_player')).toEqual({ row: 11, col: 11 });
      expect(transformToViewCoords({ row: 5, col: 3 }, 1, 'four_player')).toEqual({ row: 3, col: 6 });
    });

    it('rotates 90° CCW for player 3 (West)', () => {
      // (row, col) -> (maxIndex - col, row)
      expect(transformToViewCoords({ row: 0, col: 0 }, 3, 'four_player')).toEqual({ row: 11, col: 0 });
      expect(transformToViewCoords({ row: 0, col: 11 }, 3, 'four_player')).toEqual({ row: 0, col: 0 });
      expect(transformToViewCoords({ row: 5, col: 3 }, 3, 'four_player')).toEqual({ row: 8, col: 5 });
    });

    it('rotates 180° for player 4 (North)', () => {
      // (row, col) -> (maxIndex - row, maxIndex - col)
      expect(transformToViewCoords({ row: 0, col: 0 }, 4, 'four_player')).toEqual({ row: 11, col: 11 });
      expect(transformToViewCoords({ row: 11, col: 11 }, 4, 'four_player')).toEqual({ row: 0, col: 0 });
      expect(transformToViewCoords({ row: 5, col: 3 }, 4, 'four_player')).toEqual({ row: 6, col: 8 });
    });

    it('returns unchanged for unknown player (spectator)', () => {
      const coords: Coords = { row: 5, col: 6 };
      expect(transformToViewCoords(coords, 0, 'four_player')).toEqual({ row: 5, col: 6 });
      expect(transformToViewCoords(coords, 5, 'four_player')).toEqual({ row: 5, col: 6 });
    });
  });
});

// ============================================
// transformToGameCoords Tests
// ============================================

describe('transformToGameCoords', () => {
  describe('standard board', () => {
    it('returns unchanged coords for player 1', () => {
      const coords: Coords = { row: 3, col: 4 };
      expect(transformToGameCoords(coords, 1, 'standard')).toEqual({ row: 3, col: 4 });
    });

    it('is inverse of transformToViewCoords for player 2', () => {
      // 180° rotation is self-inverse
      expect(transformToGameCoords({ row: 7, col: 7 }, 2, 'standard')).toEqual({ row: 0, col: 0 });
      expect(transformToGameCoords({ row: 4, col: 3 }, 2, 'standard')).toEqual({ row: 3, col: 4 });
    });
  });

  describe('four_player board', () => {
    it('returns unchanged coords for player 2', () => {
      const coords: Coords = { row: 5, col: 6 };
      expect(transformToGameCoords(coords, 2, 'four_player')).toEqual({ row: 5, col: 6 });
    });

    it('is inverse of transformToViewCoords for player 1', () => {
      // 90° CW inverse is 90° CCW: (row, col) -> (maxIndex - col, row)
      expect(transformToGameCoords({ row: 0, col: 11 }, 1, 'four_player')).toEqual({ row: 0, col: 0 });
      expect(transformToGameCoords({ row: 11, col: 11 }, 1, 'four_player')).toEqual({ row: 0, col: 11 });
      expect(transformToGameCoords({ row: 3, col: 6 }, 1, 'four_player')).toEqual({ row: 5, col: 3 });
    });

    it('is inverse of transformToViewCoords for player 3', () => {
      // 90° CCW inverse is 90° CW: (row, col) -> (col, maxIndex - row)
      expect(transformToGameCoords({ row: 11, col: 0 }, 3, 'four_player')).toEqual({ row: 0, col: 0 });
      expect(transformToGameCoords({ row: 0, col: 0 }, 3, 'four_player')).toEqual({ row: 0, col: 11 });
      expect(transformToGameCoords({ row: 8, col: 5 }, 3, 'four_player')).toEqual({ row: 5, col: 3 });
    });

    it('is self-inverse for player 4 (180°)', () => {
      expect(transformToGameCoords({ row: 11, col: 11 }, 4, 'four_player')).toEqual({ row: 0, col: 0 });
      expect(transformToGameCoords({ row: 6, col: 8 }, 4, 'four_player')).toEqual({ row: 5, col: 3 });
    });
  });

  describe('round-trip consistency', () => {
    const testCoords: Coords[] = [
      { row: 0, col: 0 },
      { row: 5, col: 5 },
      { row: 3, col: 7 },
      { row: 11, col: 2 },
    ];

    it('game -> view -> game returns original for all players (four_player)', () => {
      for (const player of [1, 2, 3, 4]) {
        for (const coords of testCoords) {
          const view = transformToViewCoords(coords, player, 'four_player');
          const game = transformToGameCoords(view, player, 'four_player');
          expect(game).toEqual(coords);
        }
      }
    });

    it('view -> game -> view returns original for all players (four_player)', () => {
      for (const player of [1, 2, 3, 4]) {
        for (const coords of testCoords) {
          const game = transformToGameCoords(coords, player, 'four_player');
          const view = transformToViewCoords(game, player, 'four_player');
          expect(view).toEqual(coords);
        }
      }
    });

    it('game -> view -> game returns original for standard board', () => {
      const standardCoords: Coords[] = [
        { row: 0, col: 0 },
        { row: 3, col: 4 },
        { row: 7, col: 7 },
      ];

      for (const player of [1, 2]) {
        for (const coords of standardCoords) {
          const view = transformToViewCoords(coords, player, 'standard');
          const game = transformToGameCoords(view, player, 'standard');
          expect(game).toEqual(coords);
        }
      }
    });
  });
});

// ============================================
// Constants Validation Tests
// ============================================

describe('BOARD_DIMENSIONS', () => {
  it('has correct standard dimensions', () => {
    expect(BOARD_DIMENSIONS.standard).toEqual({ width: 8, height: 8 });
  });

  it('has correct four_player dimensions', () => {
    expect(BOARD_DIMENSIONS.four_player).toEqual({ width: 12, height: 12 });
  });
});

import { describe, it, expect } from 'vitest';
import {
  interpolatePiecePosition,
  calculateCooldownProgress,
  type Position,
  type ActiveMove,
} from '../../src/game/interpolation';
import { TIMING } from '../../src/game/constants';

// ============================================
// Test Fixtures
// ============================================

const createActiveMove = (
  pieceId: string,
  path: [number, number][],
  startTick: number
): ActiveMove => ({
  pieceId,
  path,
  startTick,
});

// ============================================
// interpolatePiecePosition Tests
// ============================================

describe('interpolatePiecePosition', () => {
  describe('no active move', () => {
    it('returns base position when activeMove is null', () => {
      const basePosition: Position = { row: 3, col: 4 };
      const result = interpolatePiecePosition(basePosition, null, 100, 10);
      expect(result).toEqual({ row: 3, col: 4 });
    });

    it('returns a copy of base position (not the same reference)', () => {
      const basePosition: Position = { row: 3, col: 4 };
      const result = interpolatePiecePosition(basePosition, null, 100, 10);
      expect(result).not.toBe(basePosition);
    });

    it('returns base position when path has only one point', () => {
      const basePosition: Position = { row: 3, col: 4 };
      const move = createActiveMove('p1', [[3, 4]], 0);
      const result = interpolatePiecePosition(basePosition, move, 100, 10);
      expect(result).toEqual({ row: 3, col: 4 });
    });
  });

  describe('single-segment move (one square)', () => {
    const basePosition: Position = { row: 3, col: 4 };
    const path: [number, number][] = [[3, 4], [3, 5]]; // Move right one square
    const ticksPerSquare = 10;

    it('returns start position at 0% progress (startTick)', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 0, ticksPerSquare);
      expect(result).toEqual({ row: 3, col: 4 });
    });

    it('returns midpoint at 50% progress', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 5, ticksPerSquare);
      expect(result).toEqual({ row: 3, col: 4.5 });
    });

    it('returns end position at 100% progress', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 10, ticksPerSquare);
      expect(result).toEqual({ row: 3, col: 5 });
    });

    it('returns end position when progress exceeds 100%', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 20, ticksPerSquare);
      expect(result).toEqual({ row: 3, col: 5 });
    });

    it('handles negative progress (before move started)', () => {
      const move = createActiveMove('p1', path, 10);
      const result = interpolatePiecePosition(basePosition, move, 0, ticksPerSquare);
      expect(result).toEqual({ row: 3, col: 4 });
    });
  });

  describe('multi-segment move (multiple squares)', () => {
    const basePosition: Position = { row: 0, col: 0 };
    // Rook moving 3 squares right: (0,0) -> (0,1) -> (0,2) -> (0,3)
    const path: [number, number][] = [[0, 0], [0, 1], [0, 2], [0, 3]];
    const ticksPerSquare = 10;
    // Total move = 3 segments * 10 ticks = 30 ticks

    it('returns start position at tick 0', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 0, ticksPerSquare);
      expect(result).toEqual({ row: 0, col: 0 });
    });

    it('returns position in first segment at 1/6 progress (tick 5)', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 5, ticksPerSquare);
      // 5/30 = 1/6 progress through 3 segments = 0.5 through path
      // segmentProgress = (5/30) * 3 = 0.5
      // segmentIndex = 0, segmentFraction = 0.5
      expect(result).toEqual({ row: 0, col: 0.5 });
    });

    it('returns position at segment boundary (tick 10)', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 10, ticksPerSquare);
      // 10/30 = 1/3 progress = 1.0 through segments
      // segmentIndex = 1, segmentFraction = 0
      expect(result).toEqual({ row: 0, col: 1 });
    });

    it('returns position in second segment at tick 15', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 15, ticksPerSquare);
      // 15/30 = 0.5 progress through 3 segments = 1.5 through path
      // segmentIndex = 1, segmentFraction = 0.5
      expect(result).toEqual({ row: 0, col: 1.5 });
    });

    it('returns position in third segment at tick 25', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 25, ticksPerSquare);
      // 25/30 progress through 3 segments = 2.5 through path
      // segmentIndex = 2, segmentFraction = 0.5
      expect(result).toEqual({ row: 0, col: 2.5 });
    });

    it('returns end position at completion (tick 30)', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 30, ticksPerSquare);
      expect(result).toEqual({ row: 0, col: 3 });
    });
  });

  describe('diagonal move', () => {
    const basePosition: Position = { row: 4, col: 4 };
    // Bishop moving diagonally: (4,4) -> (3,5) -> (2,6)
    const path: [number, number][] = [[4, 4], [3, 5], [2, 6]];
    const ticksPerSquare = 10;

    it('interpolates both row and col at 25% progress', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 5, ticksPerSquare);
      // 5/20 = 0.25 progress through 2 segments = 0.5 through path
      // segmentIndex = 0, segmentFraction = 0.5
      // row: 4 + (3-4)*0.5 = 3.5, col: 4 + (5-4)*0.5 = 4.5
      expect(result).toEqual({ row: 3.5, col: 4.5 });
    });

    it('interpolates correctly at segment boundary (tick 10)', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, 10, ticksPerSquare);
      expect(result).toEqual({ row: 3, col: 5 });
    });
  });

  describe('lightning speed', () => {
    const basePosition: Position = { row: 0, col: 0 };
    const path: [number, number][] = [[0, 0], [0, 1]];
    const ticksPerSquare = TIMING.LIGHTNING_TICKS_PER_SQUARE;

    it('moves faster with lightning speed', () => {
      const move = createActiveMove('p1', path, 0);

      // At half the ticks, should be 50% through
      const halfTicks = ticksPerSquare / 2;
      const result = interpolatePiecePosition(basePosition, move, halfTicks, ticksPerSquare);
      expect(result).toEqual({ row: 0, col: 0.5 });
    });

    it('completes in LIGHTNING_TICKS_PER_SQUARE ticks', () => {
      const move = createActiveMove('p1', path, 0);
      const result = interpolatePiecePosition(basePosition, move, ticksPerSquare, ticksPerSquare);
      expect(result).toEqual({ row: 0, col: 1 });
    });
  });

  describe('move with non-zero startTick', () => {
    const basePosition: Position = { row: 0, col: 0 };
    const path: [number, number][] = [[0, 0], [0, 1]];
    const ticksPerSquare = 10;

    it('calculates progress relative to startTick', () => {
      const move = createActiveMove('p1', path, 100);

      // At tick 105, should be 50% through (5 ticks elapsed out of 10)
      const result = interpolatePiecePosition(basePosition, move, 105, ticksPerSquare);
      expect(result).toEqual({ row: 0, col: 0.5 });
    });

    it('returns start position before move begins', () => {
      const move = createActiveMove('p1', path, 100);
      const result = interpolatePiecePosition(basePosition, move, 50, ticksPerSquare);
      expect(result).toEqual({ row: 0, col: 0 });
    });
  });
});

// ============================================
// calculateCooldownProgress Tests
// ============================================

describe('calculateCooldownProgress', () => {
  describe('basic progress calculation', () => {
    it('returns 0 when cooldown just started (remaining = total)', () => {
      const result = calculateCooldownProgress(100, 100);
      expect(result).toBe(0);
    });

    it('returns 0.5 when cooldown is halfway done', () => {
      const result = calculateCooldownProgress(50, 100);
      expect(result).toBe(0.5);
    });

    it('returns 1 when cooldown is complete (remaining = 0)', () => {
      const result = calculateCooldownProgress(0, 100);
      expect(result).toBe(1);
    });

    it('returns 0.75 when 25% remaining', () => {
      const result = calculateCooldownProgress(25, 100);
      expect(result).toBe(0.75);
    });
  });

  describe('edge cases', () => {
    it('returns 1 for negative remaining ticks', () => {
      const result = calculateCooldownProgress(-10, 100);
      expect(result).toBe(1);
    });

    it('returns 0 when remaining exceeds total', () => {
      const result = calculateCooldownProgress(150, 100);
      expect(result).toBe(0);
    });
  });

  describe('default total cooldown', () => {
    it('uses STANDARD_COOLDOWN_TICKS as default', () => {
      // At half remaining, should be 0.5
      const halfTicks = TIMING.STANDARD_COOLDOWN_TICKS / 2;
      const result = calculateCooldownProgress(halfTicks);
      expect(result).toBe(0.5);
    });
  });

  describe('lightning speed cooldown', () => {
    const lightningCooldown = TIMING.LIGHTNING_COOLDOWN_TICKS;

    it('calculates correctly for lightning cooldown', () => {
      // Half remaining = 50% complete
      const halfTicks = lightningCooldown / 2;
      const result = calculateCooldownProgress(halfTicks, lightningCooldown);
      expect(result).toBe(0.5);
    });

    it('completes faster with lightning cooldown', () => {
      // 25% remaining = 75% complete
      const quarterTicks = lightningCooldown / 4;
      const result = calculateCooldownProgress(quarterTicks, lightningCooldown);
      expect(result).toBe(0.75);
    });
  });
});

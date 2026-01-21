/**
 * Piece Position Interpolation
 *
 * Calculates smooth positions for pieces during movement.
 */

import { TIMING } from './constants';

export interface Position {
  row: number;
  col: number;
}

export interface ActiveMove {
  pieceId: string;
  path: [number, number][];
  startTick: number;
}

/**
 * Interpolate a piece's position based on its active move
 *
 * @param basePosition - The piece's base position (may be start or end depending on server state)
 * @param activeMove - The active move data, if the piece is moving
 * @param currentTick - Current game tick
 * @param ticksPerSquare - How many ticks to move one square (10 for standard, 2 for lightning)
 * @returns The interpolated position
 */
export function interpolatePiecePosition(
  basePosition: Position,
  activeMove: ActiveMove | null,
  currentTick: number,
  ticksPerSquare: number = TIMING.STANDARD_TICKS_PER_SQUARE
): Position {
  // No active move - return base position
  if (!activeMove || activeMove.path.length < 2) {
    return { ...basePosition };
  }

  const path = activeMove.path;
  const pathLength = path.length - 1; // Number of segments
  const totalTicks = pathLength * ticksPerSquare;

  // Calculate progress through the move (0.0 to 1.0)
  const elapsedTicks = currentTick - activeMove.startTick;
  const progress = Math.max(0, Math.min(1, elapsedTicks / totalTicks));

  // If move is complete, return final position
  if (progress >= 1) {
    const end = path[path.length - 1];
    return { row: end[0], col: end[1] };
  }

  // Find which segment of the path we're on
  const segmentProgress = progress * pathLength;
  const segmentIndex = Math.floor(segmentProgress);
  const segmentFraction = segmentProgress - segmentIndex;

  // Clamp segment index to valid range
  const safeIndex = Math.min(segmentIndex, pathLength - 1);

  const startPoint = path[safeIndex];
  const endPoint = path[safeIndex + 1];

  // Linear interpolation between segment points
  return {
    row: startPoint[0] + (endPoint[0] - startPoint[0]) * segmentFraction,
    col: startPoint[1] + (endPoint[1] - startPoint[1]) * segmentFraction,
  };
}

/**
 * Calculate cooldown progress (0.0 = full cooldown, 1.0 = ready)
 *
 * @param remainingTicks - Remaining cooldown ticks
 * @param totalCooldownTicks - Total cooldown duration
 * @returns Progress from 0 (just started cooldown) to 1 (cooldown complete)
 */
export function calculateCooldownProgress(
  remainingTicks: number,
  totalCooldownTicks: number = TIMING.STANDARD_COOLDOWN_TICKS
): number {
  if (remainingTicks <= 0) return 1;
  if (remainingTicks >= totalCooldownTicks) return 0;
  return 1 - remainingTicks / totalCooldownTicks;
}

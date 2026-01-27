/**
 * Game Constants
 *
 * Board dimensions, colors, and timing constants.
 */

// Board square colors (green/white checkerboard like original)
export const BOARD_COLORS = {
  light: 0xffffff,
  dark: 0x8ed47d,
  highlight: 0xf0f000,
  legalMove: 0xf0f000,
  selected: 0xf0f000,
  invalid: 0x666666, // For 4-player corner squares
  background: 0xfcfcf4,
} as const;

// Board dimensions by type
export const BOARD_DIMENSIONS = {
  standard: { width: 8, height: 8 },
  four_player: { width: 12, height: 12 },
} as const;

// Tick rate - single source of truth
// Changing this value automatically adjusts all tick-based timing
const TICK_RATE_HZ = 30;

// Timing defined in real-world units (seconds), with derived tick values
export const TIMING = {
  // Core tick rate
  TICK_RATE_HZ,
  TICK_PERIOD_MS: 1000 / TICK_RATE_HZ,
  TICKS_PER_SECOND: TICK_RATE_HZ,

  // Speed-specific timing (in seconds)
  STANDARD_SECONDS_PER_SQUARE: 1.0,
  LIGHTNING_SECONDS_PER_SQUARE: 0.2,
  STANDARD_COOLDOWN_SECONDS: 10.0,
  LIGHTNING_COOLDOWN_SECONDS: 2.0,

  // Derived tick values (computed from seconds * tick rate)
  get STANDARD_TICKS_PER_SQUARE() {
    return Math.round(this.STANDARD_SECONDS_PER_SQUARE * TICK_RATE_HZ);
  },
  get LIGHTNING_TICKS_PER_SQUARE() {
    return Math.round(this.LIGHTNING_SECONDS_PER_SQUARE * TICK_RATE_HZ);
  },
  get STANDARD_COOLDOWN_TICKS() {
    return Math.round(this.STANDARD_COOLDOWN_SECONDS * TICK_RATE_HZ);
  },
  get LIGHTNING_COOLDOWN_TICKS() {
    return Math.round(this.LIGHTNING_COOLDOWN_SECONDS * TICK_RATE_HZ);
  },
} as const;

// Default render settings
export const RENDER = {
  SQUARE_SIZE: 64, // Pixels per square
  PIECE_SCALE: 0.9, // Scale pieces to fit within squares
  HIGHLIGHT_ALPHA: 0.5,
  LEGAL_MOVE_ALPHA: 0.4,
  COOLDOWN_OVERLAY_ALPHA: 0.5,
  COOLDOWN_OVERLAY_COLOR: 0xf0f000, // Yellow, same as selection
  SELECTION_STROKE_WIDTH: 4, // Width of selection outline
  // Offset to center pieces within squares (compensates for sprite artwork positioning)
  // Positive values move pieces right/down, negative values move them left/up
  PIECE_OFFSET_X: -2, // Shift left to center
  PIECE_OFFSET_Y: -2, // Shift up to center
} as const;

/**
 * Check if a square is a corner square in 4-player mode
 * Corners are 2x2 squares in each corner of the 12x12 board
 */
export function isCornerSquare(row: number, col: number): boolean {
  const isTopLeft = row < 2 && col < 2;
  const isTopRight = row < 2 && col >= 10;
  const isBottomLeft = row >= 10 && col < 2;
  const isBottomRight = row >= 10 && col >= 10;
  return isTopLeft || isTopRight || isBottomLeft || isBottomRight;
}

/**
 * Check if a square is valid for a given board type
 */
export function isValidSquare(
  row: number,
  col: number,
  boardType: 'standard' | 'four_player'
): boolean {
  const dims = BOARD_DIMENSIONS[boardType];

  // Check bounds
  if (row < 0 || row >= dims.height || col < 0 || col >= dims.width) {
    return false;
  }

  // Check corners for 4-player
  if (boardType === 'four_player' && isCornerSquare(row, col)) {
    return false;
  }

  return true;
}

/**
 * Get the square color for a position
 */
export function getSquareColor(
  row: number,
  col: number,
  boardType: 'standard' | 'four_player'
): number {
  // Invalid squares (corners in 4-player)
  if (boardType === 'four_player' && isCornerSquare(row, col)) {
    return BOARD_COLORS.invalid;
  }

  // Standard checkerboard pattern
  const isLight = (row + col) % 2 === 0;
  return isLight ? BOARD_COLORS.light : BOARD_COLORS.dark;
}

/**
 * Get piece rotation angle (in radians) for 4-player mode
 *
 * In 4-player mode, pieces face toward the center of the board:
 * - Player 1 (East, right side): faces left (-90°)
 * - Player 2 (South, bottom): faces up (0°, default)
 * - Player 3 (West, left side): faces right (90°)
 * - Player 4 (North, top): faces down (180°)
 *
 * In standard mode, player 1 faces up, player 2 faces down.
 */
export function getPieceRotation(
  player: number,
  boardType: 'standard' | 'four_player'
): number {
  if (boardType === 'standard') {
    // Standard 2-player: player 1 at bottom (faces up), player 2 at top (faces down)
    return player === 2 ? Math.PI : 0;
  }

  // 4-player mode rotations
  switch (player) {
    case 1: return -Math.PI / 2;  // East, face left
    case 2: return 0;              // South, face up
    case 3: return Math.PI / 2;   // West, face right
    case 4: return Math.PI;        // North, face down
    default: return 0;
  }
}

/**
 * Board rotation transforms
 *
 * Each player should see their pieces at the bottom of the screen.
 * These functions transform between game coordinates and view coordinates.
 *
 * Standard 2-player (8x8):
 * - Player 1: no rotation (pieces at rows 6-7, already at bottom)
 * - Player 2: 180° rotation (pieces at rows 0-1 appear at bottom)
 *
 * 4-player (12x12):
 * - Player 1 (East, cols 10-11): 90° CW rotation (right side becomes bottom)
 * - Player 2 (South, rows 10-11): no rotation (already at bottom)
 * - Player 3 (West, cols 0-1): 90° CCW rotation (left side becomes bottom)
 * - Player 4 (North, rows 0-1): 180° rotation (top becomes bottom)
 */

export interface Coords {
  row: number;
  col: number;
}

/**
 * Transform game coordinates to view coordinates for rendering
 */
export function transformToViewCoords(
  coords: Coords,
  playerNumber: number,
  boardType: 'standard' | 'four_player'
): Coords {
  const { row, col } = coords;

  if (boardType === 'standard') {
    const maxIndex = 7; // 8x8 board
    if (playerNumber === 2) {
      // 180° rotation
      return { row: maxIndex - row, col: maxIndex - col };
    }
    return { row, col };
  }

  // 4-player (12x12)
  const maxIndex = 11;
  switch (playerNumber) {
    case 1:
      // 90° clockwise: (row, col) -> (col, maxIndex - row)
      return { row: col, col: maxIndex - row };
    case 2:
      // No rotation
      return { row, col };
    case 3:
      // 90° counter-clockwise: (row, col) -> (maxIndex - col, row)
      return { row: maxIndex - col, col: row };
    case 4:
      // 180°: (row, col) -> (maxIndex - row, maxIndex - col)
      return { row: maxIndex - row, col: maxIndex - col };
    default:
      // Spectator or unknown - no rotation
      return { row, col };
  }
}

/**
 * Transform view coordinates to game coordinates for input handling
 * (Inverse of transformToViewCoords)
 */
export function transformToGameCoords(
  coords: Coords,
  playerNumber: number,
  boardType: 'standard' | 'four_player'
): Coords {
  const { row, col } = coords;

  if (boardType === 'standard') {
    const maxIndex = 7;
    if (playerNumber === 2) {
      // 180° rotation (self-inverse)
      return { row: maxIndex - row, col: maxIndex - col };
    }
    return { row, col };
  }

  // 4-player (12x12)
  const maxIndex = 11;
  switch (playerNumber) {
    case 1:
      // Inverse of 90° CW is 90° CCW: (row, col) -> (maxIndex - col, row)
      return { row: maxIndex - col, col: row };
    case 2:
      // No rotation
      return { row, col };
    case 3:
      // Inverse of 90° CCW is 90° CW: (row, col) -> (col, maxIndex - row)
      return { row: col, col: maxIndex - row };
    case 4:
      // 180° (self-inverse)
      return { row: maxIndex - row, col: maxIndex - col };
    default:
      return { row, col };
  }
}

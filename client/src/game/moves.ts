/**
 * Client-side Legal Move Calculation
 *
 * Computes legal moves locally to avoid latency from server round-trips.
 * Based on the original GameLogic.js implementation.
 */

import type { Piece, ActiveMove, BoardType } from '../stores/game';
import { isValidSquare } from './constants';

// Slider piece types (move along lines/diagonals, can be blocked by same-line enemies)
const SLIDER_TYPES = new Set(['B', 'R', 'Q']);

// Board dimensions by type
const BOARD_SIZES: Record<BoardType, number> = {
  standard: 8,
  four_player: 12,
};

// Player pawn directions for standard 2-player mode
const STANDARD_PAWN_DIRECTION: Record<number, number> = {
  1: -1, // Player 1 moves up (decreasing row)
  2: 1,  // Player 2 moves down (increasing row)
};

// 4-player pawn config: forward direction (row_delta, col_delta), home axis value, axis type
interface PawnConfig {
  forward: [number, number];
  homeAxis: number;
  axis: 'row' | 'col';
}

const FOUR_PLAYER_PAWN_CONFIG: Record<number, PawnConfig> = {
  1: { forward: [0, -1], homeAxis: 10, axis: 'col' },  // East, moves left
  2: { forward: [-1, 0], homeAxis: 10, axis: 'row' },  // South, moves up
  3: { forward: [0, 1], homeAxis: 1, axis: 'col' },    // West, moves right
  4: { forward: [1, 0], homeAxis: 1, axis: 'row' },    // North, moves down
};

/**
 * Get a piece at a specific location
 */
function getPieceAtLocation(
  pieces: Piece[],
  row: number,
  col: number
): Piece | null {
  return pieces.find((p) => !p.captured && p.row === row && p.col === col) ?? null;
}

/**
 * Check if a piece is currently moving
 */
function isMoving(activeMoves: ActiveMove[], pieceId: string): boolean {
  return activeMoves.some((m) => m.pieceId === pieceId);
}

/**
 * Get the forward path squares for a moving piece (squares not yet reached).
 * Returns squares the piece will traverse but hasn't reached yet.
 * Skips non-integer coordinates (knight midpoints don't block - knights jump).
 */
function getForwardPath(
  move: ActiveMove,
  currentTick: number,
  ticksPerSquare: number
): [number, number][] {
  const path = move.path;
  if (path.length < 2) {
    return [];
  }

  // Helper to check if a coordinate is an integer (not a knight midpoint)
  const isInteger = (n: number) => n === Math.floor(n);

  const elapsed = currentTick - move.startTick;
  if (elapsed < 0) {
    // Move hasn't started yet - entire path (except start) is forward
    // Skip non-integer coordinates (knight midpoints)
    return path
      .slice(1)
      .filter(([r, c]) => isInteger(r) && isInteger(c))
      .map(([r, c]) => [r, c]);
  }

  // Number of segments = path.length - 1
  const numSegments = path.length - 1;
  const totalTicks = numSegments * ticksPerSquare;

  if (elapsed >= totalTicks) {
    // Move completed - no forward path
    return [];
  }

  // Current segment index (which segment we're currently traversing)
  const currentSegment = Math.floor(elapsed / ticksPerSquare);

  // Forward path = all squares from currentSegment + 1 onwards
  // (the square we're moving toward and all subsequent squares)
  // Skip non-integer coordinates (knight midpoints)
  const forwardSquares: [number, number][] = [];
  for (let i = currentSegment + 1; i < path.length; i++) {
    const [r, c] = path[i];
    if (isInteger(r) && isInteger(c)) {
      forwardSquares.push([r, c]);
    }
  }

  return forwardSquares;
}

/**
 * Check if a move path is legal (no blocking pieces, no friendly collisions)
 *
 * Rules:
 * - Stationary pieces block (both own and enemy)
 * - Own moving pieces' forward path (not yet traversed) blocks own pieces
 * - Own moving pieces' already-traversed path does NOT block
 * - Enemy moving pieces do NOT block (neither their start nor path)
 * - Exception: enemy slider moving on the same line blocks slider pieces
 * - Moving pieces have "vacated" their start position (treated as empty)
 */
function isLegalMoveNoCross(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  rowDir: number,
  colDir: number,
  steps: number,
  canCapture: boolean
): boolean {
  // Build set of forward path squares for own moving pieces
  const ownForwardPath = new Set<string>();
  for (const move of activeMoves) {
    const movingPiece = pieces.find((p) => p.id === move.pieceId);
    if (movingPiece && movingPiece.player === piece.player) {
      const forwardSquares = getForwardPath(move, currentTick, ticksPerSquare);
      for (const [r, c] of forwardSquares) {
        ownForwardPath.add(`${r},${c}`);
      }
    }
  }

  // Build set of same-line blocking squares from enemy sliders
  const enemySameLinePath = new Set<string>();
  if (SLIDER_TYPES.has(piece.type)) {
    for (const move of activeMoves) {
      const movingPiece = pieces.find((p) => p.id === move.pieceId);
      if (!movingPiece || movingPiece.player === piece.player) continue;
      if (!SLIDER_TYPES.has(movingPiece.type)) continue;
      if (move.path.length < 2) continue;

      // Get enemy move direction
      const eDr = move.path[1][0] - move.path[0][0];
      const eDc = move.path[1][1] - move.path[0][1];

      // Check if directions are parallel (cross product == 0)
      if (rowDir * eDc !== colDir * eDr) continue;

      // Check if on the same geometric line
      const diffR = move.path[0][0] - piece.row;
      const diffC = move.path[0][1] - piece.col;
      if (diffR * colDir !== diffC * rowDir) continue;

      // Enemy slider is on the same line - its forward path blocks us
      const forwardSquares = getForwardPath(move, currentTick, ticksPerSquare);
      for (const [r, c] of forwardSquares) {
        enemySameLinePath.add(`${r},${c}`);
      }
    }
  }

  // Check each square along the path
  for (let i = 1; i <= steps; i++) {
    const iRow = piece.row + rowDir * i;
    const iCol = piece.col + colDir * i;
    const isDestination = i === steps;

    // Check for pieces at this square
    const blockingPiece = getPieceAtLocation(pieces, iRow, iCol);
    if (blockingPiece && !blockingPiece.captured) {
      const pieceIsMoving = isMoving(activeMoves, blockingPiece.id);

      if (pieceIsMoving) {
        // Moving piece has vacated - square is effectively empty
        // (collision detection handles any mid-path interactions)
      } else if (blockingPiece.player === piece.player) {
        // Own stationary piece - blocked
        return false;
      } else {
        // Enemy stationary piece
        if (!isDestination || !canCapture) {
          // Can't pass through enemy or capture not allowed at destination
          return false;
        }
        // else: capture at destination - allowed
      }
    }

    // Check for own moving piece's forward path
    if (ownForwardPath.has(`${iRow},${iCol}`)) {
      return false; // Can't move through/to own piece's forward path
    }

    // Check for enemy same-line slider blocking
    if (enemySameLinePath.has(`${iRow},${iCol}`)) {
      return false;
    }
  }

  return true;
}

/**
 * Check if a pawn move is legal (standard 2-player)
 */
function isPawnLegalMoveStandard(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const dir = STANDARD_PAWN_DIRECTION[piece.player] ?? -1;
  const steps = Math.abs(toRow - piece.row);
  let canCapture = true;

  // Check direction
  if (toRow - piece.row !== dir) {
    // Two-square initial move
    if (piece.player === 1 && piece.row === 6 && toRow === 4) {
      canCapture = false;
    } else if (piece.player === 2 && piece.row === 1 && toRow === 3) {
      canCapture = false;
    } else {
      return false;
    }
  }

  // Forward move (no capture)
  if (piece.col === toCol) {
    return isLegalMoveNoCross(
      pieces, activeMoves, currentTick, ticksPerSquare,
      piece, dir, 0, steps, false
    );
  }

  // Diagonal capture
  if (canCapture && Math.abs(piece.col - toCol) === 1) {
    const destPiece = getPieceAtLocation(pieces, toRow, toCol);
    if (destPiece && destPiece.player !== piece.player && !isMoving(activeMoves, destPiece.id)) {
      return isLegalMoveNoCross(
        pieces, activeMoves, currentTick, ticksPerSquare,
        piece, dir, toCol - piece.col, steps, true
      );
    }
  }

  return false;
}

/**
 * Check if a pawn move is legal (4-player)
 */
function isPawnLegalMove4Player(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number,
  boardType: BoardType
): boolean {
  const config = FOUR_PLAYER_PAWN_CONFIG[piece.player];
  if (!config) return false;

  const [forwardRow, forwardCol] = config.forward;
  const rowDelta = toRow - piece.row;
  const colDelta = toCol - piece.col;

  // Check if moving in the forward direction
  const isForwardMove = (
    (forwardRow !== 0 && rowDelta === forwardRow && colDelta === 0) ||
    (forwardCol !== 0 && colDelta === forwardCol && rowDelta === 0)
  );

  // Check two-square initial move
  const isDoubleMove = (
    (forwardRow !== 0 && rowDelta === forwardRow * 2 && colDelta === 0) ||
    (forwardCol !== 0 && colDelta === forwardCol * 2 && rowDelta === 0)
  );

  const isAtHome = config.axis === 'row'
    ? piece.row === config.homeAxis
    : piece.col === config.homeAxis;

  // Forward move
  if (isForwardMove) {
    // Check destination is valid
    if (!isValidSquare(toRow, toCol, boardType)) return false;

    return isLegalMoveNoCross(
      pieces, activeMoves, currentTick, ticksPerSquare,
      piece, forwardRow, forwardCol, 1, false
    );
  }

  // Two-square initial move
  if (isDoubleMove && isAtHome) {
    if (!isValidSquare(toRow, toCol, boardType)) return false;

    return isLegalMoveNoCross(
      pieces, activeMoves, currentTick, ticksPerSquare,
      piece, forwardRow, forwardCol, 2, false
    );
  }

  // Diagonal capture - one step forward and one step perpendicular
  const isDiagonalCapture = (
    (forwardRow !== 0 && rowDelta === forwardRow && Math.abs(colDelta) === 1) ||
    (forwardCol !== 0 && colDelta === forwardCol && Math.abs(rowDelta) === 1)
  );

  if (isDiagonalCapture) {
    if (!isValidSquare(toRow, toCol, boardType)) return false;

    const destPiece = getPieceAtLocation(pieces, toRow, toCol);
    if (destPiece && destPiece.player !== piece.player && !isMoving(activeMoves, destPiece.id)) {
      return isLegalMoveNoCross(
        pieces, activeMoves, currentTick, ticksPerSquare,
        piece, rowDelta, colDelta, 1, true
      );
    }
  }

  return false;
}

/**
 * Check if a pawn move is legal (dispatches to appropriate function)
 */
function isPawnLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number,
  boardType: BoardType
): boolean {
  if (boardType === 'four_player') {
    return isPawnLegalMove4Player(
      pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol, boardType
    );
  }
  return isPawnLegalMoveStandard(
    pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol
  );
}

/**
 * Check if a knight move is legal
 */
function isKnightLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const rowDelta = Math.abs(toRow - piece.row);
  const colDelta = Math.abs(toCol - piece.col);

  if (!((rowDelta === 1 && colDelta === 2) || (rowDelta === 2 && colDelta === 1))) {
    return false;
  }

  // Knights jump, so only check destination
  return isLegalMoveNoCross(
    pieces, activeMoves, currentTick, ticksPerSquare,
    piece, toRow - piece.row, toCol - piece.col, 1, true
  );
}

/**
 * Check if a bishop move is legal
 */
function isBishopLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const rowDelta = Math.abs(toRow - piece.row);
  const colDelta = Math.abs(toCol - piece.col);

  if (rowDelta !== colDelta || rowDelta === 0) {
    return false;
  }

  const rowDir = (toRow - piece.row) / rowDelta;
  const colDir = (toCol - piece.col) / colDelta;

  return isLegalMoveNoCross(
    pieces, activeMoves, currentTick, ticksPerSquare,
    piece, rowDir, colDir, rowDelta, true
  );
}

/**
 * Check if a rook move is legal
 */
function isRookLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const rowDelta = Math.abs(toRow - piece.row);
  const colDelta = Math.abs(toCol - piece.col);

  if ((rowDelta > 0 && colDelta > 0) || (rowDelta === 0 && colDelta === 0)) {
    return false;
  }

  const rowDir = rowDelta > 0 ? (toRow - piece.row) / rowDelta : 0;
  const colDir = colDelta > 0 ? (toCol - piece.col) / colDelta : 0;

  return isLegalMoveNoCross(
    pieces, activeMoves, currentTick, ticksPerSquare,
    piece, rowDir, colDir, Math.max(rowDelta, colDelta), true
  );
}

/**
 * Check if a queen move is legal
 */
function isQueenLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  return (
    isBishopLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol) ||
    isRookLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol)
  );
}

/**
 * Check if a king move is legal (including castling)
 */
function isKingLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number,
  boardType: BoardType = 'standard'
): boolean {
  const rowDelta = Math.abs(toRow - piece.row);
  const colDelta = Math.abs(toCol - piece.col);

  if (rowDelta > 1 || colDelta > 1) {
    // Check for castling - king must not have moved
    if (!piece.moved) {
      if (boardType === 'standard') {
        return checkCastlingStandard(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
      } else {
        return checkCastling4Player(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
      }
    }
    return false;
  }

  return isQueenLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
}

/**
 * Check standard 2-player castling
 */
function checkCastlingStandard(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const rowDelta = Math.abs(toRow - piece.row);

  // King must stay on same row and move exactly 2 squares
  if (rowDelta !== 0) return false;
  if (toCol !== 2 && toCol !== 6) return false;

  const rookCol = toCol === 2 ? 0 : 7;
  const rookToCol = toCol === 2 ? 3 : 5;
  const rookPiece = getPieceAtLocation(pieces, piece.row, rookCol);

  // Rook must exist, be a rook, belong to same player, and not have moved
  if (
    rookPiece &&
    rookPiece.type === 'R' &&
    rookPiece.player === piece.player &&
    !rookPiece.moved &&
    !isMoving(activeMoves, rookPiece.id)
  ) {
    // Check both king and rook paths are clear
    const isKingPathClear = isRookLegalMove(
      pieces, activeMoves, currentTick, ticksPerSquare,
      piece, toRow, toCol
    );
    const isRookPathClear = isRookLegalMove(
      pieces, activeMoves, currentTick, ticksPerSquare,
      rookPiece, toRow, rookToCol
    );
    return isKingPathClear && isRookPathClear;
  }
  return false;
}

/**
 * Check 4-player castling
 * Players 2 and 4 (horizontal): Castle horizontally, rooks at cols 2 and 9
 * Players 1 and 3 (vertical): Castle vertically, rooks at rows 2 and 9
 */
function checkCastling4Player(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const rowDiff = toRow - piece.row;
  const colDiff = toCol - piece.col;

  // Determine if this player castles horizontally or vertically
  // Players 2 and 4 (on rows 0 and 11) castle horizontally
  // Players 1 and 3 (on cols 0 and 11) castle vertically
  const config = FOUR_PLAYER_PAWN_CONFIG[piece.player];
  if (!config) return false;

  if (config.axis === 'row') {
    // Horizontal castling (players 2 and 4)
    // King must stay on same row and move exactly 2 squares
    if (rowDiff !== 0 || Math.abs(colDiff) !== 2) return false;

    // Determine rook column based on direction
    const rookCol = colDiff > 0 ? 9 : 2;
    const newRookCol = colDiff > 0 ? toCol - 1 : toCol + 1;
    const rookPiece = getPieceAtLocation(pieces, piece.row, rookCol);

    if (
      rookPiece &&
      rookPiece.type === 'R' &&
      rookPiece.player === piece.player &&
      !rookPiece.moved &&
      !isMoving(activeMoves, rookPiece.id)
    ) {
      // Check paths are clear
      const isKingPathClear = isRookLegalMove(
        pieces, activeMoves, currentTick, ticksPerSquare,
        piece, toRow, toCol
      );
      const isRookPathClear = isRookLegalMove(
        pieces, activeMoves, currentTick, ticksPerSquare,
        rookPiece, toRow, newRookCol
      );
      return isKingPathClear && isRookPathClear;
    }
  } else {
    // Vertical castling (players 1 and 3)
    // King must stay on same column and move exactly 2 squares
    if (colDiff !== 0 || Math.abs(rowDiff) !== 2) return false;

    // Determine rook row based on direction
    const rookRow = rowDiff > 0 ? 9 : 2;
    const newRookRow = rowDiff > 0 ? toRow - 1 : toRow + 1;
    const rookPiece = getPieceAtLocation(pieces, rookRow, piece.col);

    if (
      rookPiece &&
      rookPiece.type === 'R' &&
      rookPiece.player === piece.player &&
      !rookPiece.moved &&
      !isMoving(activeMoves, rookPiece.id)
    ) {
      // Check paths are clear
      const isKingPathClear = isRookLegalMove(
        pieces, activeMoves, currentTick, ticksPerSquare,
        piece, toRow, toCol
      );
      const isRookPathClear = isRookLegalMove(
        pieces, activeMoves, currentTick, ticksPerSquare,
        rookPiece, newRookRow, piece.col
      );
      return isKingPathClear && isRookPathClear;
    }
  }

  return false;
}

/**
 * Check if a specific move is legal
 */
export function isLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number,
  boardType: BoardType = 'standard'
): boolean {
  const boardSize = BOARD_SIZES[boardType];

  // Bounds check
  if (toRow < 0 || toRow >= boardSize || toCol < 0 || toCol >= boardSize) {
    return false;
  }

  // Check for invalid squares (corners in 4-player)
  if (!isValidSquare(toRow, toCol, boardType)) {
    return false;
  }

  // Can't move to same square
  if (piece.row === toRow && piece.col === toCol) {
    return false;
  }

  // Dispatch to piece-specific logic
  switch (piece.type) {
    case 'P':
      return isPawnLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol, boardType);
    case 'N':
      return isKnightLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
    case 'B':
      return isBishopLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
    case 'R':
      return isRookLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
    case 'Q':
      return isQueenLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
    case 'K':
      return isKingLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol, boardType);
    default:
      return false;
  }
}

/**
 * Get all legal moves for a piece
 */
export function getLegalMovesForPiece(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  boardType: BoardType = 'standard'
): [number, number][] {
  const moves: [number, number][] = [];
  const boardSize = BOARD_SIZES[boardType];

  for (let row = 0; row < boardSize; row++) {
    for (let col = 0; col < boardSize; col++) {
      if (isLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, row, col, boardType)) {
        moves.push([row, col]);
      }
    }
  }

  return moves;
}

/**
 * Get all legal moves for a player
 */
export function getAllLegalMoves(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  playerNumber: number,
  boardType: BoardType = 'standard'
): Map<string, [number, number][]> {
  const allMoves = new Map<string, [number, number][]>();

  for (const piece of pieces) {
    if (
      piece.player === playerNumber &&
      !piece.captured &&
      !piece.moving &&
      !piece.onCooldown
    ) {
      const moves = getLegalMovesForPiece(
        pieces, activeMoves, currentTick, ticksPerSquare, piece, boardType
      );
      if (moves.length > 0) {
        allMoves.set(piece.id, moves);
      }
    }
  }

  return allMoves;
}

/**
 * Client-side Legal Move Calculation
 *
 * Computes legal moves locally to avoid latency from server round-trips.
 * Based on the original GameLogic.js implementation.
 */

import type { Piece, ActiveMove, PieceType } from '../stores/game';

// Player direction for pawns: player 1 moves up (-1), player 2 moves down (+1)
const PLAYER_DIRECTION: Record<number, number> = {
  1: -1,
  2: 1,
};

// Board dimensions
const BOARD_SIZE = 8;

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
 * Check if a move path is legal (no blocking pieces, no friendly collisions)
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
  // Check each square along the path
  for (let i = 1; i <= steps; i++) {
    const iRow = piece.row + rowDir * i;
    const iCol = piece.col + colDir * i;

    // Check for stationary pieces
    const blockingPiece = getPieceAtLocation(pieces, iRow, iCol);
    if (blockingPiece && !blockingPiece.captured && !isMoving(activeMoves, blockingPiece.id)) {
      // Can only pass through if this is the final square, capture is allowed,
      // and it's an enemy piece that isn't moving
      if (
        !canCapture ||
        i !== steps ||
        blockingPiece.player === piece.player
      ) {
        return false;
      }
    }

    // Check for same player's moving pieces ending at this square
    for (const move of activeMoves) {
      if (move.pieceId === piece.id) continue;

      const movingPiece = pieces.find((p) => p.id === move.pieceId);
      if (!movingPiece || movingPiece.player !== piece.player) continue;

      const endPos = move.path[move.path.length - 1];
      if (endPos[0] === iRow && endPos[1] === iCol) {
        return false;
      }
    }
  }

  // Check that destination isn't on the future path of same player's active moves
  const destRow = piece.row + rowDir * steps;
  const destCol = piece.col + colDir * steps;

  for (const move of activeMoves) {
    const movingPiece = pieces.find((p) => p.id === move.pieceId);
    if (!movingPiece || movingPiece.player !== piece.player) continue;

    const tickDelta = currentTick - move.startTick;
    const movements = Math.floor((tickDelta + ticksPerSquare - 1) / ticksPerSquare);

    for (let j = movements; j < move.path.length; j++) {
      if (move.path[j][0] === destRow && move.path[j][1] === destCol) {
        return false;
      }
    }
  }

  return true;
}

/**
 * Check if a pawn move is legal
 */
function isPawnLegalMove(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece,
  toRow: number,
  toCol: number
): boolean {
  const dir = PLAYER_DIRECTION[piece.player] ?? -1;
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
  toCol: number
): boolean {
  const rowDelta = Math.abs(toRow - piece.row);
  const colDelta = Math.abs(toCol - piece.col);

  if (rowDelta > 1 || colDelta > 1) {
    // Check for castling - king must not have moved
    if (!piece.moved && rowDelta === 0 && (toCol === 2 || toCol === 6)) {
      const rookCol = toCol === 2 ? 0 : 7;
      const rookToCol = toCol === 2 ? 3 : 5;
      const rookPiece = getPieceAtLocation(pieces, piece.row, rookCol);

      // Rook must exist, be a rook, belong to same player, and not have moved
      if (
        rookPiece &&
        rookPiece.type === 'R' &&
        rookPiece.player === piece.player &&
        !rookPiece.moved
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
    }
    return false;
  }

  return isQueenLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
}

// Map piece types to their legal move functions
const PIECE_MOVE_FN: Record<
  PieceType,
  (
    pieces: Piece[],
    activeMoves: ActiveMove[],
    currentTick: number,
    ticksPerSquare: number,
    piece: Piece,
    toRow: number,
    toCol: number
  ) => boolean
> = {
  P: isPawnLegalMove,
  N: isKnightLegalMove,
  B: isBishopLegalMove,
  R: isRookLegalMove,
  Q: isQueenLegalMove,
  K: isKingLegalMove,
};

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
  toCol: number
): boolean {
  // Bounds check
  if (toRow < 0 || toRow >= BOARD_SIZE || toCol < 0 || toCol >= BOARD_SIZE) {
    return false;
  }

  // Can't move to same square
  if (piece.row === toRow && piece.col === toCol) {
    return false;
  }

  const moveFn = PIECE_MOVE_FN[piece.type];
  if (!moveFn) {
    return false;
  }

  return moveFn(pieces, activeMoves, currentTick, ticksPerSquare, piece, toRow, toCol);
}

/**
 * Get all legal moves for a piece
 */
export function getLegalMovesForPiece(
  pieces: Piece[],
  activeMoves: ActiveMove[],
  currentTick: number,
  ticksPerSquare: number,
  piece: Piece
): [number, number][] {
  const moves: [number, number][] = [];

  for (let row = 0; row < BOARD_SIZE; row++) {
    for (let col = 0; col < BOARD_SIZE; col++) {
      if (isLegalMove(pieces, activeMoves, currentTick, ticksPerSquare, piece, row, col)) {
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
  playerNumber: number
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
        pieces, activeMoves, currentTick, ticksPerSquare, piece
      );
      if (moves.length > 0) {
        allMoves.set(piece.id, moves);
      }
    }
  }

  return allMoves;
}

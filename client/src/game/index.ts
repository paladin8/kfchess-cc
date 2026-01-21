/**
 * Game Module - Public exports
 */

export { GameRenderer, type BoardType, type RendererPiece, type RendererCooldown, type RendererOptions } from './renderer';
export { loadSprites, areSpritesLoaded, getPieceTexture, getPlayerTint, PLAYER_COLORS, type PieceType } from './sprites';
export { interpolatePiecePosition, calculateCooldownProgress, type Position, type ActiveMove } from './interpolation';
export {
  BOARD_COLORS,
  BOARD_DIMENSIONS,
  TIMING,
  RENDER,
  isCornerSquare,
  isValidSquare,
  getSquareColor,
  getPieceRotation,
  transformToViewCoords,
  transformToGameCoords,
  type Coords,
} from './constants';
export { isLegalMove, getLegalMovesForPiece, getAllLegalMoves } from './moves';

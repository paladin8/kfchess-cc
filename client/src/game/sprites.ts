/**
 * Sprite Sheet Definitions and Loader
 *
 * The chess-sprites.png contains pieces in a 6x2 layout:
 * - Top row: outline pieces (white style) - Pawn, Knight, Bishop, Rook, Queen, King
 * - Bottom row: filled pieces (black style) - Pawn, Knight, Bishop, Rook, Queen, King
 *
 * Note: The sprites are NOT in a uniform grid - each has specific pixel coordinates.
 *
 * For 4-player support, we use the filled (black) pieces and tint them:
 * - Player 1: White tint (0xFFFFFF)
 * - Player 2: Black/dark grey (0x1A1A1A)
 * - Player 3: Red tint (0xE63946)
 * - Player 4: Blue tint (0x457B9D)
 */

import { Assets, Texture, Rectangle } from 'pixi.js';
import chessSpritesUrl from '../assets/chess-sprites.png';

// Piece types
export type PieceType = 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';

// Sprite coordinates from original implementation
// Each sprite is 100x100 pixels at specific x,y positions
const SPRITE_SIZE = 100;

// Outline pieces (top row) - white sprites for player 1
const OUTLINE_SPRITE_COORDS: Record<PieceType, { x: number; y: number }> = {
  P: { x: 45, y: 19 },
  N: { x: 145, y: 15 },
  B: { x: 248, y: 16 },
  R: { x: 346, y: 13 },
  Q: { x: 445, y: 13 },
  K: { x: 545, y: 15 },
};

// Filled pieces (bottom row) - black sprites for players 2-4 (tinted for 3-4)
const FILLED_SPRITE_COORDS: Record<PieceType, { x: number; y: number }> = {
  P: { x: 45, y: 117 },
  N: { x: 145, y: 115 },
  B: { x: 248, y: 115 },
  R: { x: 348, y: 115 },
  Q: { x: 446, y: 115 },
  K: { x: 545, y: 115 },
};

// Player colors for tinting
export const PLAYER_COLORS: Record<number, number> = {
  1: 0xffffff, // White
  2: 0x1a1a1a, // Black
  3: 0xe63946, // Red
  4: 0x457b9d, // Blue
};

// Sprite textures storage
const spriteTextures: Map<string, Texture> = new Map();
let loaded = false;

/**
 * Get the texture key for a piece type and style
 */
function getTextureKey(pieceType: PieceType, style: 'outline' | 'filled'): string {
  return `piece_${pieceType}_${style}`;
}

/**
 * Load the sprite sheet and extract individual piece textures
 */
export async function loadSprites(): Promise<void> {
  if (loaded) return;

  // Load the sprite sheet image
  const texture = await Assets.load<Texture>(chessSpritesUrl);
  const baseTexture = texture.source;

  // Extract textures for each piece type - both outline and filled styles
  for (const [pieceType, coords] of Object.entries(OUTLINE_SPRITE_COORDS)) {
    const frame = new Rectangle(coords.x, coords.y, SPRITE_SIZE, SPRITE_SIZE);
    const pieceTexture = new Texture({ source: baseTexture, frame });
    spriteTextures.set(getTextureKey(pieceType as PieceType, 'outline'), pieceTexture);
  }

  for (const [pieceType, coords] of Object.entries(FILLED_SPRITE_COORDS)) {
    const frame = new Rectangle(coords.x, coords.y, SPRITE_SIZE, SPRITE_SIZE);
    const pieceTexture = new Texture({ source: baseTexture, frame });
    spriteTextures.set(getTextureKey(pieceType as PieceType, 'filled'), pieceTexture);
  }

  loaded = true;
}

/**
 * Get the texture for a piece type and player
 * Player 1 uses outline (white) sprites, players 2-4 use filled (black) sprites
 */
export function getPieceTexture(pieceType: PieceType, player: number = 1): Texture {
  const style = player === 1 ? 'outline' : 'filled';
  const key = getTextureKey(pieceType, style);
  const texture = spriteTextures.get(key);
  if (!texture) {
    throw new Error(`Texture not found for piece type: ${pieceType}, style: ${style}. Make sure loadSprites() was called.`);
  }
  return texture;
}

/**
 * Get the tint color for a player
 */
export function getPlayerTint(player: number): number {
  return PLAYER_COLORS[player] ?? 0xffffff;
}

/**
 * Check if sprites are loaded
 */
export function areSpritesLoaded(): boolean {
  return loaded;
}

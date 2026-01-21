/**
 * Game Renderer - PixiJS Board and Piece Rendering
 *
 * Handles all visual rendering of the chess board:
 * - Board squares (including 4-player corners)
 * - Piece sprites with player color tinting
 * - Selection and legal move highlights
 * - Cooldown overlay indicators
 * - Move animations via interpolation
 */

import { Application, Container, Graphics, Sprite } from 'pixi.js';
import { getPieceTexture, getPlayerTint, loadSprites, areSpritesLoaded, type PieceType } from './sprites';
import {
  BOARD_COLORS,
  BOARD_DIMENSIONS,
  RENDER,
  getSquareColor,
  isValidSquare,
  transformToViewCoords,
  transformToGameCoords,
} from './constants';
import { interpolatePiecePosition, calculateCooldownProgress, type ActiveMove } from './interpolation';

// Types
export type BoardType = 'standard' | 'four_player';

export interface RendererPiece {
  id: string;
  type: PieceType;
  player: number;
  row: number;
  col: number;
  captured: boolean;
  moving: boolean;
  onCooldown: boolean;
}

export interface RendererCooldown {
  pieceId: string;
  remainingTicks: number;
}

export interface RendererOptions {
  canvas: HTMLCanvasElement;
  boardType: BoardType;
  playerNumber?: number; // For board rotation (0 = spectator, uses player 1 view)
  squareSize?: number;
  onSquareClick?: (row: number, col: number) => void;
  onPieceClick?: (pieceId: string) => void;
}

interface PieceSprite {
  container: Container;
  sprite: Sprite;
  cooldownOverlay: Graphics;
}

/**
 * GameRenderer - Main rendering class
 */
export class GameRenderer {
  private app: Application;
  private boardType: BoardType;
  private playerNumber: number; // For board rotation
  private squareSize: number;
  private boardWidth: number;
  private boardHeight: number;

  // Containers for layered rendering
  private boardContainer: Container;
  private highlightContainer: Container;
  private piecesContainer: Container;

  // Sprite tracking
  private pieceSprites: Map<string, PieceSprite> = new Map();

  // Callbacks
  private onSquareClick?: (row: number, col: number) => void;
  private onPieceClick?: (pieceId: string) => void;

  // State
  private initialized = false;
  private hoveredViewSquare: { row: number; col: number } | null = null;

  constructor(options: RendererOptions) {
    this.boardType = options.boardType;
    this.playerNumber = options.playerNumber ?? 1; // Default to player 1 view
    this.squareSize = options.squareSize ?? RENDER.SQUARE_SIZE;
    this.onSquareClick = options.onSquareClick;
    this.onPieceClick = options.onPieceClick;

    const dims = BOARD_DIMENSIONS[this.boardType];
    this.boardWidth = dims.width;
    this.boardHeight = dims.height;

    // Create PixiJS application
    this.app = new Application();

    // Create containers
    this.boardContainer = new Container();
    this.highlightContainer = new Container();
    this.piecesContainer = new Container();
  }

  /**
   * Update the player number (for board rotation)
   * Call this when the player number changes after initialization
   */
  setPlayerNumber(playerNumber: number): void {
    this.playerNumber = playerNumber || 1; // Spectators (0) use player 1 view
    // Re-render board to update square colors for rotated view
    if (this.initialized) {
      this.renderBoard();
    }
  }

  /**
   * Initialize the renderer (async due to sprite loading)
   */
  async init(canvas: HTMLCanvasElement): Promise<void> {
    if (this.initialized) return;

    // Initialize PixiJS app
    await this.app.init({
      canvas,
      width: this.boardWidth * this.squareSize,
      height: this.boardHeight * this.squareSize,
      backgroundColor: 0x1a1a2e,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });

    // Load sprites
    if (!areSpritesLoaded()) {
      await loadSprites();
    }

    // Add containers in layer order
    this.app.stage.addChild(this.boardContainer);
    this.app.stage.addChild(this.highlightContainer);
    this.app.stage.addChild(this.piecesContainer);

    // Render the board
    this.renderBoard();

    // Setup click handling
    this.setupClickHandling();

    this.initialized = true;
  }

  /**
   * Render the chess board squares
   * Squares are rendered at view positions but colored based on game coordinates
   */
  private renderBoard(): void {
    this.boardContainer.removeChildren();

    // Iterate over view coordinates
    for (let viewRow = 0; viewRow < this.boardHeight; viewRow++) {
      for (let viewCol = 0; viewCol < this.boardWidth; viewCol++) {
        // Transform view coords to game coords for color lookup
        const gameCoords = transformToGameCoords(
          { row: viewRow, col: viewCol },
          this.playerNumber,
          this.boardType
        );

        const color = getSquareColor(gameCoords.row, gameCoords.col, this.boardType);
        const square = new Graphics();
        square.rect(0, 0, this.squareSize, this.squareSize);
        square.fill(color);
        square.position.set(viewCol * this.squareSize, viewRow * this.squareSize);
        this.boardContainer.addChild(square);
      }
    }
  }

  /**
   * Setup click and hover handling for the board
   */
  private setupClickHandling(): void {
    this.app.stage.eventMode = 'static';
    this.app.stage.hitArea = this.app.screen;

    this.app.stage.on('pointerdown', (event) => {
      const localPos = event.global;
      const viewCol = Math.floor(localPos.x / this.squareSize);
      const viewRow = Math.floor(localPos.y / this.squareSize);

      // Transform view coordinates to game coordinates
      const gameCoords = transformToGameCoords(
        { row: viewRow, col: viewCol },
        this.playerNumber,
        this.boardType
      );

      // Check if click is on a valid square (using game coordinates)
      if (!isValidSquare(gameCoords.row, gameCoords.col, this.boardType)) {
        return;
      }

      // Check if we clicked on a piece (using view coordinates for sprite lookup)
      const clickedPiece = this.findPieceAt(viewRow, viewCol);
      if (clickedPiece && this.onPieceClick) {
        this.onPieceClick(clickedPiece);
        return;
      }

      // Otherwise, it's a square click (for making moves) - pass game coordinates
      if (this.onSquareClick) {
        this.onSquareClick(gameCoords.row, gameCoords.col);
      }
    });

    // Track hover position for ghost piece rendering
    this.app.stage.on('pointermove', (event) => {
      const localPos = event.global;
      const viewCol = Math.floor(localPos.x / this.squareSize);
      const viewRow = Math.floor(localPos.y / this.squareSize);

      // Update hovered square if it changed
      if (
        !this.hoveredViewSquare ||
        this.hoveredViewSquare.row !== viewRow ||
        this.hoveredViewSquare.col !== viewCol
      ) {
        this.hoveredViewSquare = { row: viewRow, col: viewCol };
      }
    });

    // Clear hover when pointer leaves the stage
    this.app.stage.on('pointerleave', () => {
      this.hoveredViewSquare = null;
    });
  }

  /**
   * Find a piece at a given view position using distance-based hit detection.
   * This works correctly even during animations when pieces are between squares.
   */
  private findPieceAt(viewRow: number, viewCol: number): string | null {
    // Calculate click center in pixels
    const clickX = (viewCol + 0.5) * this.squareSize;
    const clickY = (viewRow + 0.5) * this.squareSize;

    // Hit detection threshold - within 60% of square size from piece center
    const threshold = this.squareSize * 0.6;

    let closestPiece: string | null = null;
    let closestDistance = Infinity;

    for (const [pieceId, pieceData] of this.pieceSprites) {
      const sprite = pieceData.container;
      // Piece center is at sprite position + half square size
      const pieceCenterX = sprite.x + this.squareSize / 2;
      const pieceCenterY = sprite.y + this.squareSize / 2;

      const dx = clickX - pieceCenterX;
      const dy = clickY - pieceCenterY;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < threshold && distance < closestDistance) {
        closestPiece = pieceId;
        closestDistance = distance;
      }
    }

    return closestPiece;
  }

  /**
   * Update piece positions and states
   */
  renderPieces(
    pieces: RendererPiece[],
    activeMoves: ActiveMove[],
    cooldowns: RendererCooldown[],
    currentTick: number,
    ticksPerSquare: number = 10
  ): void {
    // Create a map of active moves by piece ID
    const activeMoveMap = new Map(activeMoves.map((m) => [m.pieceId, m]));
    const cooldownMap = new Map(cooldowns.map((c) => [c.pieceId, c]));

    // Track which pieces we've seen (to remove old ones)
    const seenPieces = new Set<string>();

    for (const piece of pieces) {
      seenPieces.add(piece.id);

      // Skip captured pieces
      if (piece.captured) {
        this.removePieceSprite(piece.id);
        continue;
      }

      // Get or create sprite
      let pieceSprite = this.pieceSprites.get(piece.id);
      if (!pieceSprite) {
        pieceSprite = this.createPieceSprite(piece);
        this.pieceSprites.set(piece.id, pieceSprite);
        this.piecesContainer.addChild(pieceSprite.container);
      }

      // Update sprite texture and tint if piece type changed (promotion)
      this.updatePieceSpriteAppearance(pieceSprite, piece);

      // Calculate interpolated position (in game coordinates)
      const activeMove = activeMoveMap.get(piece.id) ?? null;
      const gamePosition = interpolatePiecePosition(
        { row: piece.row, col: piece.col },
        activeMove,
        currentTick,
        ticksPerSquare
      );

      // Transform game coordinates to view coordinates for rendering
      const viewPosition = transformToViewCoords(
        gamePosition,
        this.playerNumber,
        this.boardType
      );

      // Update position using view coordinates
      pieceSprite.container.x = viewPosition.col * this.squareSize;
      pieceSprite.container.y = viewPosition.row * this.squareSize;

      // Update cooldown overlay
      const cooldown = cooldownMap.get(piece.id);
      this.updateCooldownOverlay(pieceSprite, cooldown);
    }

    // Remove sprites for pieces no longer present
    for (const [pieceId] of this.pieceSprites) {
      if (!seenPieces.has(pieceId)) {
        this.removePieceSprite(pieceId);
      }
    }
  }

  /**
   * Create a sprite for a piece
   * Uses original alignment logic: SPRITE_FACTOR=0.90, with minimal offset
   * Original: cellPadding - shift ≈ 0 (they nearly cancel out)
   */
  private createPieceSprite(piece: RendererPiece): PieceSprite {
    const container = new Container();

    // Create the piece sprite - use appropriate texture based on player
    const texture = getPieceTexture(piece.type, piece.player);
    const sprite = new Sprite(texture);

    // Original alignment: sprite is 90% of cell size
    const SPRITE_FACTOR = 0.90;
    const targetSize = this.squareSize * SPRITE_FACTOR;
    const scale = targetSize / Math.max(texture.width, texture.height);
    sprite.scale.set(scale);

    // Original uses cellPadding - shift which nearly cancel out
    // cellPadding = cellDim * 0.05, shift ≈ cellDim * 0.04
    // Net offset is about 1% of cell size
    const offset = this.squareSize * 0.01;
    sprite.anchor.set(0, 0);
    sprite.x = offset;
    sprite.y = offset;

    // Apply player tint (only for players 3-4, player 2 is already black)
    if (piece.player >= 3) {
      sprite.tint = getPlayerTint(piece.player);
    }

    container.addChild(sprite);

    // Create cooldown overlay (a vertical bar that drains)
    const cooldownOverlay = new Graphics();
    cooldownOverlay.visible = false;
    container.addChild(cooldownOverlay);

    return { container, sprite, cooldownOverlay };
  }

  /**
   * Update a piece sprite's appearance (for promotions)
   */
  private updatePieceSpriteAppearance(pieceSprite: PieceSprite, piece: RendererPiece): void {
    const texture = getPieceTexture(piece.type, piece.player);
    if (pieceSprite.sprite.texture !== texture) {
      pieceSprite.sprite.texture = texture;
      const SPRITE_FACTOR = 0.90;
      const targetSize = this.squareSize * SPRITE_FACTOR;
      const scale = targetSize / Math.max(texture.width, texture.height);
      pieceSprite.sprite.scale.set(scale);

      // Update position offset when texture changes
      const offset = this.squareSize * 0.01;
      pieceSprite.sprite.x = offset;
      pieceSprite.sprite.y = offset;
    }
    // Only tint players 3-4, player 2 uses filled black sprites
    if (piece.player >= 3) {
      pieceSprite.sprite.tint = getPlayerTint(piece.player);
    } else {
      pieceSprite.sprite.tint = 0xffffff; // No tint for players 1-2
    }
  }

  /**
   * Update the cooldown overlay for a piece
   */
  private updateCooldownOverlay(
    pieceSprite: PieceSprite,
    cooldown: RendererCooldown | undefined
  ): void {
    const overlay = pieceSprite.cooldownOverlay;

    if (!cooldown || cooldown.remainingTicks <= 0) {
      overlay.visible = false;
      return;
    }

    // Calculate cooldown progress (0 = full cooldown, 1 = done)
    const progress = calculateCooldownProgress(cooldown.remainingTicks);

    // Draw overlay that drains downward (top disappears first, bottom remains)
    const remainingHeight = this.squareSize * (1 - progress);
    const yOffset = this.squareSize * progress;

    overlay.clear();
    overlay.rect(0, yOffset, this.squareSize, remainingHeight);
    overlay.fill({ color: RENDER.COOLDOWN_OVERLAY_COLOR, alpha: RENDER.COOLDOWN_OVERLAY_ALPHA });
    overlay.visible = true;
  }

  /**
   * Remove a piece sprite
   */
  private removePieceSprite(pieceId: string): void {
    const pieceSprite = this.pieceSprites.get(pieceId);
    if (pieceSprite) {
      this.piecesContainer.removeChild(pieceSprite.container);
      pieceSprite.container.destroy();
      this.pieceSprites.delete(pieceId);
    }
  }

  /**
   * Highlight the selected piece and legal move targets
   * Note: legalMoves are in game coordinates and will be transformed to view coordinates
   * When hovering a legal move square, shows a ghost piece instead of the circle
   */
  highlightSelection(
    selectedPieceId: string | null,
    legalMoves: [number, number][],
    selectedPieceType?: PieceType,
    selectedPiecePlayer?: number
  ): void {
    // Clear existing highlights
    this.highlightContainer.removeChildren();

    // Highlight selected piece's square with an outline (sprite is already at view position)
    if (selectedPieceId) {
      const pieceSprite = this.pieceSprites.get(selectedPieceId);
      if (pieceSprite) {
        const viewCol = Math.round(pieceSprite.container.x / this.squareSize);
        const viewRow = Math.round(pieceSprite.container.y / this.squareSize);

        const strokeWidth = RENDER.SELECTION_STROKE_WIDTH;
        const highlight = new Graphics();
        // Draw outline inside the square (inset by half stroke width)
        highlight.rect(
          strokeWidth / 2,
          strokeWidth / 2,
          this.squareSize - strokeWidth,
          this.squareSize - strokeWidth
        );
        highlight.stroke({ color: BOARD_COLORS.selected, width: strokeWidth });
        highlight.position.set(viewCol * this.squareSize, viewRow * this.squareSize);
        this.highlightContainer.addChild(highlight);
      }
    }

    // Check if hovered square is a legal move (convert hover to game coords for comparison)
    let hoveredLegalMove: [number, number] | null = null;
    if (this.hoveredViewSquare) {
      const hoveredGameCoords = transformToGameCoords(
        this.hoveredViewSquare,
        this.playerNumber,
        this.boardType
      );
      for (const [gameRow, gameCol] of legalMoves) {
        if (gameRow === hoveredGameCoords.row && gameCol === hoveredGameCoords.col) {
          hoveredLegalMove = [gameRow, gameCol];
          break;
        }
      }
    }

    // Highlight legal move targets (transform game coords to view coords)
    for (const [gameRow, gameCol] of legalMoves) {
      const viewCoords = transformToViewCoords(
        { row: gameRow, col: gameCol },
        this.playerNumber,
        this.boardType
      );

      const isHovered =
        hoveredLegalMove &&
        hoveredLegalMove[0] === gameRow &&
        hoveredLegalMove[1] === gameCol;

      if (isHovered && selectedPieceType && selectedPiecePlayer !== undefined) {
        // Show ghost piece on hovered legal move square
        const texture = getPieceTexture(selectedPieceType, selectedPiecePlayer);
        const ghostSprite = new Sprite(texture);

        // Same sizing as regular pieces
        const SPRITE_FACTOR = 0.90;
        const targetSize = this.squareSize * SPRITE_FACTOR;
        const scale = targetSize / Math.max(texture.width, texture.height);
        ghostSprite.scale.set(scale);

        // Same positioning as regular pieces
        const offset = this.squareSize * 0.01;
        ghostSprite.anchor.set(0, 0);
        ghostSprite.x = offset;
        ghostSprite.y = offset;

        // Apply tint for players 3-4
        if (selectedPiecePlayer >= 3) {
          ghostSprite.tint = getPlayerTint(selectedPiecePlayer);
        }

        // Make it translucent
        ghostSprite.alpha = 0.5;

        // Create container and position it
        const ghostContainer = new Container();
        ghostContainer.addChild(ghostSprite);
        ghostContainer.position.set(
          viewCoords.col * this.squareSize,
          viewCoords.row * this.squareSize
        );
        this.highlightContainer.addChild(ghostContainer);
      } else {
        // Draw a circle indicator for non-hovered legal moves
        const highlight = new Graphics();
        const centerX = this.squareSize / 2;
        const centerY = this.squareSize / 2;
        const radius = this.squareSize / 4;

        highlight.circle(centerX, centerY, radius);
        highlight.fill({ color: BOARD_COLORS.legalMove, alpha: RENDER.LEGAL_MOVE_ALPHA });
        highlight.position.set(viewCoords.col * this.squareSize, viewCoords.row * this.squareSize);
        this.highlightContainer.addChild(highlight);
      }
    }
  }

  /**
   * Clear all highlights
   */
  clearHighlights(): void {
    this.highlightSelection(null, []);
  }

  /**
   * Get the canvas dimensions
   */
  getDimensions(): { width: number; height: number } {
    return {
      width: this.boardWidth * this.squareSize,
      height: this.boardHeight * this.squareSize,
    };
  }

  /**
   * Resize the renderer
   */
  resize(squareSize: number): void {
    this.squareSize = squareSize;
    this.app.renderer.resize(
      this.boardWidth * this.squareSize,
      this.boardHeight * this.squareSize
    );
    this.renderBoard();
    // Piece positions will be updated on next renderPieces call
  }

  /**
   * Clean up the renderer
   */
  destroy(): void {
    // Only destroy if the app was fully initialized
    if (this.initialized) {
      this.app.destroy(true, { children: true, texture: false });
    }
    this.pieceSprites.clear();
    this.initialized = false;
  }
}

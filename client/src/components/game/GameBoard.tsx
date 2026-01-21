/**
 * GameBoard Component
 *
 * React wrapper around the PixiJS game renderer.
 * Handles initialization, cleanup, and connecting the renderer to the game store.
 */

import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { useGameStore } from '../../stores/game';
import { GameRenderer, type BoardType, TIMING, getLegalMovesForPiece } from '../../game';

interface GameBoardProps {
  boardType: BoardType;
  squareSize?: number;
}

export function GameBoard({ boardType, squareSize = 64 }: GameBoardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<GameRenderer | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const [isReady, setIsReady] = useState(false);

  // Use refs for callbacks to avoid recreating the renderer
  const handlePieceClickRef = useRef<(pieceId: string) => void>(() => {});
  const handleSquareClickRef = useRef<(row: number, col: number) => void>(() => {});

  // Get state and actions from store
  const pieces = useGameStore((s) => s.pieces);
  const activeMoves = useGameStore((s) => s.activeMoves);
  const cooldowns = useGameStore((s) => s.cooldowns);
  const currentTick = useGameStore((s) => s.currentTick);
  const lastTickTime = useGameStore((s) => s.lastTickTime);
  const selectedPieceId = useGameStore((s) => s.selectedPieceId);
  const playerNumber = useGameStore((s) => s.playerNumber);
  const status = useGameStore((s) => s.status);
  const speed = useGameStore((s) => s.speed);

  const selectPiece = useGameStore((s) => s.selectPiece);
  const makeMove = useGameStore((s) => s.makeMove);

  // Compute legal moves dynamically based on current game state
  // This updates as pieces move and paths open/close
  const ticksPerSquare = speed === 'lightning'
    ? TIMING.LIGHTNING_TICKS_PER_SQUARE
    : TIMING.STANDARD_TICKS_PER_SQUARE;

  const legalMoveTargets = useMemo(() => {
    if (!selectedPieceId) return [];

    const selectedPiece = pieces.find((p) => p.id === selectedPieceId);
    if (!selectedPiece || selectedPiece.captured || selectedPiece.moving || selectedPiece.onCooldown) {
      return [];
    }

    return getLegalMovesForPiece(
      pieces,
      activeMoves,
      currentTick,
      ticksPerSquare,
      selectedPiece
    );
  }, [selectedPieceId, pieces, activeMoves, currentTick, ticksPerSquare]);

  // Handle piece click
  const handlePieceClick = useCallback(
    (pieceId: string) => {
      if (status !== 'playing' || playerNumber === 0) return;

      const piece = pieces.find((p) => p.id === pieceId);
      if (!piece) return;

      // If clicking on already selected piece, deselect
      if (selectedPieceId === pieceId) {
        selectPiece(null);
        return;
      }

      // If it's our piece and available, select it
      if (piece.player === playerNumber && !piece.captured && !piece.moving && !piece.onCooldown) {
        selectPiece(pieceId);
      }
    },
    [status, playerNumber, pieces, selectedPieceId, selectPiece]
  );

  // Handle square click
  const handleSquareClick = useCallback(
    (row: number, col: number) => {
      if (status !== 'playing' || playerNumber === 0) return;

      // If no piece selected, try to select a piece at this square
      if (!selectedPieceId) {
        const pieceAtSquare = pieces.find(
          (p) => !p.captured && Math.round(p.row) === row && Math.round(p.col) === col
        );
        if (pieceAtSquare) {
          handlePieceClickRef.current(pieceAtSquare.id);
        }
        return;
      }

      // Check if this is a legal move target (using dynamically computed moves)
      const isLegalTarget = legalMoveTargets.some(
        ([targetRow, targetCol]) => targetRow === row && targetCol === col
      );

      if (isLegalTarget) {
        makeMove(row, col);
        return;
      }

      // Check if clicking on another of our pieces
      const pieceAtSquare = pieces.find(
        (p) => !p.captured && Math.round(p.row) === row && Math.round(p.col) === col
      );
      if (pieceAtSquare && pieceAtSquare.player === playerNumber) {
        handlePieceClickRef.current(pieceAtSquare.id);
        return;
      }

      // Deselect
      selectPiece(null);
    },
    [status, playerNumber, selectedPieceId, pieces, legalMoveTargets, makeMove, selectPiece]
  );

  // Keep refs updated with latest callbacks
  useEffect(() => {
    handlePieceClickRef.current = handlePieceClick;
    handleSquareClickRef.current = handleSquareClick;
  }, [handlePieceClick, handleSquareClick]);

  // Initialize renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = new GameRenderer({
      canvas,
      boardType,
      playerNumber: playerNumber || 1, // Spectators use player 1 view
      squareSize,
      // Use wrapper functions that call the refs
      onSquareClick: (row, col) => handleSquareClickRef.current(row, col),
      onPieceClick: (pieceId) => handlePieceClickRef.current(pieceId),
    });

    renderer
      .init(canvas)
      .then(() => {
        rendererRef.current = renderer;
        setIsReady(true);
      })
      .catch((error) => {
        console.error('Failed to initialize renderer:', error);
      });

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      renderer.destroy();
      rendererRef.current = null;
      setIsReady(false);
    };
  }, [boardType, squareSize, playerNumber]);

  // Render loop with visual tick interpolation
  useEffect(() => {
    if (!isReady || !rendererRef.current) return;

    // Get timing constants based on speed
    const ticksPerSquare = speed === 'lightning'
      ? TIMING.LIGHTNING_TICKS_PER_SQUARE
      : TIMING.STANDARD_TICKS_PER_SQUARE;

    const render = () => {
      const renderer = rendererRef.current;
      if (!renderer) return;

      // Calculate visual tick for smooth 60fps animation
      // Interpolate between server ticks (which arrive at 10Hz)
      const now = performance.now();
      const timeSinceLastTick = now - lastTickTime;
      const tickFraction = Math.min(timeSinceLastTick / TIMING.TICK_PERIOD_MS, 1.0);
      const visualTick = currentTick + tickFraction;

      // Convert pieces to renderer format
      const rendererPieces = pieces.map((p) => ({
        id: p.id,
        type: p.type,
        player: p.player,
        row: p.row,
        col: p.col,
        captured: p.captured,
        moving: p.moving,
        onCooldown: p.onCooldown,
      }));

      // Convert active moves
      const rendererMoves = activeMoves.map((m) => ({
        pieceId: m.pieceId,
        path: m.path,
        startTick: m.startTick,
      }));

      // Convert cooldowns
      const rendererCooldowns = cooldowns.map((c) => ({
        pieceId: c.pieceId,
        remainingTicks: c.remainingTicks,
      }));

      // Render pieces with visual tick for smooth animation
      renderer.renderPieces(
        rendererPieces,
        rendererMoves,
        rendererCooldowns,
        visualTick,
        ticksPerSquare
      );

      // Update highlights (pass selected piece info for ghost rendering on hover)
      const selectedPiece = selectedPieceId
        ? pieces.find((p) => p.id === selectedPieceId)
        : null;
      renderer.highlightSelection(
        selectedPieceId,
        legalMoveTargets,
        selectedPiece?.type,
        selectedPiece?.player
      );

      animationFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isReady, pieces, activeMoves, cooldowns, currentTick, lastTickTime, selectedPieceId, legalMoveTargets, speed]);

  // Calculate canvas dimensions
  const boardDims = boardType === 'four_player' ? { width: 12, height: 12 } : { width: 8, height: 8 };
  const canvasWidth = boardDims.width * squareSize;
  const canvasHeight = boardDims.height * squareSize;

  return (
    <div className="game-board-container" style={{ width: canvasWidth, height: canvasHeight }}>
      <canvas
        ref={canvasRef}
        width={canvasWidth}
        height={canvasHeight}
        style={{
          display: 'block',
          width: canvasWidth,
          height: canvasHeight,
        }}
      />
      {!isReady && (
        <div
          className="game-board-loading"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: canvasWidth,
            height: canvasHeight,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            color: 'white',
          }}
        >
          Loading...
        </div>
      )}
    </div>
  );
}

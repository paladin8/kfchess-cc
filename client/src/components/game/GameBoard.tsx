/**
 * GameBoard Component
 *
 * React wrapper around the PixiJS game renderer.
 * Handles initialization, cleanup, and connecting the renderer to the game store.
 *
 * ## Tick Timing: currentTick vs visualTick
 *
 * The game uses two different tick values for different purposes:
 *
 * **currentTick** (from game store):
 * - The tick value from the last server update
 * - Only updates when the server sends a StateUpdateMessage
 * - Server optimizes bandwidth by only sending updates when state changes
 *   (new moves, cooldown changes, captures, etc.)
 * - Can be "stale" between server updates (potentially seconds behind)
 * - Should NOT be used for time-sensitive client-side calculations
 *
 * **visualTick** (calculated in render loop):
 * - Interpolated tick based on elapsed time since last server update
 * - Formula: currentTick + (elapsedTime / tickPeriod)
 * - Updates every frame (60fps) for smooth animation
 * - Used for: piece position interpolation, cooldown display, legal move calculation
 * - Provides accurate "what tick is it right now?" estimation
 *
 * Legal move calculation uses visualTick (floored to integer) to ensure that
 * forward path blocking is calculated based on where pieces actually are visually,
 * not where they were at the last server update.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { useGameStore, selectIsPlayerEliminated } from '../../stores/game';
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
  const timeSinceTick = useGameStore((s) => s.timeSinceTick);
  const selectedPieceId = useGameStore((s) => s.selectedPieceId);
  const playerNumber = useGameStore((s) => s.playerNumber);
  const status = useGameStore((s) => s.status);
  const speed = useGameStore((s) => s.speed);
  const tickRateHz = useGameStore((s) => s.tickRateHz);

  const selectPiece = useGameStore((s) => s.selectPiece);
  const makeMove = useGameStore((s) => s.makeMove);
  const isEliminated = useGameStore(selectIsPlayerEliminated);

  // Store latest values in refs so the render loop can access them without restarting
  const gameStateRef = useRef({
    pieces,
    activeMoves,
    cooldowns,
    currentTick,
    lastTickTime,
    timeSinceTick,
    selectedPieceId,
    speed,
    tickRateHz,
    boardType,
    // Legal move calculation state (computed in render loop using visualTick)
    legalMoveTargets: [] as [number, number][],
    lastLegalMoveTick: -1, // Track last tick used to compute legal moves (for optimization)
    lastLegalMoveSelectedId: null as string | null, // Track selected piece for cache invalidation
  });
  // Update ref on every render (this doesn't cause re-renders)
  gameStateRef.current = {
    pieces,
    activeMoves,
    cooldowns,
    currentTick,
    lastTickTime,
    timeSinceTick,
    selectedPieceId,
    speed,
    tickRateHz,
    boardType,
    // Preserve computed values from render loop
    legalMoveTargets: gameStateRef.current.legalMoveTargets,
    lastLegalMoveTick: gameStateRef.current.lastLegalMoveTick,
    lastLegalMoveSelectedId: gameStateRef.current.lastLegalMoveSelectedId,
  };

  // Legal moves are computed in the render loop using visualTick (not currentTick)
  // This ensures forward path blocking uses the actual interpolated piece positions
  // See render loop below for the calculation
  //
  // NOTE: Callbacks must read from gameStateRef.current.legalMoveTargets directly
  // (not a captured variable) to get the latest values from the render loop.

  // Handle piece click
  const handlePieceClick = useCallback(
    (pieceId: string) => {
      if (status !== 'playing' || playerNumber === 0 || isEliminated) return;

      const piece = pieces.find((p) => p.id === pieceId);
      if (!piece) return;

      // If clicking on already selected piece, deselect
      if (selectedPieceId === pieceId) {
        selectPiece(null);
        return;
      }

      // If it's our piece and available, select it
      if (piece.player === playerNumber && !piece.captured && !piece.moving) {
        selectPiece(pieceId);
        return;
      }

      // If we have a piece selected and click on an enemy piece that's a legal target, capture it
      if (selectedPieceId && piece.player !== playerNumber) {
        const pieceRow = Math.round(piece.row);
        const pieceCol = Math.round(piece.col);
        // Read from ref to get latest legal moves computed by render loop
        const isLegalTarget = gameStateRef.current.legalMoveTargets.some(
          ([targetRow, targetCol]) => targetRow === pieceRow && targetCol === pieceCol
        );
        if (isLegalTarget) {
          makeMove(pieceRow, pieceCol);
          return;
        }
      }
    },
    [status, playerNumber, isEliminated, pieces, selectedPieceId, selectPiece, makeMove]
  );

  // Handle square click
  const handleSquareClick = useCallback(
    (row: number, col: number) => {
      if (status !== 'playing' || playerNumber === 0 || isEliminated) return;

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
      // Read from ref to get latest legal moves computed by render loop
      const isLegalTarget = gameStateRef.current.legalMoveTargets.some(
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
    [status, playerNumber, isEliminated, selectedPieceId, pieces, makeMove, selectPiece]
  );

  // Keep refs updated with latest callbacks
  useEffect(() => {
    handlePieceClickRef.current = handlePieceClick;
    handleSquareClickRef.current = handleSquareClick;
  }, [handlePieceClick, handleSquareClick]);

  // Store playerNumber in a ref so the init effect doesn't depend on it
  const playerNumberRef = useRef(playerNumber);
  playerNumberRef.current = playerNumber;

  // Track latest square size without forcing renderer re-initialization
  const latestSquareSizeRef = useRef(squareSize);
  latestSquareSizeRef.current = squareSize;

  // Initialize renderer (only when boardType changes, NOT squareSize/playerNumber)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let cancelled = false;
    const initialSquareSize = latestSquareSizeRef.current;

    const renderer = new GameRenderer({
      canvas,
      boardType,
      playerNumber: playerNumberRef.current || 1, // Use ref for initial value
      squareSize: initialSquareSize,
      // Use wrapper functions that call the refs
      onSquareClick: (row, col) => handleSquareClickRef.current(row, col),
      onPieceClick: (pieceId) => handlePieceClickRef.current(pieceId),
    });

    renderer
      .init(canvas)
      .then(() => {
        if (cancelled) {
          renderer.destroy();
          return;
        }

        rendererRef.current = renderer;
        const latestSquareSize = latestSquareSizeRef.current;
        if (latestSquareSize !== initialSquareSize) {
          renderer.resize(latestSquareSize);
        }
        setIsReady(true);
      })
      .catch((error) => {
        if (!cancelled) {
          console.error('Failed to initialize renderer:', error);
        }
      });

    return () => {
      cancelled = true;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      renderer.destroy();
      rendererRef.current = null;
      setIsReady(false);
    };
  }, [boardType]); // squareSize updates use renderer.resize below

  // Update player number without recreating renderer
  useEffect(() => {
    if (rendererRef.current && playerNumber) {
      rendererRef.current.setPlayerNumber(playerNumber);
    }
  }, [playerNumber]);

  // Resize renderer without destroying/recreating Pixi application
  useEffect(() => {
    if (rendererRef.current) {
      rendererRef.current.resize(squareSize);
    }
  }, [squareSize]);

  // Render loop with visual tick interpolation
  // Uses refs to read latest state without restarting the animation loop
  useEffect(() => {
    if (!isReady || !rendererRef.current) return;

    const render = () => {
      const renderer = rendererRef.current;
      if (!renderer) return;

      // Read latest state from ref (avoids effect restart on state change)
      const state = gameStateRef.current;

      // Get timing constants based on speed
      const ticksPerSquare = state.speed === 'lightning'
        ? TIMING.LIGHTNING_TICKS_PER_SQUARE
        : TIMING.STANDARD_TICKS_PER_SQUARE;

      // Calculate visual tick for smooth 60fps animation
      // Interpolate between server ticks (which may now arrive less frequently due to optimization)
      // Account for server's time_since_tick to stay in sync
      const now = performance.now();
      const timeSinceLastTick = now - state.lastTickTime;
      // Combine client-side elapsed time with server's time_since_tick offset
      // Guard against negative values (can happen briefly after state updates)
      const totalElapsed = Math.max(0, timeSinceLastTick + state.timeSinceTick);
      // Allow interpolation up to 10 seconds to handle sparse updates
      // This covers even the longest possible moves (7 squares at 1 sec/square = 7 seconds)
      // Use server's tick rate for accurate interpolation
      const tickPeriodMs = 1000 / state.tickRateHz;
      const maxInterpolationTicks = 10 * state.tickRateHz;
      const tickFraction = Math.min(totalElapsed / tickPeriodMs, maxInterpolationTicks);
      const visualTick = state.currentTick + tickFraction;

      // Compute legal moves using visualTick (floored to integer)
      // This ensures forward path blocking reflects actual piece positions, not stale server state
      // Optimization: only recalculate when tick changes or selection changes
      const flooredTick = Math.floor(visualTick);
      const needsLegalMoveRecalc =
        state.selectedPieceId !== state.lastLegalMoveSelectedId ||
        flooredTick !== state.lastLegalMoveTick;

      if (needsLegalMoveRecalc) {
        state.lastLegalMoveTick = flooredTick;
        state.lastLegalMoveSelectedId = state.selectedPieceId;

        if (!state.selectedPieceId) {
          state.legalMoveTargets = [];
        } else {
          const selectedPiece = state.pieces.find((p) => p.id === state.selectedPieceId);
          if (!selectedPiece || selectedPiece.captured || selectedPiece.moving || selectedPiece.onCooldown) {
            state.legalMoveTargets = [];
          } else {
            state.legalMoveTargets = getLegalMovesForPiece(
              state.pieces,
              state.activeMoves,
              flooredTick, // Use visualTick (floored) instead of stale currentTick
              ticksPerSquare,
              selectedPiece,
              state.boardType
            );
          }
        }
      }

      // Convert pieces to renderer format
      const rendererPieces = state.pieces.map((p) => ({
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
      const rendererMoves = state.activeMoves.map((m) => ({
        pieceId: m.pieceId,
        path: m.path,
        startTick: m.startTick,
      }));

      // Convert cooldowns with interpolation
      // Subtract elapsed ticks so cooldown timers decrease smoothly between server updates
      const rendererCooldowns = state.cooldowns.map((c) => ({
        pieceId: c.pieceId,
        remainingTicks: Math.max(0, c.remainingTicks - tickFraction),
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
      const selectedPiece = state.selectedPieceId
        ? state.pieces.find((p) => p.id === state.selectedPieceId)
        : null;
      renderer.highlightSelection(
        state.selectedPieceId,
        state.legalMoveTargets,
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
  }, [isReady]); // Only restart when renderer becomes ready

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

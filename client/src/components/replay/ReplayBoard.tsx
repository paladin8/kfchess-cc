/**
 * ReplayBoard Component
 *
 * Read-only board that renders replay state from the server.
 * Uses PixiJS GameRenderer but doesn't handle any user interaction.
 */

import { useEffect, useRef, useState } from 'react';
import { useReplayStore } from '../../stores/replay';
import { GameRenderer, type BoardType } from '../../game';

interface ReplayBoardProps {
  boardType: BoardType;
  squareSize?: number;
}

export function ReplayBoard({ boardType, squareSize = 64 }: ReplayBoardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<GameRenderer | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const [isReady, setIsReady] = useState(false);

  // Get state from replay store
  const pieces = useReplayStore((s) => s.pieces);
  const activeMoves = useReplayStore((s) => s.activeMoves);
  const cooldowns = useReplayStore((s) => s.cooldowns);
  const currentTick = useReplayStore((s) => s.currentTick);
  const lastTickTime = useReplayStore((s) => s.lastTickTime);
  const timeSinceTick = useReplayStore((s) => s.timeSinceTick);
  const isPlaying = useReplayStore((s) => s.isPlaying);
  const speed = useReplayStore((s) => s.speed);
  const tickRateHz = useReplayStore((s) => s.tickRateHz);

  // Store latest values in refs so the render loop can access them without restarting
  const replayStateRef = useRef({
    pieces,
    activeMoves,
    cooldowns,
    currentTick,
    lastTickTime,
    timeSinceTick,
    isPlaying,
    speed,
    tickRateHz,
  });
  // Update ref on every render
  replayStateRef.current = {
    pieces,
    activeMoves,
    cooldowns,
    currentTick,
    lastTickTime,
    timeSinceTick,
    isPlaying,
    speed,
    tickRateHz,
  };

  // Initialize renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = new GameRenderer({
      canvas,
      boardType,
      playerNumber: 1, // View from player 1's perspective
      squareSize,
      // No interaction handlers - replay is read-only
      onSquareClick: () => {},
      onPieceClick: () => {},
    });

    renderer
      .init(canvas)
      .then(() => {
        rendererRef.current = renderer;
        setIsReady(true);
      })
      .catch((error) => {
        console.error('Failed to initialize replay renderer:', error);
      });

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      renderer.destroy();
      rendererRef.current = null;
      setIsReady(false);
    };
  }, [boardType, squareSize]);

  // Render loop with visual tick interpolation
  // Uses refs to read latest state without restarting the animation loop
  useEffect(() => {
    if (!isReady || !rendererRef.current) return;

    const render = () => {
      const renderer = rendererRef.current;
      if (!renderer) return;

      // Read latest state from ref (avoids effect restart on state change)
      const state = replayStateRef.current;

      // Get timing constants based on speed and replay's tick rate
      // The ticksPerSquare must match the replay's tick rate for correct animation
      const replayTickRate = state.tickRateHz || 10;
      const tickPeriodMs = 1000 / replayTickRate;
      // Scale ticks per square based on replay's tick rate
      const baseTicksPerSquare = state.speed === 'lightning' ? 0.2 : 1.0; // seconds
      const ticksPerSquare = baseTicksPerSquare * replayTickRate;

      // Calculate visual tick for smooth animation
      // Only interpolate if playing
      let visualTick = state.currentTick;
      let tickFraction = 0;
      if (state.isPlaying) {
        const now = performance.now();
        const timeSinceLastTick = now - state.lastTickTime;
        // Combine client-side elapsed time with server's time_since_tick offset
        // Guard against negative values (can happen briefly after seeks or state updates)
        const totalElapsed = Math.max(0, timeSinceLastTick + state.timeSinceTick);
        // Allow interpolation up to 10 seconds to handle sparse updates
        // This covers even the longest possible moves
        const maxInterpolationTicks = 10 * replayTickRate;
        tickFraction = Math.min(totalElapsed / tickPeriodMs, maxInterpolationTicks);
        visualTick = state.currentTick + tickFraction;
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

      // Render pieces
      renderer.renderPieces(
        rendererPieces,
        rendererMoves,
        rendererCooldowns,
        visualTick,
        ticksPerSquare
      );

      // No selection highlighting in replay mode
      renderer.highlightSelection(null, [], undefined, undefined);

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
    <div className="replay-board-container" style={{ width: canvasWidth, height: canvasHeight }}>
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
          className="replay-board-loading"
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

/**
 * useSquareSize - Dynamic board square sizing hook
 *
 * Calculates the optimal square size for the chess board based on
 * the available container width. Responds to window resize and
 * container size changes via ResizeObserver.
 */

import { useEffect, useCallback, useState, type RefObject } from 'react';

const MAX_SQUARE_SIZE = 64;
const MIN_SQUARE_SIZE = 24;
const BOARD_BORDER_PX = 8; // 4px border on each side

export function useSquareSize(
  boardType: 'standard' | 'four_player',
  boardAreaRef: RefObject<HTMLDivElement | null>,
  /** Pass a truthy value that changes when the ref target mounts (e.g. a loaded ID) */
  refReady?: unknown
): number {
  const gridSize = boardType === 'four_player' ? 12 : 8;

  const calc = useCallback(() => {
    const containerWidth = boardAreaRef.current?.clientWidth ?? document.documentElement.clientWidth;
    const available = Math.max(0, containerWidth - BOARD_BORDER_PX);
    const nextSize = Math.floor(available / gridSize);
    return Math.max(MIN_SQUARE_SIZE, Math.min(MAX_SQUARE_SIZE, nextSize));
  }, [boardAreaRef, gridSize]);

  const [squareSize, setSquareSize] = useState(() => calc());

  useEffect(() => {
    const update = () => {
      const nextSize = calc();
      setSquareSize((prevSize) => (prevSize === nextSize ? prevSize : nextSize));
    };

    let rafId: number | null = null;
    const scheduleUpdate = () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame(() => {
        rafId = null;
        update();
      });
    };

    update();

    const observerTarget = boardAreaRef.current;
    let resizeObserver: ResizeObserver | null = null;
    if (observerTarget && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(scheduleUpdate);
      resizeObserver.observe(observerTarget);
    }

    window.addEventListener('resize', scheduleUpdate);
    return () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      resizeObserver?.disconnect();
      window.removeEventListener('resize', scheduleUpdate);
    };
    // refReady triggers re-run when the ref target mounts after loading states
  }, [calc, boardAreaRef, refReady]);

  return squareSize;
}

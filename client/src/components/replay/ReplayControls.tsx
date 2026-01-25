/**
 * ReplayControls Component
 *
 * Playback controls for replay: play/pause button, seek slider, time display.
 */

import { useCallback, useState } from 'react';
import { useReplayStore, selectFormattedTime, selectFormattedTotalTime } from '../../stores/replay';
import './ReplayControls.css';

export function ReplayControls() {
  const currentTick = useReplayStore((s) => s.currentTick);
  const totalTicks = useReplayStore((s) => s.totalTicks);
  const isPlaying = useReplayStore((s) => s.isPlaying);
  const connectionState = useReplayStore((s) => s.connectionState);

  const play = useReplayStore((s) => s.play);
  const pause = useReplayStore((s) => s.pause);
  const seek = useReplayStore((s) => s.seek);

  const formattedTime = useReplayStore(selectFormattedTime);
  const formattedTotalTime = useReplayStore(selectFormattedTotalTime);

  // Track dragging state for the slider - only seek on release
  const [isDragging, setIsDragging] = useState(false);
  const [dragTick, setDragTick] = useState(0);

  const isConnected = connectionState === 'connected';
  const isAtEnd = currentTick >= totalTicks;

  const handlePlayPause = useCallback(() => {
    if (isPlaying) {
      pause();
    } else {
      // If at end, seek to beginning before playing
      if (isAtEnd) {
        seek(0);
      }
      play();
    }
  }, [isPlaying, isAtEnd, play, pause, seek]);

  const handleSliderMouseDown = useCallback(() => {
    setIsDragging(true);
    setDragTick(currentTick);
  }, [currentTick]);

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const tick = parseInt(e.target.value, 10);
      if (isDragging) {
        // During drag, just update local state for visual feedback
        setDragTick(tick);
      } else {
        // Direct click (not drag) - seek immediately
        seek(tick);
      }
    },
    [isDragging, seek]
  );

  const handleSliderMouseUp = useCallback(() => {
    if (isDragging) {
      // Seek to final position on release
      seek(dragTick);
      setIsDragging(false);
    }
  }, [isDragging, dragTick, seek]);

  const handleSkipBackward = useCallback(() => {
    // Skip back 5 seconds (50 ticks at 10 ticks/second)
    seek(Math.max(0, currentTick - 50));
  }, [currentTick, seek]);

  const handleSkipForward = useCallback(() => {
    // Skip forward 5 seconds (50 ticks)
    seek(Math.min(totalTicks, currentTick + 50));
  }, [currentTick, totalTicks, seek]);

  const handleRestart = useCallback(() => {
    seek(0);
  }, [seek]);

  // Use drag position during drag, otherwise current tick
  const displayTick = isDragging ? dragTick : currentTick;
  // Calculate progress percentage for the slider track fill
  const progress = totalTicks > 0 ? (displayTick / totalTicks) * 100 : 0;

  return (
    <div className="replay-controls">
      <div className="replay-controls-timeline">
        <span className="replay-time">{formattedTime}</span>
        <input
          type="range"
          className="replay-slider"
          min={0}
          max={totalTicks}
          value={displayTick}
          onMouseDown={handleSliderMouseDown}
          onChange={handleSliderChange}
          onMouseUp={handleSliderMouseUp}
          disabled={!isConnected}
          style={{
            background: `linear-gradient(to right, var(--color-primary) ${progress}%, var(--color-surface-light) ${progress}%)`,
          }}
        />
        <span className="replay-time">{formattedTotalTime}</span>
      </div>

      <div className="replay-controls-buttons">
        <button
          className="replay-button"
          onClick={handleRestart}
          disabled={!isConnected}
          title="Restart"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
          </svg>
        </button>

        <button
          className="replay-button"
          onClick={handleSkipBackward}
          disabled={!isConnected}
          title="Skip back 5s"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/>
          </svg>
        </button>

        <button
          className="replay-button replay-button-primary"
          onClick={handlePlayPause}
          disabled={!isConnected}
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
          )}
        </button>

        <button
          className="replay-button"
          onClick={handleSkipForward}
          disabled={!isConnected}
          title="Skip forward 5s"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

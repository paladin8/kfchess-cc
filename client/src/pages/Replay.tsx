/**
 * Replay Page
 *
 * Main replay viewer that displays a recorded game with playback controls.
 */

import { useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useReplayStore } from '../stores/replay';
import { ReplayBoard, ReplayControls } from '../components/replay';
import { AudioControls } from '../components/game';
import { useAudio } from '../hooks/useAudio';
import { formatWinReason } from '../utils/format';
import './Replay.css';

export function Replay() {
  const { replayId } = useParams<{ replayId: string }>();
  const navigate = useNavigate();

  // Track if effect is still active (handles React StrictMode double-mount)
  const isActiveRef = useRef(true);

  // Get state and actions from store
  const gameId = useReplayStore((s) => s.gameId);
  const boardType = useReplayStore((s) => s.boardType);
  const connectionState = useReplayStore((s) => s.connectionState);
  const error = useReplayStore((s) => s.error);
  const players = useReplayStore((s) => s.players);
  const winner = useReplayStore((s) => s.winner);
  const winReason = useReplayStore((s) => s.winReason);
  const speed = useReplayStore((s) => s.speed);

  const isPlaying = useReplayStore((s) => s.isPlaying);
  const pieces = useReplayStore((s) => s.pieces);
  const currentTick = useReplayStore((s) => s.currentTick);
  const totalTicks = useReplayStore((s) => s.totalTicks);

  const connect = useReplayStore((s) => s.connect);
  const disconnect = useReplayStore((s) => s.disconnect);

  // Audio management
  // Use currentTick >= totalTicks for isFinished (not winner, which is set at start from metadata)
  const replayEnded = totalTicks > 0 && currentTick >= totalTicks;
  const {
    musicVolume,
    soundVolume,
    setMusicVolume,
    setSoundVolume,
    playCaptureSound,
  } = useAudio({
    isPlaying: isPlaying,
    isFinished: replayEnded,
  });

  // Track captures by watching pieces that become captured
  const prevCapturedIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const currentCapturedIds = new Set(
      pieces.filter((p) => p.captured).map((p) => p.id)
    );

    // Find newly captured pieces
    let newCaptures = 0;
    currentCapturedIds.forEach((id) => {
      if (!prevCapturedIdsRef.current.has(id)) {
        newCaptures++;
      }
    });

    // Play capture sound for each new capture
    for (let i = 0; i < newCaptures; i++) {
      playCaptureSound();
    }

    prevCapturedIdsRef.current = currentCapturedIds;
  }, [pieces, playCaptureSound]);

  // Connect to replay on mount
  useEffect(() => {
    isActiveRef.current = true;

    if (!replayId) {
      navigate('/');
      return;
    }

    // Connect to replay WebSocket
    if (isActiveRef.current) {
      connect(replayId);
    }

    // Cleanup on unmount
    return () => {
      isActiveRef.current = false;
      disconnect();
    };
  }, [replayId, connect, disconnect, navigate]);

  // Show loading state
  if (connectionState === 'connecting') {
    return (
      <div className="replay-page">
        <div className="replay-loading">Connecting to replay...</div>
      </div>
    );
  }

  // Show error state
  if (error) {
    return (
      <div className="replay-page">
        <div className="replay-error">
          <h2>Error</h2>
          <p>{error}</p>
          <button className="replay-back-button" onClick={() => navigate('/')}>
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  // Show loading state while waiting for data
  if (!gameId || !boardType) {
    return (
      <div className="replay-page">
        <div className="replay-loading">Loading replay...</div>
      </div>
    );
  }

  return (
    <div className="replay-page">
      <div className="replay-content">
        <div className="replay-board-wrapper">
          <ReplayBoard boardType={boardType} squareSize={64} />
        </div>
        <div className="replay-sidebar">
          <div className="replay-info">
            <h2>Game Replay</h2>
            <div className="replay-info-row">
              <span className="replay-info-label">Game ID:</span>
              <span className="replay-info-value">{gameId}</span>
            </div>
            {speed && (
              <div className="replay-info-row">
                <span className="replay-info-label">Speed:</span>
                <span className="replay-info-value">{speed}</span>
              </div>
            )}
            {players && (
              <>
                {Object.entries(players).map(([playerNum, playerId]) => (
                  <div key={playerNum} className="replay-info-row">
                    <span className="replay-info-label">Player {playerNum}:</span>
                    <span className="replay-info-value">{playerId || 'Unknown'}</span>
                  </div>
                ))}
              </>
            )}
            {winner !== null && (
              <div className="replay-info-row replay-winner">
                <span className="replay-info-label">Winner:</span>
                <span className="replay-info-value">Player {winner}</span>
              </div>
            )}
            {winReason && (
              <div className="replay-info-row">
                <span className="replay-info-label">Result:</span>
                <span className="replay-info-value">{formatWinReason(winReason)}</span>
              </div>
            )}
          </div>

          <ReplayControls />

          <AudioControls
            musicVolume={musicVolume}
            soundVolume={soundVolume}
            onMusicVolumeChange={setMusicVolume}
            onSoundVolumeChange={setSoundVolume}
          />

          <button className="replay-back-button" onClick={() => navigate('/')}>
            Back to Home
          </button>
        </div>
      </div>
    </div>
  );
}

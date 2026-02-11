/**
 * Replay Page
 *
 * Main replay viewer that displays a recorded game with playback controls.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useReplayStore } from '../stores/replay';
import { useAuthStore } from '../stores/auth';
import { ReplayBoard, ReplayControls } from '../components/replay';
import { AudioControls } from '../components/game';
import { useAudio } from '../hooks/useAudio';
import { useSquareSize } from '../hooks/useSquareSize';
import { formatWinReason } from '../utils/format';
import { getReplayLikeStatus, likeReplay, unlikeReplay } from '../api/client';
import { track } from '../analytics';
import PlayerBadge from '../components/PlayerBadge';
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
  const isRanked = useReplayStore((s) => s.isRanked);

  const isPlaying = useReplayStore((s) => s.isPlaying);
  const pieces = useReplayStore((s) => s.pieces);
  const currentTick = useReplayStore((s) => s.currentTick);
  const totalTicks = useReplayStore((s) => s.totalTicks);
  const campaignLevelId = useReplayStore((s) => s.campaignLevelId);

  const connect = useReplayStore((s) => s.connect);
  const disconnect = useReplayStore((s) => s.disconnect);

  // Auth state for like functionality
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // Like state
  const [likes, setLikes] = useState(0);
  const [userHasLiked, setUserHasLiked] = useState(false);
  const [isLiking, setIsLiking] = useState(false);

  // Share link state
  const [copied, setCopied] = useState(false);

  // Dynamic board sizing
  const boardAreaRef = useRef<HTMLDivElement>(null);
  const squareSize = useSquareSize(boardType ?? 'standard', boardAreaRef, gameId);

  // Collapsible sidebar state (mobile)
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

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
      track('Watch Replay', { historyId: replayId });
      connect(replayId);
    }

    // Cleanup on unmount
    return () => {
      isActiveRef.current = false;
      disconnect();
    };
  }, [replayId, connect, disconnect, navigate]);

  // Fetch like status when replay loads
  useEffect(() => {
    if (replayId) {
      getReplayLikeStatus(replayId)
        .then((response) => {
          setLikes(response.likes);
          setUserHasLiked(response.user_has_liked);
        })
        .catch(() => {
          // Silently fail - likes are non-critical UI enhancement
          // Default values (0 likes, not liked) are acceptable fallback
        });
    }
  }, [replayId]);

  const copyReplayLink = useCallback(() => {
    if (!replayId) return;
    track('Copy Replay Link', { source: 'replay', gameId: replayId, historyId: replayId });
    const link = `${window.location.origin}/replay/${replayId}`;
    navigator.clipboard.writeText(link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [replayId]);

  const handleLikeClick = async () => {
    if (!isAuthenticated || isLiking || !replayId) return;

    setIsLiking(true);
    track(userHasLiked ? 'Unlike Replay' : 'Like Replay', { replayId });
    try {
      const response = userHasLiked
        ? await unlikeReplay(replayId)
        : await likeReplay(replayId);
      setLikes(response.likes);
      setUserHasLiked(response.user_has_liked);
    } catch (error) {
      console.error('Failed to toggle like:', error);
    } finally {
      setIsLiking(false);
    }
  };

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
      <div className={`replay-content${boardType === 'four_player' ? ' four-player' : ''}`}>
        <div className="replay-board-area" ref={boardAreaRef}>
          <div className="replay-board-wrapper">
            <ReplayBoard boardType={boardType} squareSize={squareSize} />
          </div>
        </div>
        <div className="replay-sidebar">
          <button
            className="replay-sidebar-toggle"
            onClick={() => setSidebarExpanded((v) => !v)}
          >
            Replay Info {sidebarExpanded ? '\u25B2' : '\u25BC'}
          </button>
          <div className={`replay-sidebar-details${sidebarExpanded ? ' expanded' : ''}`}>
            <div className="replay-info">
              <h2>Game Replay</h2>
              <div className="replay-info-row">
                <span className="replay-info-label">Share:</span>
                <button className="copy-link-button" onClick={copyReplayLink}>
                  {copied ? 'Copied!' : 'Copy Link'}
                </button>
              </div>
              {campaignLevelId !== null ? (
                <div className="replay-info-row">
                  <span className="replay-info-label">Mode:</span>
                  <span className="replay-info-value">
                    Campaign Level {campaignLevelId + 1}
                  </span>
                </div>
              ) : speed && (
                <div className="replay-info-row">
                  <span className="replay-info-label">Mode:</span>
                  <span className="replay-info-value">
                    {speed.charAt(0).toUpperCase() + speed.slice(1)}
                    {isRanked && ' (Rated)'}
                  </span>
                </div>
              )}
              {players && (
                <>
                  {Object.entries(players).map(([playerNum, player]) => (
                    <div key={playerNum} className="replay-info-row">
                      <span className="replay-info-label">Player {playerNum}:</span>
                      <span className="replay-info-value">
                        <PlayerBadge
                          userId={player.user_id}
                          username={player.name}
                          pictureUrl={player.picture_url}
                          size="sm"
                        />
                      </span>
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

          </div>

          <ReplayControls />

          <div className="replay-like-section">
            <button
              className={`replay-like-button ${userHasLiked ? 'liked' : ''}`}
              onClick={handleLikeClick}
              disabled={!isAuthenticated || isLiking}
            >
              <span className="like-icon">{userHasLiked ? '\u2764\ufe0f' : '\ud83e\udd0d'}</span>
              <span>{userHasLiked ? 'Liked' : 'Like'}</span>
              <span className="like-count">({likes})</span>
            </button>
            {!isAuthenticated && (
              <span className="like-hint">Log in to like this replay</span>
            )}
          </div>

          <AudioControls
            musicVolume={musicVolume}
            soundVolume={soundVolume}
            onMusicVolumeChange={setMusicVolume}
            onSoundVolumeChange={setSoundVolume}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Game Page
 *
 * Main game view that contains the board and game UI.
 */

import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useGameStore } from '../stores/game';
import { GameBoard, GameStatus, GameOverModal, AudioControls, ResignButton, DrawOfferButton } from '../components/game';
import { useAudio } from '../hooks/useAudio';
import { useSquareSize } from '../hooks/useSquareSize';
import { track } from '../analytics';
import './Game.css';

function getConnectionColor(connectionState: string): string {
  switch (connectionState) {
    case 'connected':
      return '#4ade80';
    case 'connecting':
    case 'reconnecting':
      return '#fbbf24';
    case 'disconnected':
      return '#f87171';
    default:
      return '#9ca3af';
  }
}

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Track if effect is still active (handles React StrictMode double-mount)
  const isActiveRef = useRef(true);

  // Get player key from URL or local storage
  const playerKeyFromUrl = searchParams.get('playerKey');

  // Store state only - actions accessed via getState() to avoid dependency issues
  const storeGameId = useGameStore((s) => s.gameId);
  const boardType = useGameStore((s) => s.boardType);
  const status = useGameStore((s) => s.status);
  const connectionState = useGameStore((s) => s.connectionState);
  const countdown = useGameStore((s) => s.countdown);
  const captureCount = useGameStore((s) => s.captureCount);
  const playerNumber = useGameStore((s) => s.playerNumber);
  const winner = useGameStore((s) => s.winner);
  const winReason = useGameStore((s) => s.winReason);
  const campaignLevel = useGameStore((s) => s.campaignLevel);
  const boardAreaRef = useRef<HTMLDivElement>(null);

  // Dynamic board sizing
  const squareSize = useSquareSize(boardType, boardAreaRef);

  // Collapsible sidebar state (mobile)
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

  // Audio management
  const {
    musicVolume,
    soundVolume,
    setMusicVolume,
    setSoundVolume,
    playCaptureSound,
  } = useAudio({
    isPlaying: status === 'playing',
    isFinished: status === 'finished',
  });

  // Track previous capture count to detect new captures
  const prevCaptureCountRef = useRef(captureCount);
  useEffect(() => {
    // Play capture sound for each new capture
    if (captureCount > prevCaptureCountRef.current) {
      const newCaptures = captureCount - prevCaptureCountRef.current;
      for (let i = 0; i < newCaptures; i++) {
        playCaptureSound();
      }
    }
    prevCaptureCountRef.current = captureCount;
  }, [captureCount, playCaptureSound]);

  // Analytics: track game start
  const prevStatusRef = useRef(status);
  useEffect(() => {
    if (status === 'playing' && prevStatusRef.current !== 'playing') {
      track('Start Game', {
        gameId: storeGameId,
        player: playerNumber,
        level: campaignLevel?.level_id ?? null,
      });
    }
    if (status === 'finished' && prevStatusRef.current !== 'finished') {
      track('Finish Game', {
        gameId: storeGameId,
        player: playerNumber,
        won: winner === playerNumber && playerNumber > 0,
        winner,
        winReason,
        level: campaignLevel?.level_id ?? null,
      });
    }
    prevStatusRef.current = status;
  }, [status, storeGameId, playerNumber, winner, winReason, campaignLevel]);

  // Stable action callbacks that don't change between renders
  const doConnect = useCallback(() => {
    useGameStore.getState().connect();
  }, []);

  const doDisconnect = useCallback(() => {
    useGameStore.getState().disconnect();
  }, []);

  const doJoinGame = useCallback((gId: string, pKey?: string) => {
    return useGameStore.getState().joinGame(gId, pKey);
  }, []);

  // Initialize game on mount
  useEffect(() => {
    isActiveRef.current = true;

    if (!gameId) {
      navigate('/');
      return;
    }

    // Get player key from URL or session storage
    const playerKey = playerKeyFromUrl || sessionStorage.getItem(`playerKey_${gameId}`);

    // If we have a player key from URL, save it to session storage
    if (playerKeyFromUrl) {
      sessionStorage.setItem(`playerKey_${gameId}`, playerKeyFromUrl);
      // Remove player key from URL for cleaner URLs
      const newUrl = window.location.pathname;
      window.history.replaceState({}, '', newUrl);
    }

    // Join the game
    doJoinGame(gameId, playerKey ?? undefined)
      .then(() => {
        // Only connect if still active (handles StrictMode double-mount)
        if (isActiveRef.current) {
          doConnect();
        }
      })
      .catch((error) => {
        console.error('Failed to join game:', error);
        // Navigate back to home on error
        if (isActiveRef.current) {
          navigate('/');
        }
      });

    // Cleanup on unmount
    return () => {
      isActiveRef.current = false;
      doDisconnect();
    };
  }, [gameId, playerKeyFromUrl, navigate, doJoinGame, doConnect, doDisconnect]);

  // Handle unexpected disconnection (only reconnect if we were previously connected)
  const wasConnectedRef = useRef(false);
  const reconnectingRef = useRef(false);

  useEffect(() => {
    // Track if we've ever been connected
    if (connectionState === 'connected') {
      wasConnectedRef.current = true;
      reconnectingRef.current = false;
    }

    // Only auto-reconnect if we were previously connected and got disconnected
    // Use reconnectingRef to prevent multiple reconnect attempts
    if (
      connectionState === 'disconnected' &&
      wasConnectedRef.current &&
      storeGameId &&
      status !== 'finished' &&
      !reconnectingRef.current
    ) {
      reconnectingRef.current = true;
      doConnect();
    }
  }, [connectionState, storeGameId, status, doConnect]);

  const statusDotColor = useMemo(() => getConnectionColor(connectionState), [connectionState]);

  // Don't render until we have game data
  if (!storeGameId) {
    return (
      <div className="game-page">
        <div className="game-loading">Loading game...</div>
      </div>
    );
  }

  return (
    <div className="game-page">
      <div className="game-content">
        <div className="game-board-area" ref={boardAreaRef}>
          <div className="game-board-wrapper">
            <GameBoard boardType={boardType} squareSize={squareSize} />
            {countdown !== null && (
              <div className="game-countdown-overlay">
                <div className="game-countdown-number">{countdown}</div>
              </div>
            )}
          </div>
        </div>
        <div className="game-sidebar">
          <button
            className="game-sidebar-toggle"
            onClick={() => setSidebarExpanded((v) => !v)}
          >
            <span className="status-dot" style={{ backgroundColor: statusDotColor }} />
            Game Info {sidebarExpanded ? '\u25B2' : '\u25BC'}
          </button>
          <div className={`game-sidebar-details${sidebarExpanded ? ' expanded' : ''}`}>
            <GameStatus />
          </div>
          {playerNumber > 0 && (
            <div className="game-action-buttons">
              <DrawOfferButton />
              <ResignButton />
            </div>
          )}
          <AudioControls
            musicVolume={musicVolume}
            soundVolume={soundVolume}
            onMusicVolumeChange={setMusicVolume}
            onSoundVolumeChange={setSoundVolume}
          />
        </div>
      </div>
      <GameOverModal />
    </div>
  );
}

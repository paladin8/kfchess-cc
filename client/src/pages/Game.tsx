/**
 * Game Page
 *
 * Main game view that contains the board and game UI.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useGameStore } from '../stores/game';
import { GameBoard, GameStatus, GameOverModal, AudioControls } from '../components/game';
import { useAudio } from '../hooks/useAudio';
import './Game.css';

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
  const currentTick = useGameStore((s) => s.currentTick);
  const connectionState = useGameStore((s) => s.connectionState);
  const countdown = useGameStore((s) => s.countdown);
  const captureCount = useGameStore((s) => s.captureCount);

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

  const doStartCountdown = useCallback(() => {
    useGameStore.getState().startCountdown();
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

  // Start countdown when connected and waiting (only once)
  // Also check currentTick === 0 to prevent countdown on rejoin of in-progress games
  const countdownStartedRef = useRef(false);
  useEffect(() => {
    if (
      connectionState === 'connected' &&
      status === 'waiting' &&
      currentTick === 0 &&
      !countdownStartedRef.current
    ) {
      countdownStartedRef.current = true;
      doStartCountdown();
    }
    // Reset if game finishes and we reconnect
    if (status === 'finished') {
      countdownStartedRef.current = false;
    }
  }, [connectionState, status, currentTick, doStartCountdown]);

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
        <div className="game-board-wrapper">
          <GameBoard boardType={boardType} squareSize={64} />
          {countdown !== null && (
            <div className="game-countdown-overlay">
              <div className="game-countdown-number">{countdown}</div>
            </div>
          )}
        </div>
        <div className="game-sidebar">
          <GameStatus />
          <AudioControls
            musicVolume={musicVolume}
            soundVolume={soundVolume}
            onMusicVolumeChange={setMusicVolume}
            onSoundVolumeChange={setSoundVolume}
          />
          <div className="game-instructions">
            <h3>How to Play</h3>
            <ul>
              <li>Click a piece to select it</li>
              <li>Green dots show legal moves</li>
              <li>Click a dot to move there</li>
              <li>Pieces have cooldowns after moving</li>
              <li>Capture the opponent's king to win!</li>
            </ul>
          </div>
        </div>
      </div>
      <GameOverModal />
    </div>
  );
}

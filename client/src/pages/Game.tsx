/**
 * Game Page
 *
 * Main game view that contains the board and game UI.
 */

import { useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useGameStore } from '../stores/game';
import { GameBoard, GameStatus, GameOverModal } from '../components/game';
import './Game.css';

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Track if effect is still active (handles React StrictMode double-mount)
  const isActiveRef = useRef(true);

  // Get player key from URL or local storage
  const playerKeyFromUrl = searchParams.get('playerKey');

  // Store state and actions
  const storeGameId = useGameStore((s) => s.gameId);
  const boardType = useGameStore((s) => s.boardType);
  const status = useGameStore((s) => s.status);
  const connectionState = useGameStore((s) => s.connectionState);
  const joinGame = useGameStore((s) => s.joinGame);
  const connect = useGameStore((s) => s.connect);
  const disconnect = useGameStore((s) => s.disconnect);

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
    joinGame(gameId, playerKey ?? undefined)
      .then(() => {
        // Only connect if still active (handles StrictMode double-mount)
        if (isActiveRef.current) {
          connect();
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
      disconnect();
    };
  }, [gameId, playerKeyFromUrl, joinGame, connect, disconnect, navigate]);

  // Handle unexpected disconnection (only reconnect if we were previously connected)
  const wasConnectedRef = useRef(false);

  useEffect(() => {
    // Track if we've ever been connected
    if (connectionState === 'connected') {
      wasConnectedRef.current = true;
    }

    // Only auto-reconnect if we were previously connected and got disconnected
    if (connectionState === 'disconnected' && wasConnectedRef.current && storeGameId && status !== 'finished') {
      connect();
    }
  }, [connectionState, storeGameId, status, connect]);

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
        </div>
        <div className="game-sidebar">
          <GameStatus />
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

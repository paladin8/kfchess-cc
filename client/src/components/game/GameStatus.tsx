/**
 * GameStatus Component
 *
 * Displays game info (ID, mode, players) and current connection state.
 */

import { useState, useCallback } from 'react';
import { useGameStore } from '../../stores/game';
import { useLobbyStore } from '../../stores/lobby';
import PlayerBadge from '../PlayerBadge';

export function GameStatus() {
  const [copied, setCopied] = useState(false);
  const gameId = useGameStore((s) => s.gameId);
  const speed = useGameStore((s) => s.speed);
  const players = useGameStore((s) => s.players);
  const status = useGameStore((s) => s.status);
  const connectionState = useGameStore((s) => s.connectionState);
  const playerNumber = useGameStore((s) => s.playerNumber);
  const lastError = useGameStore((s) => s.lastError);
  const campaignLevel = useGameStore((s) => s.campaignLevel);
  const isRanked = useLobbyStore((s) => s.lobby?.settings.isRanked ?? false);

  const getStatusText = () => {
    switch (status) {
      case 'waiting':
        return 'Waiting to start...';
      case 'playing':
        return 'Game in progress';
      case 'finished':
        return 'Game over';
      default:
        return 'Unknown';
    }
  };

  const getConnectionText = () => {
    switch (connectionState) {
      case 'disconnected':
        return 'Disconnected';
      case 'connecting':
        return 'Connecting...';
      case 'connected':
        return 'Connected';
      case 'reconnecting':
        return 'Reconnecting...';
      default:
        return 'Unknown';
    }
  };

  const getConnectionColor = () => {
    switch (connectionState) {
      case 'connected':
        return '#4ade80'; // green
      case 'connecting':
      case 'reconnecting':
        return '#fbbf24'; // yellow
      case 'disconnected':
        return '#f87171'; // red
      default:
        return '#9ca3af'; // gray
    }
  };

  const getPlayerLabel = () => {
    if (playerNumber === 0) return 'Spectator';
    const colors = ['', 'White', 'Black', 'Red', 'Blue'];
    return `Player ${playerNumber} (${colors[playerNumber] || 'Unknown'})`;
  };

  const copySpectatorLink = useCallback(() => {
    if (!gameId) return;
    const link = `${window.location.origin}/game/${gameId}`;
    navigator.clipboard.writeText(link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [gameId]);

  return (
    <>
      <div className="game-info">
        {campaignLevel && (
          <div className="campaign-level-info">
            <div className="campaign-level-title">{campaignLevel.title}</div>
            <div className="campaign-level-description">{campaignLevel.description}</div>
          </div>
        )}

        {gameId && (
          <div className="game-info-row">
            <span className="game-info-label">Spectate:</span>
            <button className="copy-link-button" onClick={copySpectatorLink}>
              {copied ? 'Copied!' : 'Copy Link'}
            </button>
          </div>
        )}

        <div className="game-info-row">
          <span className="game-info-label">Mode:</span>
          <span className="game-info-value">
            {campaignLevel
              ? `Campaign Level ${campaignLevel.level_id + 1}`
              : `${speed.charAt(0).toUpperCase() + speed.slice(1)}${isRanked ? ' (Rated)' : ''}`
            }
          </span>
        </div>

        {players && Object.entries(players).map(([playerNum, player]) => (
          <div key={playerNum} className="game-info-row">
            <span className="game-info-label">Player {playerNum}:</span>
            <span className="game-info-value game-info-player">
              <PlayerBadge
                userId={player.user_id}
                username={player.name}
                pictureUrl={player.picture_url}
                size="sm"
              />
            </span>
          </div>
        ))}
      </div>

      <div className="game-status">
        <div className="game-status-row">
          <span className="game-status-label">Status:</span>
          <span className="game-status-value">{getStatusText()}</span>
        </div>

        <div className="game-status-row">
          <span className="game-status-label">Connection:</span>
          <span className="game-status-value" style={{ color: getConnectionColor() }}>
            {getConnectionText()}
          </span>
        </div>

        <div className="game-status-row">
          <span className="game-status-label">You are:</span>
          <span className="game-status-value">{getPlayerLabel()}</span>
        </div>

        {lastError && (
          <div className="game-status-error">
            {lastError}
          </div>
        )}
      </div>
    </>
  );
}

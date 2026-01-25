/**
 * Lobby Page Component
 *
 * Displays the lobby waiting room where players can ready up and start games.
 * Handles both direct URL navigation and navigation from create/join flows.
 */

import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  useLobbyStore,
  selectIsHost,
  selectMyPlayer,
  selectCanStart,
  selectIsFull,
  getSavedLobbyCredentials,
} from '../stores/lobby';
import { useAuthStore } from '../stores/auth';
import type { LobbyPlayer, LobbySettings as LobbySettingsType } from '../api/types';
import './Lobby.css';

// ============================================
// Sub-components
// ============================================

interface PlayerSlotProps {
  slot: number;
  player: LobbyPlayer | undefined;
  isHost: boolean;
  isMe: boolean;
  canKick: boolean;
  onKick: (slot: number) => void;
}

function PlayerSlot({ slot, player, isHost, isMe, canKick, onKick }: PlayerSlotProps) {
  if (!player) {
    // Use same structure as filled slot to prevent size jumping
    return (
      <div className="player-slot empty">
        <div className="slot-header">
          <span className="slot-number">Slot {slot}</span>
          <span className="badge-placeholder">&nbsp;</span>
        </div>
        <div className="player-name slot-empty">Empty</div>
        <div className="player-status">&nbsp;</div>
      </div>
    );
  }

  // Disconnected players are shown differently
  const isDisconnected = !player.isAi && !player.isConnected;

  // Host is always considered ready (but not if disconnected)
  const isEffectivelyReady = !isDisconnected && (player.isReady || isHost);

  return (
    <div
      className={`player-slot ${isMe ? 'me' : ''} ${isEffectivelyReady ? 'ready' : ''} ${isDisconnected ? 'disconnected' : ''}`}
    >
      <div className="slot-header">
        <span className="slot-number">Slot {slot}</span>
        {isHost && <span className="host-badge">Host</span>}
        {player.isAi && <span className="ai-badge">AI</span>}
        {isDisconnected && <span className="disconnected-badge">Offline</span>}
      </div>
      <div className="player-name">{player.username}</div>
      <div className="player-status">
        {isDisconnected ? (
          <span className="status-disconnected">Disconnected</span>
        ) : isEffectivelyReady ? (
          <span className="status-ready">Ready</span>
        ) : (
          <span className="status-waiting">Not Ready</span>
        )}
      </div>
      {canKick && (
        <button className="btn btn-sm btn-link kick-btn" onClick={() => onKick(slot)}>
          Kick
        </button>
      )}
    </div>
  );
}

interface LobbySettingsProps {
  settings: LobbySettingsType;
  isHost: boolean;
  disabled: boolean;
  canEnableRated: boolean;
  onUpdate: (settings: Partial<LobbySettingsType>) => void;
}

function LobbySettings({ settings, isHost, disabled, canEnableRated, onUpdate }: LobbySettingsProps) {
  const canEdit = isHost && !disabled;

  return (
    <div className="lobby-settings">
      <h3>Game Settings</h3>
      <div className="settings-grid">
        <div className="setting-item">
          <label>Speed</label>
          <select
            value={settings.speed}
            onChange={(e) => onUpdate({ speed: e.target.value as 'standard' | 'lightning' })}
            disabled={!canEdit}
          >
            <option value="standard">Standard</option>
            <option value="lightning">Lightning</option>
          </select>
        </div>

        <div className="setting-item">
          <label>Players</label>
          <select
            value={settings.playerCount}
            onChange={(e) => onUpdate({ playerCount: Number(e.target.value) as 2 | 4 })}
            disabled={!canEdit}
          >
            <option value={2}>2 Players</option>
            <option value={4}>4 Players</option>
          </select>
        </div>

        <div className="setting-item">
          <label>Visibility</label>
          <select
            value={settings.isPublic ? 'public' : 'private'}
            onChange={(e) => onUpdate({ isPublic: e.target.value === 'public' })}
            disabled={!canEdit}
          >
            <option value="public">Public</option>
            <option value="private">Private</option>
          </select>
        </div>

        <div className="setting-item">
          <label>Rated</label>
          <select
            value={!canEnableRated ? 'no' : settings.isRanked ? 'yes' : 'no'}
            onChange={(e) => onUpdate({ isRanked: e.target.value === 'yes' })}
            disabled={!canEdit || !canEnableRated}
          >
            <option value="no">No</option>
            <option value="yes">Yes</option>
          </select>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Join Modal (for direct URL navigation)
// ============================================

interface JoinModalProps {
  code: string;
  onJoin: (username?: string) => void;
  onCancel: () => void;
  isJoining: boolean;
  error: string | null;
}

function JoinModal({ code, onJoin, onCancel, isJoining, error }: JoinModalProps) {
  const user = useAuthStore((s) => s.user);
  const [username, setUsername] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onJoin(user ? undefined : username || undefined);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>Join Lobby</h2>
        <p className="modal-subtitle">Lobby Code: {code}</p>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          {!user && (
            <div className="form-group">
              <label htmlFor="username">
                Display Name <span className="optional">(optional)</span>
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Guest"
                disabled={isJoining}
                maxLength={20}
              />
            </div>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={isJoining}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isJoining}>
              {isJoining ? 'Joining...' : 'Join Lobby'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================
// Main Lobby Page
// ============================================

export function Lobby() {
  const { code: urlCode } = useParams<{ code: string }>();
  const navigate = useNavigate();

  // Store state
  const code = useLobbyStore((s) => s.code);
  const playerKey = useLobbyStore((s) => s.playerKey);
  const mySlot = useLobbyStore((s) => s.mySlot);
  const lobby = useLobbyStore((s) => s.lobby);
  const connectionState = useLobbyStore((s) => s.connectionState);
  const error = useLobbyStore((s) => s.error);
  const pendingGameId = useLobbyStore((s) => s.pendingGameId);

  // Derived state
  const isHost = useLobbyStore(selectIsHost);
  const myPlayer = useLobbyStore(selectMyPlayer);
  const canStart = useLobbyStore(selectCanStart);
  const isFull = useLobbyStore(selectIsFull);

  // Actions
  const joinLobby = useLobbyStore((s) => s.joinLobby);
  const connect = useLobbyStore((s) => s.connect);
  const setReady = useLobbyStore((s) => s.setReady);
  const updateSettings = useLobbyStore((s) => s.updateSettings);
  const kickPlayer = useLobbyStore((s) => s.kickPlayer);
  const addAi = useLobbyStore((s) => s.addAi);
  const removeAi = useLobbyStore((s) => s.removeAi);
  const startGame = useLobbyStore((s) => s.startGame);
  const leaveLobby = useLobbyStore((s) => s.leaveLobby);
  const clearError = useLobbyStore((s) => s.clearError);

  // Local state
  const [showJoinModal, setShowJoinModal] = useState(false);
  const [isJoining, setIsJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);

  // Check if we need to join (direct URL navigation)
  useEffect(() => {
    if (!urlCode) return;

    // If we already have credentials for this lobby, connect
    if (code === urlCode && playerKey) {
      if (connectionState === 'disconnected') {
        connect(urlCode, playerKey);
      }
      return;
    }

    // Check if we have saved credentials for this lobby (page refresh)
    const savedCredentials = getSavedLobbyCredentials();
    if (savedCredentials && savedCredentials.code === urlCode) {
      // Restore credentials and reconnect
      useLobbyStore.setState({
        code: savedCredentials.code,
        playerKey: savedCredentials.playerKey,
        mySlot: savedCredentials.slot,
      });
      connect(savedCredentials.code, savedCredentials.playerKey);
      return;
    }

    // We're navigating directly to a lobby we're not in - show join modal
    if (code !== urlCode) {
      setShowJoinModal(true);
    }
  }, [urlCode, code, playerKey, connectionState, connect]);

  // Navigate to game when it starts
  useEffect(() => {
    if (pendingGameId && lobby?.status === 'in_game') {
      navigate(`/game/${pendingGameId}`);
    }
  }, [pendingGameId, lobby?.status, navigate]);

  // Cleanup on unmount (unless navigating to game)
  useEffect(() => {
    return () => {
      // Don't disconnect if we're going to a game
      const state = useLobbyStore.getState();
      if (!state.pendingGameId) {
        // Leave lobby if navigating away (not to game)
        state.leaveLobby();
      }
    };
  }, []);

  const handleJoin = useCallback(
    async (username?: string) => {
      if (!urlCode) return;

      setIsJoining(true);
      setJoinError(null);

      try {
        await joinLobby(urlCode, username);
        setShowJoinModal(false);

        // Connect WebSocket
        const state = useLobbyStore.getState();
        if (state.playerKey) {
          connect(urlCode, state.playerKey);
        }
      } catch (err) {
        setJoinError(err instanceof Error ? err.message : 'Failed to join lobby');
      } finally {
        setIsJoining(false);
      }
    },
    [urlCode, joinLobby, connect]
  );

  const handleCancelJoin = useCallback(() => {
    setShowJoinModal(false);
    navigate('/');
  }, [navigate]);

  const handleLeave = useCallback(() => {
    leaveLobby();
    navigate('/lobbies');
  }, [leaveLobby, navigate]);

  const handleKick = useCallback(
    (slot: number) => {
      const player = lobby?.players[slot];
      if (player?.isAi) {
        removeAi(slot);
      } else {
        kickPlayer(slot);
      }
    },
    [lobby?.players, kickPlayer, removeAi]
  );

  const handleCopyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = window.location.href;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    }
  }, []);

  // Show join modal for direct URL navigation
  if (showJoinModal && urlCode) {
    return (
      <JoinModal
        code={urlCode}
        onJoin={handleJoin}
        onCancel={handleCancelJoin}
        isJoining={isJoining}
        error={joinError}
      />
    );
  }

  // Loading state
  if (!lobby) {
    return (
      <div className="lobby-page">
        <div className="lobby-loading">
          {connectionState === 'connecting' && <p>Connecting to lobby...</p>}
          {connectionState === 'reconnecting' && <p>Reconnecting...</p>}
          {connectionState === 'disconnected' && error && (
            <div className="lobby-error">
              <p>{error}</p>
              <button className="btn btn-primary" onClick={() => navigate('/')}>
                Back to Home
              </button>
            </div>
          )}
          {connectionState === 'disconnected' && !error && <p>Loading...</p>}
        </div>
      </div>
    );
  }

  const playerSlots = Array.from({ length: lobby.settings.playerCount }, (_, i) => i + 1);
  const hasAiPlayers = Object.values(lobby.players).some((p) => p?.isAi);
  // Rated games require all players to be logged in (not AI and not guests)
  const hasGuestPlayers = Object.values(lobby.players).some((p) => p && !p.isAi && p.userId === null);
  const canEnableRated = !hasAiPlayers && !hasGuestPlayers;

  return (
    <div className="lobby-page">
      <header className="lobby-header">
        <div className="lobby-title">
          <h1>Lobby</h1>
          <span className="lobby-code">{lobby.code}</span>
          <button
            className="btn btn-sm btn-link copy-link-btn"
            onClick={handleCopyLink}
            title="Copy invite link"
          >
            {copyFeedback ? '✓' : '🔗'}
          </button>
        </div>
        <button className="btn btn-link" onClick={handleLeave}>
          Leave Lobby
        </button>
      </header>

      {error && (
        <div className="auth-error lobby-error-banner">
          {error}
          <button className="btn btn-link" onClick={clearError}>
            Dismiss
          </button>
        </div>
      )}

      <div className="lobby-content">
        <LobbySettings
          settings={lobby.settings}
          isHost={isHost}
          disabled={lobby.status !== 'waiting'}
          canEnableRated={canEnableRated}
          onUpdate={updateSettings}
        />

        <div className="player-slots">
          <div className="slots-header">
            <h3>Players</h3>
            {isHost && (
              <button
                className="btn btn-sm btn-secondary"
                onClick={() => addAi()}
                disabled={isFull}
              >
                Add AI
              </button>
            )}
          </div>
          <div className="slots-grid">
            {playerSlots.map((slot) => (
              <PlayerSlot
                key={slot}
                slot={slot}
                player={lobby.players[slot]}
                isHost={slot === lobby.hostSlot}
                isMe={slot === mySlot}
                canKick={isHost && slot !== mySlot && !!lobby.players[slot]}
                onKick={handleKick}
              />
            ))}
          </div>
        </div>

        <div className="lobby-actions">
          {/* Non-host players can toggle their ready status */}
          {myPlayer && !isHost && !myPlayer.isReady && (
            <button className="btn btn-primary" onClick={() => setReady(true)}>
              Ready
            </button>
          )}

          {myPlayer?.isReady && !isHost && (
            <button className="btn btn-secondary" onClick={() => setReady(false)}>
              Cancel Ready
            </button>
          )}

          {/* Host is always ready and just clicks Start Game */}
          {isHost && (
            <button className="btn btn-primary" onClick={startGame} disabled={!canStart}>
              Start Game
            </button>
          )}
        </div>

        {!lobby.settings.isPublic && (
          <div className="share-section">
            <p>Share this link to invite players:</p>
            <div className="share-link">
              <code>{window.location.href}</code>
              <button className="btn btn-sm btn-secondary" onClick={handleCopyLink}>
                {copyFeedback ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        )}
      </div>

      {connectionState === 'reconnecting' && (
        <div className="connection-banner reconnecting">Reconnecting...</div>
      )}
    </div>
  );
}

export default Lobby;

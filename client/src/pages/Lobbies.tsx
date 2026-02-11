/**
 * Lobbies Page Component
 *
 * Browse and join public lobbies, or join by code.
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLobbyStore } from '../stores/lobby';
import { useAuthStore } from '../stores/auth';
import { track } from '../analytics';
import type { LobbyListItem } from '../api/types';
import './Lobby.css';

// ============================================
// Join Modal
// ============================================

interface JoinModalProps {
  lobby: LobbyListItem;
  onJoin: () => void;
  onCancel: () => void;
  isJoining: boolean;
  error: string | null;
}

function JoinModal({ lobby, onJoin, onCancel, isJoining, error }: JoinModalProps) {
  const user = useAuthStore((s) => s.user);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onJoin();
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h2>Join Lobby</h2>
        <p className="modal-subtitle">
          {lobby.hostUsername}'s Lobby - {lobby.settings.speed}, {lobby.settings.playerCount} players
        </p>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          {!user && (
            <p className="guest-notice">You will join as Guest</p>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onCancel}
              disabled={isJoining}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isJoining}>
              {isJoining ? 'Joining...' : 'Join'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================
// Main Component
// ============================================

export function Lobbies() {
  const navigate = useNavigate();

  // Store state
  const publicLobbies = useLobbyStore((s) => s.publicLobbies);
  const isLoadingLobbies = useLobbyStore((s) => s.isLoadingLobbies);
  const fetchPublicLobbies = useLobbyStore((s) => s.fetchPublicLobbies);
  const joinLobby = useLobbyStore((s) => s.joinLobby);
  const connect = useLobbyStore((s) => s.connect);
  const createLobby = useLobbyStore((s) => s.createLobby);

  // Local state
  const [speedFilter, setSpeedFilter] = useState<string>('');
  const [playerCountFilter, setPlayerCountFilter] = useState<number | undefined>();
  const [ratedFilter, setRatedFilter] = useState<boolean | undefined>();
  const [joinCode, setJoinCode] = useState('');
  const [selectedLobby, setSelectedLobby] = useState<LobbyListItem | null>(null);
  const [isJoining, setIsJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Refresh cooldown state
  const [canRefresh, setCanRefresh] = useState(false);
  const lastRefreshRef = useRef<number>(0);

  useEffect(() => { track('Visit Lobbies Page'); }, []);

  // Fetch lobbies on mount and when filters change
  useEffect(() => {
    fetchPublicLobbies(speedFilter || undefined, playerCountFilter, ratedFilter);
    lastRefreshRef.current = Date.now();
    setCanRefresh(false);
  }, [fetchPublicLobbies, speedFilter, playerCountFilter, ratedFilter]);

  // Enable refresh button after 10 seconds
  useEffect(() => {
    const checkRefreshCooldown = () => {
      const elapsed = Date.now() - lastRefreshRef.current;
      if (elapsed >= 10000) {
        setCanRefresh(true);
      }
    };

    const interval = setInterval(checkRefreshCooldown, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = useCallback(() => {
    if (!canRefresh) return;
    fetchPublicLobbies(speedFilter || undefined, playerCountFilter, ratedFilter);
    lastRefreshRef.current = Date.now();
    setCanRefresh(false);
  }, [canRefresh, fetchPublicLobbies, speedFilter, playerCountFilter, ratedFilter]);

  const handleJoinLobby = useCallback(
    async () => {
      if (!selectedLobby) return;

      setIsJoining(true);
      setJoinError(null);

      try {
        await joinLobby(selectedLobby.code);
        track('Lobby Join', { code: selectedLobby.code, speed: selectedLobby.settings.speed, playerCount: selectedLobby.settings.playerCount });
        const state = useLobbyStore.getState();
        if (state.playerKey) {
          connect(selectedLobby.code, state.playerKey);
        }
        navigate(`/lobby/${selectedLobby.code}`);
      } catch (err) {
        setJoinError(err instanceof Error ? err.message : 'Failed to join lobby');
      } finally {
        setIsJoining(false);
      }
    },
    [selectedLobby, joinLobby, connect, navigate]
  );

  const handleJoinByCode = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const code = joinCode.trim().toUpperCase();
      if (!code) return;

      track('Lobby Join By Code', { code });
      // Navigate to lobby page which will handle joining
      navigate(`/lobby/${code}`);
    },
    [joinCode, navigate]
  );

  const handleCreateLobby = useCallback(async () => {
    track('Lobby Create', { source: 'lobbies_page' });
    setIsCreating(true);
    setCreateError(null);
    try {
      const code = await createLobby({ isPublic: false }, false);
      const state = useLobbyStore.getState();
      if (state.playerKey) {
        connect(code, state.playerKey);
      }
      navigate(`/lobby/${code}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create lobby');
    } finally {
      setIsCreating(false);
    }
  }, [createLobby, connect, navigate]);

  return (
    <div className="lobbies-page">
      <header className="lobbies-header">
        <h1>Browse Lobbies</h1>
        <button className="btn btn-primary" onClick={handleCreateLobby} disabled={isCreating}>
          {isCreating ? 'Creating...' : 'Create Lobby'}
        </button>
      </header>

      {createError && (
        <div className="auth-error lobby-error-banner">
          {createError}
          <button className="btn btn-link" onClick={() => setCreateError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="lobbies-filters">
        <button
          className="refresh-btn"
          onClick={handleRefresh}
          disabled={!canRefresh || isLoadingLobbies}
          title={canRefresh ? 'Refresh lobbies' : 'Wait 10 seconds to refresh'}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
            <path d="M8 16H3v5" />
          </svg>
        </button>

        <select value={speedFilter} onChange={(e) => setSpeedFilter(e.target.value)}>
          <option value="">All Speeds</option>
          <option value="standard">Standard</option>
          <option value="lightning">Lightning</option>
        </select>

        <select
          value={playerCountFilter || ''}
          onChange={(e) => setPlayerCountFilter(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All Player Counts</option>
          <option value="2">2 Players</option>
          <option value="4">4 Players</option>
        </select>

        <select
          value={ratedFilter === undefined ? '' : ratedFilter ? 'rated' : 'unrated'}
          onChange={(e) => {
            const val = e.target.value;
            setRatedFilter(val === '' ? undefined : val === 'rated');
          }}
        >
          <option value="">All Types</option>
          <option value="rated">Rated</option>
          <option value="unrated">Unrated</option>
        </select>
      </div>

      {isLoadingLobbies && publicLobbies.length === 0 ? (
        <div className="lobbies-loading">Loading lobbies...</div>
      ) : publicLobbies.length === 0 ? (
        <div className="lobbies-empty">
          <p>No public lobbies available.</p>
          <p>Create one or join by code!</p>
        </div>
      ) : (
        <div className="lobbies-list">
          {publicLobbies.map((lobby) => (
            <div key={lobby.id} className="lobby-card">
              <div className="lobby-card-info">
                <div className="lobby-card-host">{lobby.hostUsername}'s Lobby</div>
                <div className="lobby-card-details">
                  <span>{lobby.settings.speed}</span>
                  <span>{lobby.settings.playerCount} players</span>
                  {lobby.settings.isRanked && <span>Ranked</span>}
                </div>
              </div>
              <div className="lobby-card-players">
                {lobby.currentPlayers}/{lobby.playerCount}
              </div>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setSelectedLobby(lobby)}
                disabled={lobby.currentPlayers >= lobby.playerCount}
              >
                {lobby.currentPlayers >= lobby.playerCount ? 'Full' : 'Join'}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="join-code-section">
        <h3>Join by Code</h3>
        <form className="join-code-form" onSubmit={handleJoinByCode}>
          <input
            type="text"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            placeholder="Enter lobby code"
            maxLength={6}
          />
          <button type="submit" className="btn btn-secondary" disabled={!joinCode.trim()}>
            Join
          </button>
        </form>
      </div>

      {selectedLobby && (
        <JoinModal
          lobby={selectedLobby}
          onJoin={handleJoinLobby}
          onCancel={() => {
            setSelectedLobby(null);
            setJoinError(null);
          }}
          isJoining={isJoining}
          error={joinError}
        />
      )}
    </div>
  );
}

export default Lobbies;

/**
 * Watch Page
 *
 * Unified page with tabs for Live Games, Replays, and Leaderboard.
 */

import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useLobbyStore } from '../stores/lobby';
import { listReplays } from '../api/client';
import type { LobbyListItem, ApiReplaySummary } from '../api/types';
import { formatDate, formatDuration, formatWinReason } from '../utils/format';
import { Leaderboard } from '../components/Leaderboard';
import './Watch.css';

type TabId = 'live' | 'replays' | 'leaderboard';

// ============================================
// Live Games Tab Content
// ============================================

function LiveGamesTab() {
  const publicLobbies = useLobbyStore((s) => s.publicLobbies);
  const isLoadingLobbies = useLobbyStore((s) => s.isLoadingLobbies);
  const fetchPublicLobbies = useLobbyStore((s) => s.fetchPublicLobbies);

  useEffect(() => {
    fetchPublicLobbies();
  }, [fetchPublicLobbies]);

  // Refresh lobbies periodically
  useEffect(() => {
    const interval = setInterval(() => {
      fetchPublicLobbies();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchPublicLobbies]);

  // Filter to show only lobbies that are in-game (active games to watch)
  const activeGames = publicLobbies.filter((lobby) => lobby.status === 'in_game');
  const waitingLobbies = publicLobbies.filter((lobby) => lobby.status === 'waiting');

  if (isLoadingLobbies && publicLobbies.length === 0) {
    return <div className="tab-loading">Loading live games...</div>;
  }

  return (
    <div className="live-games-content">
      {activeGames.length > 0 && (
        <section className="games-section">
          <h3>Active Games</h3>
          <div className="games-list">
            {activeGames.map((lobby) => (
              <LiveGameCard key={lobby.id} lobby={lobby} isActive />
            ))}
          </div>
        </section>
      )}

      {waitingLobbies.length > 0 && (
        <section className="games-section">
          <h3>Waiting for Players</h3>
          <div className="games-list">
            {waitingLobbies.map((lobby) => (
              <LiveGameCard key={lobby.id} lobby={lobby} />
            ))}
          </div>
        </section>
      )}

      {publicLobbies.length === 0 && (
        <div className="tab-empty">
          <p>No live games right now.</p>
          <p>Create a lobby to start playing!</p>
          <Link to="/lobbies" className="btn btn-primary">
            Browse Lobbies
          </Link>
        </div>
      )}
    </div>
  );
}

interface LiveGameCardProps {
  lobby: LobbyListItem;
  isActive?: boolean;
}

function LiveGameCard({ lobby, isActive }: LiveGameCardProps) {
  return (
    <Link
      to={isActive && lobby.status === 'in_game' ? `/game/${lobby.code}` : `/lobby/${lobby.code}`}
      className={`game-card ${isActive ? 'active' : ''}`}
    >
      <div className="game-card-info">
        <div className="game-card-host">{lobby.hostUsername}'s Game</div>
        <div className="game-card-details">
          <span className="detail-badge">{lobby.settings.speed}</span>
          <span>{lobby.settings.playerCount}P</span>
          {lobby.settings.isRanked && <span className="ranked-badge">Ranked</span>}
        </div>
      </div>
      <div className="game-card-status">
        {isActive ? (
          <span className="status-live">Live</span>
        ) : (
          <span className="status-waiting">
            {lobby.currentPlayers}/{lobby.playerCount}
          </span>
        )}
      </div>
    </Link>
  );
}

// ============================================
// Replays Tab Content
// ============================================

function ReplaysTab() {
  const [replays, setReplays] = useState<ApiReplaySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchReplays = useCallback(async () => {
    try {
      setLoading(true);
      const response = await listReplays(20);
      setReplays(response.replays);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load replays');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReplays();
  }, [fetchReplays]);

  if (loading) {
    return <div className="tab-loading">Loading replays...</div>;
  }

  if (error) {
    return (
      <div className="tab-error">
        <p>{error}</p>
        <button className="btn btn-primary" onClick={fetchReplays}>
          Retry
        </button>
      </div>
    );
  }

  if (replays.length === 0) {
    return (
      <div className="tab-empty">
        <p>No replays available yet.</p>
        <p>Play a game to create your first replay!</p>
        <Link to="/" className="btn btn-primary">
          Play Now
        </Link>
      </div>
    );
  }

  return (
    <div className="replays-content">
      {replays.map((replay) => (
        <Link key={replay.game_id} to={`/replay/${replay.game_id}`} className="replay-card">
          <div className="replay-card-header">
            <span className="replay-card-date">{formatDate(replay.created_at)}</span>
            <span className="replay-card-speed">{replay.speed}</span>
          </div>

          <div className="replay-card-players">
            {Object.entries(replay.players).map(([num, name]) => (
              <span
                key={num}
                className={`replay-card-player ${replay.winner === parseInt(num) ? 'winner' : ''}`}
              >
                {name || `Player ${num}`}
                {replay.winner === parseInt(num) && ' (W)'}
              </span>
            ))}
          </div>

          <div className="replay-card-footer">
            <span className="replay-card-duration">{formatDuration(replay.total_ticks)}</span>
            {replay.win_reason && (
              <span className="replay-card-result">{formatWinReason(replay.win_reason)}</span>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}

// ============================================
// Main Watch Page
// ============================================

export function Watch() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get('tab') as TabId) || 'live';
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);

  const handleTabChange = (tab: TabId) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  return (
    <div className="watch-page">
      <h1>Watch</h1>

      <div className="watch-tabs">
        <button
          className={`tab-button ${activeTab === 'live' ? 'active' : ''}`}
          onClick={() => handleTabChange('live')}
        >
          Live Games
        </button>
        <button
          className={`tab-button ${activeTab === 'replays' ? 'active' : ''}`}
          onClick={() => handleTabChange('replays')}
        >
          Replays
        </button>
        <button
          className={`tab-button ${activeTab === 'leaderboard' ? 'active' : ''}`}
          onClick={() => handleTabChange('leaderboard')}
        >
          Leaderboard
        </button>
      </div>

      <div className="watch-content">
        {activeTab === 'live' && <LiveGamesTab />}
        {activeTab === 'replays' && <ReplaysTab />}
        {activeTab === 'leaderboard' && <Leaderboard />}
      </div>
    </div>
  );
}

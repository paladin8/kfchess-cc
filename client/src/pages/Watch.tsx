/**
 * Watch Page
 *
 * Unified page with tabs for Live Games, Recent Replays, Top Replays, and Leaderboard.
 */

import { useState, useEffect, useCallback, useRef, useImperativeHandle, forwardRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { fetchLiveGames, listReplays } from '../api/client';
import type { LiveGameItem, ApiReplaySummary } from '../api/types';
import { Leaderboard } from '../components/Leaderboard';
import { track } from '../analytics';
import PlayerBadge from '../components/PlayerBadge';
import ReplayCard from '../components/ReplayCard';
import './Watch.css';

type TabId = 'live' | 'recent' | 'top' | 'leaderboard';

// ============================================
// Live Games Tab Content
// ============================================

interface LiveGamesTabHandle {
  refresh: () => void;
}

interface LiveGamesTabProps {
  onCanRefreshChange?: (canRefresh: boolean) => void;
}

const LiveGamesTab = forwardRef<LiveGamesTabHandle, LiveGamesTabProps>(function LiveGamesTab({ onCanRefreshChange }, ref) {
  const [games, setGames] = useState<LiveGameItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [canRefresh, setCanRefresh] = useState(false);
  const lastRefreshRef = useRef<number>(0);

  const loadGames = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetchLiveGames();
      setGames(response.games);
    } catch (err) {
      console.error('Failed to fetch live games:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGames();
    lastRefreshRef.current = Date.now();
    setCanRefresh(false);
  }, [loadGames]);

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
    if (!canRefresh || loading) return;
    loadGames();
    lastRefreshRef.current = Date.now();
    setCanRefresh(false);
  }, [canRefresh, loading, loadGames]);

  useImperativeHandle(ref, () => ({
    refresh: handleRefresh,
  }), [handleRefresh]);

  useEffect(() => {
    onCanRefreshChange?.(canRefresh && !loading);
  }, [canRefresh, loading, onCanRefreshChange]);

  if (loading && games.length === 0) {
    return <div className="tab-loading">Loading live games...</div>;
  }

  return (
    <div className="live-games-content">
      {games.length > 0 ? (
        <div className="match-history-list">
          {games.map((game) => (
            <LiveGameCard key={game.game_id} game={game} />
          ))}
        </div>
      ) : (
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
});

function formatElapsed(startedAt: string | null): string {
  if (!startedAt) return '';
  const normalized = startedAt.endsWith('Z') || startedAt.includes('+') || startedAt.includes('-', 10)
    ? startedAt
    : startedAt + 'Z';
  const seconds = Math.floor((Date.now() - new Date(normalized).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function LiveGameCard({ game }: { game: LiveGameItem }) {
  let modeLabel: string;
  if (game.campaign_level_id !== null && game.campaign_level_id !== undefined) {
    modeLabel = `Campaign Level ${game.campaign_level_id + 1}`;
  } else if (game.settings.playerCount > 2) {
    modeLabel = `${game.settings.speed} (${game.settings.playerCount}p)`;
  } else {
    modeLabel = game.settings.speed;
  }

  return (
    <Link to={`/game/${game.game_id}`} className="match-history-item" onClick={() => track('Click Spectate Game', { source: 'watch_live', gameId: game.game_id })}>
      <div className="match-info">
        <span className="match-date">{formatElapsed(game.started_at)}</span>
        <span className="match-speed">{modeLabel}</span>
      </div>
      <div className="match-result">
        <div className="match-players">
          {game.players.map((p) => (
            <span key={p.slot} className="match-player">
              <PlayerBadge
                userId={p.user_id}
                username={p.username}
                pictureUrl={p.picture_url}
                size="sm"
                linkToProfile={false}
              />
            </span>
          ))}
        </div>
        <span className="spectate-badge">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          Spectate
        </span>
      </div>
    </Link>
  );
}

// ============================================
// Replays Tab Content
// ============================================

interface ReplaysTabProps {
  sort: 'recent' | 'top';
}

function ReplaysTab({ sort }: ReplaysTabProps) {
  const [replays, setReplays] = useState<ApiReplaySummary[]>([]);
  const [replaysTotal, setReplaysTotal] = useState(0);
  const [replaysPage, setReplaysPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pageSize = 10;
  const maxPages = 10; // Cap at 100 replays total
  const totalPages = Math.min(Math.ceil(replaysTotal / pageSize), maxPages);

  const fetchReplays = useCallback(async () => {
    try {
      setLoading(true);
      const response = await listReplays(pageSize, replaysPage * pageSize, sort);
      setReplays(response.replays);
      setReplaysTotal(response.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load replays');
    } finally {
      setLoading(false);
    }
  }, [replaysPage, sort]);

  // Reset page when sort changes
  useEffect(() => {
    setReplaysPage(0);
  }, [sort]);

  useEffect(() => {
    fetchReplays();
  }, [fetchReplays]);

  if (loading && replays.length === 0) {
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
        {sort === 'top' ? (
          <>
            <p>No liked replays yet.</p>
            <p>Watch a replay and like it to see it here!</p>
          </>
        ) : (
          <>
            <p>No replays available yet.</p>
            <p>Play a game to create your first replay!</p>
          </>
        )}
        <Link to="/" className="btn btn-primary">
          Play Now
        </Link>
      </div>
    );
  }

  return (
    <div className="profile-match-history">
      <div className="match-history-list">
        {replays.map((replay) => (
          <ReplayCard
            key={replay.game_id}
            replay={replay}
          />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="match-history-pagination">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setReplaysPage((p) => Math.max(0, p - 1))}
            disabled={replaysPage === 0 || loading}
          >
            Previous
          </button>
          <span className="page-info">
            Page {replaysPage + 1} of {totalPages}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setReplaysPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={replaysPage >= totalPages - 1 || loading}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================
// Main Watch Page
// ============================================

export function Watch() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  // Handle legacy 'replays' tab by redirecting to 'recent'
  const initialTab: TabId = tabParam === 'replays' ? 'recent' : (tabParam as TabId) || 'live';
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const liveGamesRef = useRef<LiveGamesTabHandle>(null);
  const [liveCanRefresh, setLiveCanRefresh] = useState(false);

  useEffect(() => { track('Visit Live Page'); }, []);

  const handleTabChange = (tab: TabId) => {
    track('Watch Tab Change', { tab });
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  const handleLiveTabClick = () => {
    if (activeTab === 'live') {
      // Already on live tab — trigger refresh
      liveGamesRef.current?.refresh();
    } else {
      handleTabChange('live');
    }
  };

  return (
    <div className="watch-page">
      <div className="watch-tabs">
        <button
          className={`tab-button ${activeTab === 'live' ? 'active' : ''}`}
          onClick={handleLiveTabClick}
        >
          Live Games
          {activeTab === 'live' && (
            <svg
              className={`tab-refresh-icon ${liveCanRefresh ? '' : 'disabled'}`}
              width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 16H3v5" />
            </svg>
          )}
        </button>
        <button
          className={`tab-button ${activeTab === 'recent' ? 'active' : ''}`}
          onClick={() => handleTabChange('recent')}
        >
          Recent Replays
        </button>
        <button
          className={`tab-button ${activeTab === 'top' ? 'active' : ''}`}
          onClick={() => handleTabChange('top')}
        >
          Top Replays
        </button>
        <button
          className={`tab-button ${activeTab === 'leaderboard' ? 'active' : ''}`}
          onClick={() => handleTabChange('leaderboard')}
        >
          Leaderboard
        </button>
      </div>

      <div className="watch-content">
        {activeTab === 'live' && <LiveGamesTab ref={liveGamesRef} onCanRefreshChange={setLiveCanRefresh} />}
        {activeTab === 'recent' && <ReplaysTab sort="recent" />}
        {activeTab === 'top' && <ReplaysTab sort="top" />}
        {activeTab === 'leaderboard' && <Leaderboard />}
      </div>
    </div>
  );
}

/**
 * Leaderboard Component
 *
 * Displays player rankings for a selected rating mode.
 */

import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getLeaderboard, getMyRank } from '../api/client';
import type { LeaderboardEntry, MyRankResponse } from '../api/types';
import { useAuthStore } from '../stores/auth';
import { RATING_MODES, formatModeName, getBeltIconUrl, type RatingMode } from '../utils/ratings';
import './Leaderboard.css';

interface LeaderboardProps {
  initialMode?: RatingMode;
}

export function Leaderboard({ initialMode = '2p_standard' }: LeaderboardProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

  const [mode, setMode] = useState<RatingMode>(initialMode);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [myRank, setMyRank] = useState<MyRankResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const fetchLeaderboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [leaderboardData, myRankData] = await Promise.all([
        getLeaderboard(mode, pageSize, page * pageSize),
        isAuthenticated ? getMyRank(mode).catch(() => null) : Promise.resolve(null),
      ]);
      setEntries(leaderboardData.entries);
      setTotalCount(leaderboardData.total_count);
      setMyRank(myRankData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load leaderboard');
    } finally {
      setLoading(false);
    }
  }, [mode, page, isAuthenticated]);

  useEffect(() => {
    fetchLeaderboard();
  }, [fetchLeaderboard]);

  // Reset to page 0 when mode changes
  useEffect(() => {
    setPage(0);
  }, [mode]);

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="leaderboard">
      <div className="leaderboard-header">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as RatingMode)}
          className="mode-selector"
        >
          {RATING_MODES.map((m) => (
            <option key={m} value={m}>
              {formatModeName(m)}
            </option>
          ))}
        </select>
      </div>

      {/* User's own rank card */}
      {isAuthenticated && myRank && (
        <div className="my-rank-card">
          <div className="my-rank-header">Your Ranking</div>
          <div className="my-rank-content">
            <img
              src={getBeltIconUrl(myRank.belt)}
              alt={myRank.belt}
              className="my-rank-belt"
            />
            <div className="my-rank-info">
              <div className="my-rank-rating">{myRank.rating}</div>
              {myRank.rank !== null ? (
                <>
                  <div className="my-rank-position">Rank #{myRank.rank}</div>
                  <div className="my-rank-percentile">
                    Top {myRank.percentile !== null ? `${myRank.percentile}%` : 'N/A'}
                  </div>
                </>
              ) : (
                <div className="my-rank-unranked">Play a ranked game to get ranked!</div>
              )}
            </div>
            <div className="my-rank-stats">
              <div>{myRank.games_played} games</div>
              <div>{myRank.wins} wins</div>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="leaderboard-loading">Loading leaderboard...</div>
      ) : error ? (
        <div className="leaderboard-error">
          <p>{error}</p>
          <button className="btn btn-primary" onClick={fetchLeaderboard}>
            Retry
          </button>
        </div>
      ) : entries.length === 0 ? (
        <div className="leaderboard-empty">
          <p>No ranked players yet for {formatModeName(mode)}.</p>
          <p>Be the first to play a ranked game!</p>
          <Link to="/lobbies" className="btn btn-primary">
            Find a Game
          </Link>
        </div>
      ) : (
        <>
          <table className="leaderboard-table">
            <thead>
              <tr>
                <th className="col-rank">#</th>
                <th className="col-belt"></th>
                <th className="col-player">Player</th>
                <th className="col-rating">Rating</th>
                <th className="col-record">W-L</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr
                  key={entry.user_id}
                  className={user?.id === entry.user_id ? 'highlight-row' : ''}
                >
                  <td className="col-rank">{entry.rank}</td>
                  <td className="col-belt">
                    <img
                      src={getBeltIconUrl(entry.belt)}
                      alt={entry.belt}
                      className="belt-icon"
                    />
                  </td>
                  <td className="col-player">{entry.username}</td>
                  <td className="col-rating">{entry.rating}</td>
                  <td className="col-record">
                    {entry.wins}-{entry.games_played - entry.wins}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="leaderboard-pagination">
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                Previous
              </button>
              <span className="page-info">
                Page {page + 1} of {totalPages}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

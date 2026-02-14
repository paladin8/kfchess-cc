import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useAuthStore, UserRatingStats } from '../stores/auth';
import { BELT_NAMES, BELT_COLORS } from '../stores/campaign';
import * as api from '../api/client';
import {
  RATING_MODES,
  formatModeName,
  getBelt,
  DEFAULT_RATING,
} from '../utils/ratings';
import BeltIcon from '../components/BeltIcon';
import ReplayCard from '../components/ReplayCard';
import { track } from '../analytics';
import { staticUrl } from '../config';
import type { ApiRatingStats, ApiPublicUser, ApiReplaySummary, CampaignProgress } from '../api/types';

/**
 * User Profile page
 *
 * Displays user profile information and match history.
 * Supports viewing own profile (with edit) or other users' profiles (read-only).
 */
function Profile() {
  const navigate = useNavigate();
  const { userId } = useParams<{ userId?: string }>();
  const { user: currentUser, isLoading: isAuthLoading, setUser } = useAuthStore();

  // Determine if viewing own profile
  const targetUserId = userId ? parseInt(userId) : currentUser?.id;
  const isOwnProfile = !userId || (currentUser && currentUser.id === parseInt(userId));

  // State for public profile data (when viewing others)
  const [publicUser, setPublicUser] = useState<ApiPublicUser | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(!isOwnProfile);
  const [profileError, setProfileError] = useState<string | null>(null);

  // State for match history
  const [replays, setReplays] = useState<ApiReplaySummary[]>([]);
  const [replaysTotal, setReplaysTotal] = useState(0);
  const [replaysPage, setReplaysPage] = useState(0);
  const [isLoadingReplays, setIsLoadingReplays] = useState(false);
  const pageSize = 10;
  const totalPages = Math.ceil(replaysTotal / pageSize);

  // State for editing (only for own profile)
  const [username, setUsername] = useState(currentUser?.username || '');
  const [isEditing, setIsEditing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingPicture, setIsUploadingPicture] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Campaign progress (only for own profile)
  const [campaignProgress, setCampaignProgress] = useState<CampaignProgress | null>(null);

  // Redirect to login if viewing own profile without auth (wait for auth check to finish)
  useEffect(() => {
    if (!isAuthLoading && isOwnProfile && !currentUser) {
      navigate('/login', { replace: true });
    }
  }, [isAuthLoading, isOwnProfile, currentUser, navigate]);

  // Track profile visit
  useEffect(() => {
    if (targetUserId) {
      track('Visit Profile Page', { userId: targetUserId, isSelf: !!isOwnProfile });
    }
  }, [targetUserId, isOwnProfile]);

  // Reset form when user changes
  useEffect(() => {
    if (currentUser) {
      setUsername(currentUser.username);
    }
  }, [currentUser]);

  // Fetch public profile if viewing another user
  useEffect(() => {
    if (!isOwnProfile && targetUserId) {
      setIsLoadingProfile(true);
      setProfileError(null);

      api.getPublicUser(targetUserId)
        .then((userData) => {
          setPublicUser(userData);
        })
        .catch((err) => {
          if (err instanceof api.ApiClientError && err.status === 404) {
            setProfileError('User not found');
          } else {
            setProfileError('Failed to load profile');
          }
        })
        .finally(() => setIsLoadingProfile(false));
    }
  }, [isOwnProfile, targetUserId]);

  // Fetch replays for the user
  const fetchReplays = useCallback(async () => {
    if (!targetUserId) return;

    setIsLoadingReplays(true);
    try {
      const response = await api.getUserReplays(
        targetUserId,
        pageSize,
        replaysPage * pageSize
      );
      setReplays(response.replays);
      setReplaysTotal(response.total);
    } catch {
      // Silently fail - replays are not critical
    } finally {
      setIsLoadingReplays(false);
    }
  }, [targetUserId, replaysPage]);

  useEffect(() => {
    fetchReplays();
  }, [fetchReplays]);

  // Fetch campaign progress for any user
  useEffect(() => {
    if (targetUserId) {
      const fetchProgress = isOwnProfile
        ? api.getCampaignProgress()
        : api.getUserCampaignProgress(targetUserId);

      fetchProgress
        .then(setCampaignProgress)
        .catch(() => {
          // Silently fail - campaign progress is not critical
        });
    }
  }, [isOwnProfile, targetUserId]);

  const handlePictureUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploadingPicture(true);
    setError(null);
    setSuccess(null);

    try {
      const updatedUser = await api.uploadProfilePicture(file);

      const ratings: Record<string, UserRatingStats> = {};
      for (const [mode, value] of Object.entries(updatedUser.ratings)) {
        if (typeof value === 'number') {
          ratings[mode] = { rating: value, games: 0, wins: 0 };
        } else {
          const stats = value as ApiRatingStats;
          ratings[mode] = { rating: stats.rating, games: stats.games, wins: stats.wins };
        }
      }

      setUser({
        id: updatedUser.id,
        username: updatedUser.username,
        email: updatedUser.email,
        pictureUrl: updatedUser.picture_url,
        ratings,
        isVerified: updatedUser.is_verified,
      });
      track('Upload Profile Pic');
      setSuccess('Profile picture updated!');
    } catch (err) {
      if (err instanceof api.ApiClientError && err.detail) {
        setError(err.detail);
      } else {
        setError('Failed to upload picture. Max size is 1MB.');
      }
    } finally {
      setIsUploadingPicture(false);
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const trimmedUsername = username.trim();

    // Validate username
    if (trimmedUsername.length < 2) {
      setError('Username must be at least 2 characters');
      return;
    }

    if (trimmedUsername.length > 32) {
      setError('Username must be at most 32 characters');
      return;
    }

    // No change
    if (trimmedUsername === currentUser?.username) {
      setIsEditing(false);
      return;
    }

    if (isSubmitting) return;
    setIsSubmitting(true);

    try {
      const updatedUser = await api.updateUser({ username: trimmedUsername });

      // Convert ratings to the proper format
      const ratings: Record<string, UserRatingStats> = {};
      for (const [mode, value] of Object.entries(updatedUser.ratings)) {
        if (typeof value === 'number') {
          ratings[mode] = { rating: value, games: 0, wins: 0 };
        } else {
          const stats = value as ApiRatingStats;
          ratings[mode] = { rating: stats.rating, games: stats.games, wins: stats.wins };
        }
      }

      // Update the store with the new user data
      setUser({
        id: updatedUser.id,
        username: updatedUser.username,
        email: updatedUser.email,
        pictureUrl: updatedUser.picture_url,
        ratings,
        isVerified: updatedUser.is_verified,
      });
      track('Update User', { username: updatedUser.username });
      setIsEditing(false);
      setSuccess('Username updated successfully!');
    } catch (err) {
      if (err instanceof api.ApiClientError && err.detail) {
        if (err.detail.toLowerCase().includes('username')) {
          setError('This username is already taken. Please choose another.');
        } else {
          setError(err.detail);
        }
      } else {
        setError('Failed to update username. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setUsername(currentUser?.username || '');
    setIsEditing(false);
    setError(null);
  };

  // Loading state for public profiles
  if (isLoadingProfile) {
    return (
      <div className="auth-page">
        <div className="auth-card profile-card">
          <div className="profile-loading">Loading profile...</div>
        </div>
      </div>
    );
  }

  // Error state for public profiles
  if (profileError) {
    return (
      <div className="auth-page">
        <div className="auth-card profile-card">
          <div className="profile-error">
            <p>{profileError}</p>
            <Link to="/" className="btn btn-primary">Go Home</Link>
          </div>
        </div>
      </div>
    );
  }

  // Determine which user data to display
  const displayUser = isOwnProfile ? currentUser : publicUser;

  if (!displayUser) {
    return null;
  }

  // Get ratings based on which user we're viewing
  const displayRatings = isOwnProfile
    ? currentUser?.ratings
    : publicUser?.ratings;

  // Normalize ratings format
  const getRatingStats = (mode: string): UserRatingStats => {
    const value = displayRatings?.[mode];
    if (!value) {
      return { rating: DEFAULT_RATING, games: 0, wins: 0 };
    }
    if (typeof value === 'number') {
      return { rating: value, games: 0, wins: 0 };
    }
    return { rating: value.rating, games: value.games, wins: value.wins };
  };

  return (
    <div className="auth-page profile-page">
      <div className="auth-card profile-card">
        {error && <div className="auth-error" role="alert">{error}</div>}
        {success && <div className="auth-success" role="status">{success}</div>}

        <h1 className="profile-title">{isOwnProfile ? 'My Profile' : displayUser.username}</h1>

        {isOwnProfile && currentUser ? (
          <div className="profile-header-row">
            <div className="profile-header-info">
              {currentUser.email && (
                <div className="profile-field">
                  <label>Email</label>
                  <div className="profile-value">{currentUser.email}</div>
                </div>
              )}
              <div className="profile-field">
                <label htmlFor="username">Username</label>
                {isEditing ? (
                  <form onSubmit={handleSubmit} className="profile-edit-form">
                    <input
                      type="text"
                      id="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      required
                      minLength={2}
                      maxLength={32}
                      autoComplete="username"
                      disabled={isSubmitting}
                      autoFocus
                    />
                    <div className="profile-edit-actions">
                      <button
                        type="submit"
                        className="btn btn-primary btn-sm"
                        disabled={isSubmitting}
                      >
                        {isSubmitting ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={handleCancel}
                        disabled={isSubmitting}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <div className="profile-value-row">
                    <span className="profile-value">{displayUser.username}</span>
                    <button
                      type="button"
                      className="btn btn-link btn-sm"
                      onClick={() => { track('Click Edit Username'); setIsEditing(true); }}
                    >
                      Edit
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="profile-avatar-wrapper">
              <img
                className="profile-avatar-lg profile-avatar-clickable"
                src={currentUser.pictureUrl || staticUrl('default-profile.jpg')}
                alt={currentUser.username}
                width={100}
                height={100}
                onClick={!isUploadingPicture ? () => { track('Click Edit Profile Pic'); fileInputRef.current?.click(); } : undefined}
              />
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                onChange={handlePictureUpload}
                className="profile-avatar-input"
              />
            </div>
          </div>
        ) : (
          <div className="profile-avatar-center">
            <img
              className="profile-avatar-lg"
              src={publicUser?.picture_url || staticUrl('default-profile.jpg')}
              alt={displayUser.username}
              width={100}
              height={100}
            />
          </div>
        )}

        <div className="profile-section">

          {/* Campaign Progress */}
          {campaignProgress && (
            <div className="profile-field">
              <label>Campaign</label>
              <div className="profile-campaign-belts">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((belt) => {
                  const beltStart = (belt - 1) * 8;
                  const completedInBelt = Object.keys(campaignProgress.levelsCompleted)
                    .filter((id) => {
                      const levelId = parseInt(id);
                      return levelId >= beltStart && levelId < beltStart + 8;
                    }).length;
                  const isEmpty = completedInBelt === 0;
                  return (
                    <div
                      key={belt}
                      className={`campaign-belt-box ${isEmpty ? 'empty' : ''}`}
                      title={`${BELT_NAMES[belt]} Belt`}
                    >
                      <div
                        className="belt-color"
                        style={{
                          backgroundColor: BELT_COLORS[belt],
                          border: belt === 1 || belt === 9 ? '1px solid #666' : 'none',
                        }}
                      />
                      {completedInBelt}/8
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Ratings */}
          <div className="profile-field">
            <label>Ratings</label>
            <div className="profile-ratings">
              {RATING_MODES.map((mode) => {
                const stats = getRatingStats(mode);
                const belt = getBelt(stats.rating);
                return (
                  <div key={mode} className="profile-rating-card">
                    <div className="rating-header">
                      <BeltIcon belt={belt} size="lg" />
                      <div className="rating-mode">{formatModeName(mode)}</div>
                    </div>
                    <div className="rating-details">
                      <div className="rating-value">{stats.rating}</div>
                      <div className="rating-stats">
                        {stats.games > 0
                          ? `${stats.wins}W / ${stats.games - stats.wins}L`
                          : 'No games'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

        </div>
      </div>

      <div className="auth-card profile-card">
        <h2 className="profile-title">Match History</h2>
        <div className="profile-match-history">
          {isLoadingReplays && replays.length === 0 ? (
            <div className="match-history-loading">Loading matches...</div>
          ) : replays.length === 0 ? (
            <div className="match-history-empty">No matches played yet</div>
          ) : (
            <>
              <div className="match-history-list">
                {replays.map((replay) => (
                  <ReplayCard key={replay.game_id} replay={replay} />
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="match-history-pagination">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setReplaysPage((p) => Math.max(0, p - 1))}
                    disabled={replaysPage === 0 || isLoadingReplays}
                  >
                    Previous
                  </button>
                  <span className="page-info">
                    Page {replaysPage + 1} of {totalPages}
                  </span>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setReplaysPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={replaysPage >= totalPages - 1 || isLoadingReplays}
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default Profile;

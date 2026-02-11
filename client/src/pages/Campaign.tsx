/**
 * Campaign Page - Single-player campaign mode
 *
 * Displays belts and levels, allowing users to select and play campaign missions.
 */

import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/auth';
import { useCampaignStore, getLevelsForBelt } from '../stores/campaign';
import { BeltSelector, LevelGrid } from '../components/campaign';
import { track } from '../analytics';
import './Campaign.css';

function Campaign() {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();

  const progress = useCampaignStore((s) => s.progress);
  const levels = useCampaignStore((s) => s.levels);
  const selectedBelt = useCampaignStore((s) => s.selectedBelt);
  const isLoading = useCampaignStore((s) => s.isLoading);
  const isStartingLevel = useCampaignStore((s) => s.isStartingLevel);
  const error = useCampaignStore((s) => s.error);
  const init = useCampaignStore((s) => s.init);
  const selectBelt = useCampaignStore((s) => s.selectBelt);
  const startLevel = useCampaignStore((s) => s.startLevel);
  const clearError = useCampaignStore((s) => s.clearError);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate('/login?next=/campaign');
    }
  }, [authLoading, isAuthenticated, navigate]);

  // Fetch progress and levels on mount
  useEffect(() => {
    if (isAuthenticated) {
      init();
    }
  }, [isAuthenticated, init]);

  useEffect(() => { track('Visit Campaign Page'); }, []);

  const handleSelectBelt = useCallback(
    (belt: number) => {
      selectBelt(belt);
      track('Click Campaign Belt', { belt, isCompleted: !!progress?.beltsCompleted[belt] });
    },
    [selectBelt, progress?.beltsCompleted]
  );

  const handleStartLevel = useCallback(
    async (levelId: number) => {
      track('Click Campaign Level', { level: levelId, isCompleted: !!progress?.levelsCompleted[levelId] });
      try {
        const { gameId, playerKey } = await startLevel(levelId);
        navigate(`/game/${gameId}?playerKey=${playerKey}`);
      } catch {
        // Error is set in store
      }
    },
    [startLevel, navigate, progress?.levelsCompleted]
  );

  // Don't render until auth check is complete
  if (authLoading) {
    return (
      <div className="campaign">
        <div className="campaign-loading">Loading...</div>
      </div>
    );
  }

  // Redirect happens in useEffect, but prevent flash
  if (!isAuthenticated) {
    return null;
  }

  // Get levels for selected belt
  const beltLevels = getLevelsForBelt(levels, selectedBelt);

  return (
    <div className="campaign">
      <div className="campaign-header">
        <h1 className="campaign-title">Campaign Mode</h1>
        <p className="campaign-subtitle">Complete missions to earn your belts!</p>
      </div>

      {error && (
        <div className="campaign-error" role="alert" aria-live="polite">
          {error}
          <button className="campaign-error-dismiss" onClick={clearError}>
            Dismiss
          </button>
        </div>
      )}

      {isLoading && !progress ? (
        <div className="campaign-loading">Loading campaign...</div>
      ) : (
        <>
          <BeltSelector
            currentBelt={progress?.currentBelt ?? 1}
            maxBelt={progress?.maxBelt ?? 4}
            selectedBelt={selectedBelt}
            beltsCompleted={progress?.beltsCompleted ?? {}}
            onSelectBelt={handleSelectBelt}
          />

          {isLoading ? (
            <div className="campaign-loading">Loading levels...</div>
          ) : (
            <LevelGrid
              levels={beltLevels}
              onStartLevel={handleStartLevel}
              isStarting={isStartingLevel}
            />
          )}
        </>
      )}
    </div>
  );
}

export default Campaign;

/**
 * GameOverModal Component
 *
 * Displays when the game ends, showing winner and options.
 */

import { useState } from 'react';
import { useGameStore } from '../../stores/game';
import { useLobbyStore } from '../../stores/lobby';
import { useCampaignStore } from '../../stores/campaign';
import { useNavigate } from 'react-router-dom';
import {
  formatRatingChange,
  getRatingChangeClass,
  getBeltDisplayName,
} from '../../utils/ratings';
import { track } from '../../analytics';
import BeltIcon from '../BeltIcon';

export function GameOverModal() {
  const navigate = useNavigate();
  const [isStartingNext, setIsStartingNext] = useState(false);
  const status = useGameStore((s) => s.status);
  const winner = useGameStore((s) => s.winner);
  const winReason = useGameStore((s) => s.winReason);
  const playerNumber = useGameStore((s) => s.playerNumber);
  const reset = useGameStore((s) => s.reset);
  const gameId = useGameStore((s) => s.gameId);
  const ratingChange = useGameStore((s) => s.ratingChange);
  const campaignLevel = useGameStore((s) => s.campaignLevel);

  // Campaign store for starting next level
  const startLevel = useCampaignStore((s) => s.startLevel);

  // Lobby state for returning to lobby
  const lobbyCode = useLobbyStore((s) => s.code);
  const returnToLobby = useLobbyStore((s) => s.returnToLobby);
  const clearPendingGame = useLobbyStore((s) => s.clearPendingGame);

  // Only show when game is finished
  if (status !== 'finished') {
    return null;
  }

  const getResultText = () => {
    if (winner === null) {
      return 'Game Over';
    }

    if (winner === 0) {
      return 'Draw!';
    }

    if (winner === playerNumber) {
      return 'You Win!';
    }

    if (playerNumber === 0) {
      const colors = ['', 'White', 'Black', 'Red', 'Blue'];
      return `${colors[winner] || 'Player ' + winner} Wins!`;
    }

    return 'You Lose';
  };

  const getReasonText = () => {
    switch (winReason) {
      case 'king_captured':
        return 'King was captured';
      case 'draw_timeout':
        return 'Game timed out';
      case 'draw':
        return 'Draw agreed';
      case 'resignation':
        if (playerNumber === 0) return 'Player resigned';
        return winner === playerNumber ? 'Opponent resigned' : 'You resigned';
      default:
        return '';
    }
  };

  const getResultClass = () => {
    if (winner === 0) return 'draw';
    if (winner === playerNumber) return 'win';
    if (playerNumber === 0) return 'neutral';
    return 'lose';
  };

  const handleReturnToLobby = () => {
    track('Click Play Again', { source: 'game_over', player: playerNumber, gameId, level: campaignLevel?.level_id ?? null });
    // Send return_to_lobby message and navigate
    returnToLobby();
    clearPendingGame();
    reset();
    if (lobbyCode) {
      navigate(`/lobby/${lobbyCode}`);
    } else {
      // Try to get lobby code from session storage
      const storedLobbyCode = gameId ? sessionStorage.getItem(`lobbyCode_${gameId}`) : null;
      if (storedLobbyCode) {
        navigate(`/lobby/${storedLobbyCode}`);
      } else {
        navigate('/');
      }
    }
  };

  const handleViewReplay = () => {
    if (gameId) {
      track('Watch Replay', { historyId: gameId });
      reset();
      navigate(`/replay/${gameId}`);
    }
  };

  const handleBackToHome = () => {
    track('Cancel Game', { source: 'game_over', player: playerNumber, gameId, level: campaignLevel?.level_id ?? null });
    clearPendingGame();
    reset();
    navigate('/');
  };

  const handleNextLevel = async () => {
    if (!campaignLevel || isStartingNext) return;
    if (!campaignLevel.has_next_level) return;
    const nextLevelId = campaignLevel.level_id + 1;

    track('Click Next Level', { source: 'game_over', player: playerNumber, gameId, level: campaignLevel.level_id });
    setIsStartingNext(true);
    try {
      const { gameId: newGameId, playerKey } = await startLevel(nextLevelId);
      reset();
      navigate(`/game/${newGameId}?playerKey=${playerKey}`);
    } catch {
      setIsStartingNext(false);
    }
  };

  const handleRestartLevel = async () => {
    if (!campaignLevel || isStartingNext) return;

    track('Restart Level', { source: 'game_over', player: playerNumber, gameId, level: campaignLevel.level_id });
    setIsStartingNext(true);
    try {
      const { gameId: newGameId, playerKey } = await startLevel(campaignLevel.level_id);
      reset();
      navigate(`/game/${newGameId}?playerKey=${playerKey}`);
    } catch {
      setIsStartingNext(false);
    }
  };

  const handleBackToCampaign = () => {
    track('Cancel Campaign', { source: 'game_over' });
    reset();
    navigate('/campaign');
  };

  // Check if we came from a lobby
  const hasLobby = lobbyCode || (gameId && sessionStorage.getItem(`lobbyCode_${gameId}`));

  // Check if this is a campaign game and player won/lost
  const isCampaignWin = campaignLevel && winner === playerNumber && playerNumber > 0;
  const isCampaignLoss = campaignLevel && winner !== playerNumber && playerNumber > 0;
  const hasNextLevel = campaignLevel?.has_next_level;

  return (
    <div className="game-over-overlay">
      <div className={`game-over-modal ${getResultClass()}`}>
        <h2 className="game-over-title">{getResultText()}</h2>
        {winReason && <p className="game-over-reason">{getReasonText()}</p>}

        {/* Rating Change Display */}
        {ratingChange && (
          <div className="rating-change-display">
            <div className="rating-change-header">Rating</div>
            <div
              className={`rating-change-value ${getRatingChangeClass(
                ratingChange.oldRating,
                ratingChange.newRating
              )}`}
            >
              {formatRatingChange(ratingChange.oldRating, ratingChange.newRating)}
            </div>
            <div className="rating-change-details">
              <span>{ratingChange.oldRating}</span>
              <span className="rating-change-arrow">&rarr;</span>
              <span>{ratingChange.newRating}</span>
            </div>

            {/* Belt Change */}
            {ratingChange.beltChanged && (
              <div className="belt-change-display">
                <span className="belt-change-label">New Belt!</span>
                <BeltIcon belt={ratingChange.newBelt} size="lg" />
                <span className="belt-change-name">
                  {getBeltDisplayName(ratingChange.newBelt)}
                </span>
              </div>
            )}
          </div>
        )}

        <div className="game-over-actions">
          {isCampaignWin && hasNextLevel && (
            <button
              className="game-over-button primary"
              onClick={handleNextLevel}
              disabled={isStartingNext}
            >
              {isStartingNext ? 'Starting...' : 'Next Level'}
            </button>
          )}
          {isCampaignLoss && (
            <button
              className="game-over-button primary"
              onClick={handleRestartLevel}
              disabled={isStartingNext}
            >
              {isStartingNext ? 'Starting...' : 'Restart Level'}
            </button>
          )}
          {campaignLevel && (
            <button className="game-over-button secondary" onClick={handleBackToCampaign}>
              Back to Campaign
            </button>
          )}
          {hasLobby && !campaignLevel && (
            <button className="game-over-button primary" onClick={handleReturnToLobby}>
              Return to Lobby
            </button>
          )}
          {gameId && (
            <button className="game-over-button secondary" onClick={handleViewReplay}>
              View Replay
            </button>
          )}
          {!campaignLevel && (
            <button className="game-over-button secondary" onClick={handleBackToHome}>
              Back to Home
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

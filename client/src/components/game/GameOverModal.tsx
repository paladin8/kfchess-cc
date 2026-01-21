/**
 * GameOverModal Component
 *
 * Displays when the game ends, showing winner and options.
 */

import { useGameStore } from '../../stores/game';
import { useNavigate } from 'react-router-dom';

export function GameOverModal() {
  const navigate = useNavigate();
  const status = useGameStore((s) => s.status);
  const winner = useGameStore((s) => s.winner);
  const winReason = useGameStore((s) => s.winReason);
  const playerNumber = useGameStore((s) => s.playerNumber);
  const reset = useGameStore((s) => s.reset);

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
      case 'resignation':
        return 'Opponent resigned';
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

  const handlePlayAgain = () => {
    reset();
    navigate('/');
  };

  const handleBackToHome = () => {
    reset();
    navigate('/');
  };

  return (
    <div className="game-over-overlay">
      <div className={`game-over-modal ${getResultClass()}`}>
        <h2 className="game-over-title">{getResultText()}</h2>
        {winReason && <p className="game-over-reason">{getReasonText()}</p>}
        <div className="game-over-actions">
          <button className="game-over-button primary" onClick={handlePlayAgain}>
            Play Again
          </button>
          <button className="game-over-button secondary" onClick={handleBackToHome}>
            Back to Home
          </button>
        </div>
      </div>
    </div>
  );
}

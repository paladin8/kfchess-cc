import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGameStore } from '../stores/game';
import type { BoardType } from '../stores/game';

function Home() {
  const navigate = useNavigate();
  const createGame = useGameStore((s) => s.createGame);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedBoardType, setSelectedBoardType] = useState<BoardType>('standard');
  const [showBoardTypeModal, setShowBoardTypeModal] = useState(false);

  const handlePlayVsAI = () => {
    setShowBoardTypeModal(true);
  };

  const handleStartGame = async () => {
    if (isCreating) return;
    setIsCreating(true);

    try {
      await createGame({
        speed: 'standard',
        board_type: selectedBoardType,
        opponent: 'bot:dummy',
      });

      // Get the game ID from the store
      const gameId = useGameStore.getState().gameId;
      const playerKey = useGameStore.getState().playerKey;

      if (gameId) {
        // Store player key in session storage for reconnection
        if (playerKey) {
          sessionStorage.setItem(`playerKey_${gameId}`, playerKey);
        }
        navigate(`/game/${gameId}`);
      }
    } catch (error) {
      console.error('Failed to create game:', error);
      alert('Failed to create game. Please try again.');
    } finally {
      setIsCreating(false);
      setShowBoardTypeModal(false);
    }
  };

  return (
    <div className="home-page">
      <h1>Kung Fu Chess</h1>
      <p className="tagline">Real-time chess where both players move simultaneously</p>

      <div className="play-options">
        <div className="play-option">
          <h2>Quick Play</h2>
          <p>Jump into a game against an AI opponent</p>
          <button className="btn btn-primary" onClick={handlePlayVsAI} disabled={isCreating}>
            {isCreating ? 'Creating...' : 'Play vs AI'}
          </button>
        </div>

        <div className="play-option">
          <h2>Multiplayer</h2>
          <p>Find an opponent or create a lobby</p>
          <button className="btn btn-secondary" disabled>Browse Lobbies</button>
        </div>

        <div className="play-option">
          <h2>Campaign</h2>
          <p>Progress through 64 levels and earn belts</p>
          <button className="btn btn-secondary" disabled>Start Campaign</button>
        </div>
      </div>

      {/* Board Type Selection Modal */}
      {showBoardTypeModal && (
        <div className="modal-overlay" onClick={() => setShowBoardTypeModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Select Board Type</h2>
            <div className="board-type-options">
              <label className={`board-type-option ${selectedBoardType === 'standard' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="boardType"
                  value="standard"
                  checked={selectedBoardType === 'standard'}
                  onChange={() => setSelectedBoardType('standard')}
                />
                <div className="board-type-info">
                  <h3>Standard (8x8)</h3>
                  <p>Classic 2-player chess board</p>
                </div>
              </label>
              <label className={`board-type-option ${selectedBoardType === 'four_player' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="boardType"
                  value="four_player"
                  checked={selectedBoardType === 'four_player'}
                  onChange={() => setSelectedBoardType('four_player')}
                />
                <div className="board-type-info">
                  <h3>4-Player (12x12)</h3>
                  <p>Larger board with cut corners</p>
                </div>
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowBoardTypeModal(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleStartGame} disabled={isCreating}>
                {isCreating ? 'Creating...' : 'Start Game'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Home;

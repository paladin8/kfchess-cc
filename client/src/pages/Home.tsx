import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLobbyStore } from '../stores/lobby';
import './Home.css';

type BoardType = 'standard' | 'four_player';
type Speed = 'standard' | 'lightning';

function Home() {
  const navigate = useNavigate();
  const createLobby = useLobbyStore((s) => s.createLobby);
  const connect = useLobbyStore((s) => s.connect);

  const [isCreating, setIsCreating] = useState(false);
  const [selectedBoardType, setSelectedBoardType] = useState<BoardType>('standard');
  const [showBoardTypeModal, setShowBoardTypeModal] = useState(false);
  const [showCreateLobbyModal, setShowCreateLobbyModal] = useState(false);
  const [isCreatingLobby, setIsCreatingLobby] = useState(false);
  const [addAiToLobby, setAddAiToLobby] = useState(false);
  const [speed, setSpeed] = useState<Speed>(() => {
    return (localStorage.getItem('friendlySpeed') as Speed) || 'standard';
  });

  const handleSpeedChange = (newSpeed: Speed) => {
    setSpeed(newSpeed);
    localStorage.setItem('friendlySpeed', newSpeed);
  };

  const handlePlayVsAI = () => {
    setShowBoardTypeModal(true);
  };

  const handleStartGame = async () => {
    if (isCreating) return;
    setIsCreating(true);

    try {
      const playerCount = selectedBoardType === 'four_player' ? 4 : 2;
      const code = await createLobby(
        {
          isPublic: false,
          speed,
          playerCount,
          isRanked: false,
        },
        true
      );

      const state = useLobbyStore.getState();
      if (state.playerKey) {
        connect(code, state.playerKey);
      }
      navigate(`/lobby/${code}`);
    } catch (error) {
      console.error('Failed to create game:', error);
      alert('Failed to create game. Please try again.');
    } finally {
      setIsCreating(false);
      setShowBoardTypeModal(false);
    }
  };

  const handlePlayVsFriend = async () => {
    if (isCreating) return;
    setIsCreating(true);

    try {
      const code = await createLobby(
        {
          isPublic: false,
          speed,
          playerCount: 2,
          isRanked: false,
        },
        false
      );

      const state = useLobbyStore.getState();
      if (state.playerKey) {
        connect(code, state.playerKey);
      }
      navigate(`/lobby/${code}`);
    } catch (error) {
      console.error('Failed to create game:', error);
      alert('Failed to create game. Please try again.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleCampaign = () => {
    navigate('/campaign');
  };

  const handleCreateLobbySubmit = useCallback(async () => {
    if (isCreatingLobby) return;
    setIsCreatingLobby(true);

    try {
      const code = await createLobby(
        {
          isPublic: false,
          speed: 'standard',
          playerCount: 2,
          isRanked: false,
        },
        addAiToLobby
      );

      const state = useLobbyStore.getState();
      if (state.playerKey) {
        connect(code, state.playerKey);
      }
      navigate(`/lobby/${code}`);
    } catch (error) {
      console.error('Failed to create lobby:', error);
      alert('Failed to create lobby. Please try again.');
    } finally {
      setIsCreatingLobby(false);
      setShowCreateLobbyModal(false);
      setAddAiToLobby(false);
    }
  }, [createLobby, connect, navigate, addAiToLobby, isCreatingLobby]);

  return (
    <div className="home">
      <div className="home-banner">
        <div className="home-banner-inner">
          <div className="home-banner-video">
            <video autoPlay loop muted playsInline>
              <source src="/static/banner-video.mp4" type="video/mp4" />
            </video>
          </div>
          <div className="home-banner-text">
            <div className="home-banner-text-main">Chess Without Turns</div>
            <div className="home-banner-text-sub">
              The world's most popular strategy game goes real-time.
            </div>
          </div>
        </div>
      </div>

      <div className="home-play-buttons">
        <div className="home-play-button-wrapper">
          <button className="home-play-button" onClick={handleCampaign}>
            Campaign
          </button>
          <div className="home-play-subtitle">Complete Solo Missions</div>
        </div>

        <div className="home-play-button-wrapper">
          <button
            className="home-play-button"
            onClick={handlePlayVsAI}
            disabled={isCreating}
          >
            {isCreating ? 'Creating...' : 'Play vs AI'}
          </button>
          <div className="home-play-option-wrapper">
            <button
              className={`home-play-option ${speed === 'standard' ? 'selected' : ''}`}
              onClick={() => handleSpeedChange('standard')}
            >
              Standard
            </button>
            <button
              className={`home-play-option ${speed === 'lightning' ? 'selected' : ''}`}
              onClick={() => handleSpeedChange('lightning')}
            >
              Lightning
            </button>
          </div>
        </div>

        <div className="home-play-button-wrapper">
          <button
            className="home-play-button"
            onClick={handlePlayVsFriend}
            disabled={isCreating}
          >
            Play vs Friend
          </button>
          <div className="home-play-option-wrapper">
            <button
              className={`home-play-option ${speed === 'standard' ? 'selected' : ''}`}
              onClick={() => handleSpeedChange('standard')}
            >
              Standard
            </button>
            <button
              className={`home-play-option ${speed === 'lightning' ? 'selected' : ''}`}
              onClick={() => handleSpeedChange('lightning')}
            >
              Lightning
            </button>
          </div>
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

      {/* Create Lobby Modal */}
      {showCreateLobbyModal && (
        <div className="modal-overlay" onClick={() => setShowCreateLobbyModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Create Lobby</h2>
            <div className="board-type-options">
              <label className={`board-type-option ${!addAiToLobby ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="lobbyType"
                  checked={!addAiToLobby}
                  onChange={() => setAddAiToLobby(false)}
                />
                <div className="board-type-info">
                  <h3>Wait for Player</h3>
                  <p>Create a lobby and wait for someone to join</p>
                </div>
              </label>
              <label className={`board-type-option ${addAiToLobby ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="lobbyType"
                  checked={addAiToLobby}
                  onChange={() => setAddAiToLobby(true)}
                />
                <div className="board-type-info">
                  <h3>Play vs AI</h3>
                  <p>Create a lobby with an AI opponent</p>
                </div>
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowCreateLobbyModal(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleCreateLobbySubmit} disabled={isCreatingLobby}>
                {isCreatingLobby ? 'Creating...' : 'Create Lobby'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Home;

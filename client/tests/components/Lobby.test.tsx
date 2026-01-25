import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Lobby } from '../../src/pages/Lobby';
import { useLobbyStore } from '../../src/stores/lobby';
import type { Lobby as LobbyType, LobbyPlayer, LobbySettings } from '../../src/api/types';

// ============================================
// Test Fixtures
// ============================================

const createMockSettings = (overrides?: Partial<LobbySettings>): LobbySettings => ({
  isPublic: true,
  speed: 'standard',
  playerCount: 2,
  isRanked: false,
  ...overrides,
});

const createMockPlayer = (slot: number, overrides?: Partial<LobbyPlayer>): LobbyPlayer => ({
  slot,
  userId: null,
  username: `Player ${slot}`,
  isAi: false,
  aiType: null,
  isReady: false,
  isConnected: true,
  ...overrides,
});

const createMockLobby = (overrides?: Partial<LobbyType>): LobbyType => ({
  id: 1,
  code: 'ABC123',
  hostSlot: 1,
  settings: createMockSettings(),
  players: {
    1: createMockPlayer(1),
  },
  status: 'waiting',
  currentGameId: null,
  gamesPlayed: 0,
  ...overrides,
});

// Helper to render with router and specific URL
const renderWithRouter = (ui: React.ReactElement, { route = '/lobby/ABC123' } = {}) => {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/lobby/:code" element={ui} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
};

// ============================================
// Tests
// ============================================

describe('Lobby Page', () => {
  beforeEach(() => {
    // Reset store between tests
    useLobbyStore.getState().reset();
  });

  describe('Loading State', () => {
    it('shows loading when no lobby data', () => {
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        connectionState: 'connecting',
        lobby: null,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Connecting to lobby...')).toBeInTheDocument();
    });

    it('shows reconnecting state', () => {
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        connectionState: 'reconnecting',
        lobby: null,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
    });

    it('shows connecting message when disconnected with playerKey', () => {
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        connectionState: 'disconnected',
        error: null,
        lobby: null,
      });

      renderWithRouter(<Lobby />);
      // When disconnected with credentials but no lobby, shows loading state
      expect(screen.getByText(/Connecting|Loading/i)).toBeInTheDocument();
    });
  });

  describe('Join Modal (Direct URL Navigation)', () => {
    it('shows join modal when navigating directly without credentials', () => {
      // No credentials in store - simulates direct URL navigation
      useLobbyStore.setState({
        code: null,
        playerKey: null,
        lobby: null,
      });

      renderWithRouter(<Lobby />);
      // Modal heading
      expect(screen.getByRole('heading', { name: 'Join Lobby' })).toBeInTheDocument();
      expect(screen.getByText('Lobby Code: ABC123')).toBeInTheDocument();
    });

    it('shows username input for guests', () => {
      useLobbyStore.setState({
        code: null,
        playerKey: null,
        lobby: null,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByLabelText(/Display Name/i)).toBeInTheDocument();
    });
  });

  describe('Lobby Display', () => {
    it('renders lobby code in header', () => {
      const lobby = createMockLobby();
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('ABC123')).toBeInTheDocument();
    });

    it('renders player slots based on player count', () => {
      const lobby = createMockLobby({
        settings: createMockSettings({ playerCount: 2 }),
        players: {
          1: createMockPlayer(1),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Slot 1')).toBeInTheDocument();
      expect(screen.getByText('Slot 2')).toBeInTheDocument();
    });

    it('shows player name in slot', () => {
      const lobby = createMockLobby({
        players: {
          1: createMockPlayer(1, { username: 'TestPlayer' }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('TestPlayer')).toBeInTheDocument();
    });

    it('shows waiting message for empty slots', () => {
      const lobby = createMockLobby({
        settings: createMockSettings({ playerCount: 2 }),
        players: {
          1: createMockPlayer(1),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Empty')).toBeInTheDocument();
    });

    it('shows Host badge for host player', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Host')).toBeInTheDocument();
    });

    it('shows AI badge for AI players', () => {
      const lobby = createMockLobby({
        players: {
          1: createMockPlayer(1),
          2: createMockPlayer(2, { isAi: true, aiType: 'bot:dummy', username: 'AI Bot' }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('AI')).toBeInTheDocument();
    });

    it('shows Ready status for ready players', () => {
      const lobby = createMockLobby({
        players: {
          1: createMockPlayer(1, { isReady: true }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Ready')).toBeInTheDocument();
    });

    it('shows Not Ready status for not ready non-host players', () => {
      // Note: Hosts are always shown as Ready. This tests a non-host player.
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1, { isReady: true }),
          2: createMockPlayer(2, { isReady: false }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 2, // We are a non-host player
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Not Ready')).toBeInTheDocument();
    });
  });

  describe('Lobby Settings Display', () => {
    it('shows game settings section', () => {
      const lobby = createMockLobby({
        settings: createMockSettings({
          speed: 'standard',
          playerCount: 2,
          isPublic: true,
          isRanked: false,
        }),
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Game Settings')).toBeInTheDocument();
      // Settings labels are present
      expect(screen.getByText('Speed')).toBeInTheDocument();
      expect(screen.getByText('Visibility')).toBeInTheDocument();
      expect(screen.getByText('Rated')).toBeInTheDocument();
    });

    it('shows editable settings for host', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      // Host should see dropdowns, not just text
      const selects = screen.getAllByRole('combobox');
      expect(selects.length).toBeGreaterThan(0);
    });

    it('shows read-only settings for non-host', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1),
          2: createMockPlayer(2),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 2, // Not the host
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      // Non-host should see disabled dropdowns for settings
      const selects = screen.queryAllByRole('combobox');
      expect(selects.length).toBe(4);
      selects.forEach((select) => {
        expect(select).toBeDisabled();
      });
    });
  });

  describe('Action Buttons', () => {
    it('shows Ready button when non-host player is not ready', () => {
      // Note: Hosts don't have Ready/Cancel Ready buttons - they're always ready
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1, { isReady: true }),
          2: createMockPlayer(2, { isReady: false }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 2, // Non-host player
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Ready' })).toBeInTheDocument();
    });

    it('shows Cancel Ready button when non-host player is ready', () => {
      // Note: Hosts don't have Ready/Cancel Ready buttons - they're always ready
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1, { isReady: true }),
          2: createMockPlayer(2, { isReady: true }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 2, // Non-host player
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Cancel Ready' })).toBeInTheDocument();
    });

    it('does not show Ready/Cancel Ready buttons for host', () => {
      // Host is always ready and doesn't have ready toggle buttons
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1, { isReady: false }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1, // Host player
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.queryByRole('button', { name: 'Ready' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Cancel Ready' })).not.toBeInTheDocument();
    });

    it('shows Start Game button for host', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1, { isReady: true }),
          2: createMockPlayer(2, { isReady: true }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Start Game' })).toBeInTheDocument();
    });

    it('disables Start Game when not all ready', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1, { isReady: true }),
          2: createMockPlayer(2, { isReady: false }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Start Game' })).toBeDisabled();
    });

    it('disables Start Game when lobby not full', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        settings: createMockSettings({ playerCount: 2 }),
        players: {
          1: createMockPlayer(1, { isReady: true }),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Start Game' })).toBeDisabled();
    });

    it('shows Add AI button for host when lobby not full', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        settings: createMockSettings({ playerCount: 2 }),
        players: {
          1: createMockPlayer(1),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Add AI' })).toBeInTheDocument();
    });

    it('disables Add AI button when lobby is full', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        settings: createMockSettings({ playerCount: 2 }),
        players: {
          1: createMockPlayer(1),
          2: createMockPlayer(2),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Add AI' })).toBeDisabled();
    });

    it('shows Kick button for host on other players', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1),
          2: createMockPlayer(2),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Kick' })).toBeInTheDocument();
    });

    it('does not show Kick button for non-host', () => {
      const lobby = createMockLobby({
        hostSlot: 1,
        players: {
          1: createMockPlayer(1),
          2: createMockPlayer(2),
        },
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 2, // Not the host
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.queryByRole('button', { name: 'Kick' })).not.toBeInTheDocument();
    });
  });

  describe('Share Section', () => {
    it('shows share link for private lobbies', () => {
      const lobby = createMockLobby({
        settings: createMockSettings({ isPublic: false }),
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Share this link to invite players:')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    });

    it('hides share link for public lobbies', () => {
      const lobby = createMockLobby({
        settings: createMockSettings({ isPublic: true }),
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.queryByText('Share this link to invite players:')).not.toBeInTheDocument();
    });

    it('shows Copied! feedback after clicking copy', async () => {
      // Mock clipboard API
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText },
      });

      const lobby = createMockLobby({
        settings: createMockSettings({ isPublic: false }),
      });
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);

      const copyButton = screen.getByRole('button', { name: 'Copy' });
      fireEvent.click(copyButton);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Copied!' })).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('shows error banner when error is set', () => {
      const lobby = createMockLobby();
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        error: 'Something went wrong',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
    });

    it('clears error when dismiss is clicked', () => {
      const lobby = createMockLobby();
      const clearError = vi.fn();
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        error: 'Something went wrong',
        lobby,
        clearError,
      });

      renderWithRouter(<Lobby />);
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
      expect(clearError).toHaveBeenCalled();
    });
  });

  describe('Leave Lobby', () => {
    it('shows Leave Lobby button', () => {
      const lobby = createMockLobby();
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'connected',
        lobby,
      });

      renderWithRouter(<Lobby />);
      expect(screen.getByRole('button', { name: 'Leave Lobby' })).toBeInTheDocument();
    });
  });

  describe('Reconnection Banner', () => {
    it('shows reconnecting banner when reconnecting', () => {
      const lobby = createMockLobby();
      useLobbyStore.setState({
        code: 'ABC123',
        playerKey: 'key123',
        mySlot: 1,
        connectionState: 'reconnecting',
        lobby,
      });

      renderWithRouter(<Lobby />);
      // There should be a reconnecting banner at the bottom
      const banners = screen.getAllByText('Reconnecting...');
      expect(banners.length).toBeGreaterThan(0);
    });
  });
});

/**
 * Lobby Store - Zustand store for lobby state management
 *
 * Handles lobby creation, joining, WebSocket communication,
 * and real-time updates for the lobby system.
 */

import { create } from 'zustand';
import type { Lobby, LobbySettings, LobbyPlayer, LobbyListItem } from '../api/types';
import * as api from '../api/client';

// ============================================
// Types
// ============================================

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

// WebSocket message types (server -> client)
type LobbyServerMessage =
  | { type: 'lobby_state'; lobby: Lobby }
  | { type: 'player_joined'; slot: number; player: LobbyPlayer }
  | { type: 'player_left'; slot: number; reason: string }
  | { type: 'player_ready'; slot: number; ready: boolean }
  | { type: 'player_disconnected'; slot: number }
  | { type: 'player_reconnected'; slot: number; player: LobbyPlayer }
  | { type: 'settings_updated'; settings: LobbySettings }
  | { type: 'host_changed'; newHostSlot: number }
  | { type: 'game_starting'; gameId: string; playerKey: string; lobbyCode: string }
  | { type: 'game_ended'; winner: number; winReason: string }
  | { type: 'ai_type_changed'; slot: number; aiType: string; player: LobbyPlayer }
  | { type: 'error'; message: string };

interface LobbyState {
  // Connection state
  code: string | null;
  playerKey: string | null;
  mySlot: number | null;
  connectionState: ConnectionState;
  error: string | null;

  // Lobby data
  lobby: Lobby | null;

  // Public lobbies list
  publicLobbies: LobbyListItem[];
  isLoadingLobbies: boolean;

  // Game starting info (for navigation)
  pendingGameId: string | null;
  pendingGamePlayerKey: string | null;

  // Actions - REST
  createLobby: (settings?: Partial<LobbySettings>, addAi?: boolean) => Promise<string>;
  joinLobby: (code: string) => Promise<void>;
  fetchPublicLobbies: (speed?: string, playerCount?: number, isRanked?: boolean) => Promise<void>;

  // Actions - WebSocket
  connect: (code: string, playerKey: string) => void;
  disconnect: () => void;
  setReady: (ready: boolean) => void;
  updateSettings: (settings: Partial<LobbySettings>) => void;
  kickPlayer: (slot: number) => void;
  addAi: (aiType?: string) => void;
  removeAi: (slot: number) => void;
  changeAiDifficulty: (slot: number, aiType: string) => void;
  startGame: () => void;
  leaveLobby: () => void;
  returnToLobby: () => void;

  // Internal state management
  clearPendingGame: () => void;
  clearError: () => void;
  reset: () => void;

  // Internal WebSocket management
  _ws: WebSocket | null;
  _pingInterval: ReturnType<typeof setInterval> | null;
  _reconnectTimeout: ReturnType<typeof setTimeout> | null;
  _reconnectAttempts: number;
  _intentionalClose: boolean;
  _handleMessage: (event: MessageEvent) => void;
  _scheduleReconnect: () => void;
}

// ============================================
// Constants
// ============================================

const PING_INTERVAL_MS = 30000;
const RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;
const MAX_RECONNECT_ATTEMPTS = 10;

// ============================================
// Store
// ============================================

export const useLobbyStore = create<LobbyState>((set, get) => ({
  // Initial state
  code: null,
  playerKey: null,
  mySlot: null,
  connectionState: 'disconnected',
  error: null,
  lobby: null,
  publicLobbies: [],
  isLoadingLobbies: false,
  pendingGameId: null,
  pendingGamePlayerKey: null,

  // Internal WebSocket state
  _ws: null,
  _pingInterval: null,
  _reconnectTimeout: null,
  _reconnectAttempts: 0,
  _intentionalClose: false,

  // ============================================
  // REST API Actions
  // ============================================

  createLobby: async (settings, addAi = false) => {
    const guestId = getOrCreateGuestId();
    const response = await api.createLobby({
      settings,
      addAi,
      aiType: 'bot:novice',
      guestId,
    });

    set({
      code: response.code,
      playerKey: response.playerKey,
      mySlot: response.slot,
      lobby: response.lobby,
      error: null,
    });

    // Persist credentials for reconnection on refresh
    saveLobbyCredentials(response.code, response.playerKey, response.slot);

    return response.code;
  },

  joinLobby: async (code) => {
    const guestId = getOrCreateGuestId();
    const response = await api.joinLobby(code, {
      guestId,
    });

    set({
      code,
      playerKey: response.playerKey,
      mySlot: response.slot,
      lobby: response.lobby,
      error: null,
    });

    // Persist credentials for reconnection on refresh
    saveLobbyCredentials(code, response.playerKey, response.slot);
  },

  fetchPublicLobbies: async (speed, playerCount, isRanked) => {
    set({ isLoadingLobbies: true });
    try {
      const response = await api.listLobbies(speed, playerCount, isRanked);
      set({ publicLobbies: response.lobbies, isLoadingLobbies: false });
    } catch (error) {
      console.error('Failed to fetch public lobbies:', error);
      set({ isLoadingLobbies: false });
    }
  },

  // ============================================
  // WebSocket Actions
  // ============================================

  connect: (code, playerKey) => {
    const state = get();

    // Close existing connection (mark as intentional to prevent reconnect loop)
    if (state._ws) {
      set({ _intentionalClose: true });
      state._ws.close();
    }

    // Clear any pending reconnect
    if (state._reconnectTimeout) {
      clearTimeout(state._reconnectTimeout);
    }

    set({
      code,
      playerKey,
      connectionState: 'connecting',
      error: null,
      _intentionalClose: false,
      _reconnectAttempts: 0,
    });

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/lobby/${code}?player_key=${encodeURIComponent(playerKey)}`;

    try {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        set({
          connectionState: 'connected',
          _ws: ws,
          _reconnectAttempts: 0,
        });

        // Start ping interval
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, PING_INTERVAL_MS);

        set({ _pingInterval: pingInterval });
      };

      ws.onmessage = (event) => {
        get()._handleMessage(event);
      };

      ws.onclose = (event) => {
        const currentState = get();

        // Clear ping interval
        if (currentState._pingInterval) {
          clearInterval(currentState._pingInterval);
        }

        // Only clear _ws if this is the current WebSocket (not if a new one replaced it)
        if (currentState._ws === ws) {
          set({ _ws: null, _pingInterval: null });

          // Don't reconnect on permanent rejection codes — retrying won't help
          const permanentCodes = [4001, 4004]; // invalid key, lobby not found
          if (permanentCodes.includes(event.code)) {
            clearLobbyCredentials();
            set({ connectionState: 'disconnected', error: event.reason || 'Lobby unavailable' });
          } else if (!currentState._intentionalClose) {
            currentState._scheduleReconnect();
          } else {
            set({ connectionState: 'disconnected' });
          }
        }
      };

      ws.onerror = () => {
        set({ error: 'Connection error' });
      };

      set({ _ws: ws });
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      get()._scheduleReconnect();
    }
  },

  disconnect: () => {
    const state = get();

    set({ _intentionalClose: true });

    if (state._pingInterval) {
      clearInterval(state._pingInterval);
    }

    if (state._reconnectTimeout) {
      clearTimeout(state._reconnectTimeout);
    }

    if (state._ws) {
      state._ws.close();
    }

    set({
      connectionState: 'disconnected',
      _ws: null,
      _pingInterval: null,
      _reconnectTimeout: null,
    });
  },

  _scheduleReconnect: () => {
    const state = get();

    if (state._intentionalClose) {
      return;
    }

    if (state._reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('Max reconnection attempts reached');
      // Clear stale credentials to prevent infinite retry loop
      clearLobbyCredentials();
      set({ connectionState: 'disconnected', error: 'Connection lost' });
      return;
    }

    set({ connectionState: 'reconnecting' });

    // Exponential backoff with jitter
    const delay = Math.min(
      RECONNECT_DELAY_MS * Math.pow(2, state._reconnectAttempts) + Math.random() * 1000,
      MAX_RECONNECT_DELAY_MS
    );

    set({ _reconnectAttempts: state._reconnectAttempts + 1 });

    const timeout = setTimeout(() => {
      const currentState = get();
      if (currentState.code && currentState.playerKey) {
        currentState.connect(currentState.code, currentState.playerKey);
      }
    }, delay);

    set({ _reconnectTimeout: timeout });
  },

  _handleMessage: (event) => {
    let data: LobbyServerMessage;
    try {
      data = JSON.parse(event.data);
    } catch (error) {
      console.error('Failed to parse lobby message:', error);
      return;
    }

    switch (data.type) {
      case 'lobby_state':
        set({ lobby: data.lobby, error: null });
        break;

      case 'player_joined':
        set((state) => ({
          lobby: state.lobby
            ? {
                ...state.lobby,
                players: {
                  ...state.lobby.players,
                  [data.slot]: data.player,
                },
              }
            : null,
        }));
        break;

      case 'ai_type_changed':
        set((state) => ({
          lobby: state.lobby
            ? {
                ...state.lobby,
                players: {
                  ...state.lobby.players,
                  [data.slot]: data.player,
                },
              }
            : null,
        }));
        break;

      case 'player_left':
        set((state) => {
          if (!state.lobby) return state;
          const newPlayers = { ...state.lobby.players };
          delete newPlayers[data.slot];
          return {
            lobby: {
              ...state.lobby,
              players: newPlayers,
            },
          };
        });
        break;

      case 'player_ready':
        set((state) => {
          if (!state.lobby) return state;
          const player = state.lobby.players[data.slot];
          if (!player) return state;
          return {
            lobby: {
              ...state.lobby,
              players: {
                ...state.lobby.players,
                [data.slot]: { ...player, isReady: data.ready },
              },
            },
          };
        });
        break;

      case 'player_disconnected':
        set((state) => {
          if (!state.lobby) return state;
          const player = state.lobby.players[data.slot];
          if (!player) return state;
          return {
            lobby: {
              ...state.lobby,
              players: {
                ...state.lobby.players,
                [data.slot]: { ...player, isConnected: false, isReady: false },
              },
            },
          };
        });
        break;

      case 'player_reconnected':
        set((state) => ({
          lobby: state.lobby
            ? {
                ...state.lobby,
                players: {
                  ...state.lobby.players,
                  [data.slot]: data.player,
                },
              }
            : null,
        }));
        break;

      case 'settings_updated':
        set((state) => ({
          lobby: state.lobby
            ? {
                ...state.lobby,
                settings: data.settings,
              }
            : null,
        }));
        break;

      case 'host_changed':
        set((state) => ({
          lobby: state.lobby
            ? {
                ...state.lobby,
                hostSlot: data.newHostSlot,
              }
            : null,
        }));
        break;

      case 'game_starting':
        // Store player key and lobby code in sessionStorage FIRST for game page
        if (data.gameId && data.playerKey) {
          sessionStorage.setItem(`playerKey_${data.gameId}`, data.playerKey);
        }
        if (data.lobbyCode) {
          sessionStorage.setItem(`lobbyCode_${data.gameId}`, data.lobbyCode);
        }
        // Store game info for navigation
        set((state) => ({
          // Preserve lobbyCode from message in case state was lost
          code: state.code || data.lobbyCode,
          lobby: state.lobby
            ? {
                ...state.lobby,
                status: 'in_game',
                currentGameId: data.gameId,
              }
            : null,
          pendingGameId: data.gameId,
          pendingGamePlayerKey: data.playerKey,
        }));
        break;

      case 'game_ended':
        set((state) => ({
          lobby: state.lobby
            ? {
                ...state.lobby,
                status: 'finished',
                gamesPlayed: state.lobby.gamesPlayed + 1,
              }
            : null,
        }));
        break;

      case 'error':
        set({ error: data.message });
        break;

      default:
        // Unknown message type (e.g., 'pong')
        break;
    }
  },

  // ============================================
  // WebSocket Send Actions
  // ============================================

  setReady: (ready) => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'ready', ready }));
    }
  },

  updateSettings: (settings) => {
    const { _ws, lobby } = get();
    if (!_ws || _ws.readyState !== WebSocket.OPEN || !lobby) return;

    const newSettings = { ...lobby.settings, ...settings };
    _ws.send(JSON.stringify({ type: 'update_settings', settings: newSettings }));
  },

  kickPlayer: (slot) => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'kick', slot }));
    }
  },

  addAi: (aiType = 'bot:novice') => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'add_ai', aiType }));
    }
  },

  removeAi: (slot) => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'remove_ai', slot }));
    }
  },

  changeAiDifficulty: (slot, aiType) => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'change_ai_type', slot, aiType }));
    }
  },

  startGame: () => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'start_game' }));
    }
  },

  leaveLobby: () => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'leave' }));
    }
    get().disconnect();
    // Clear saved credentials
    clearLobbyCredentials();
    set({
      code: null,
      playerKey: null,
      mySlot: null,
      lobby: null,
      pendingGameId: null,
      pendingGamePlayerKey: null,
    });
  },

  returnToLobby: () => {
    const { _ws } = get();
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'return_to_lobby' }));
    }
  },

  // ============================================
  // State Management
  // ============================================

  clearPendingGame: () => {
    set({ pendingGameId: null, pendingGamePlayerKey: null });
  },

  clearError: () => {
    set({ error: null });
  },

  reset: () => {
    get().disconnect();
    set({
      code: null,
      playerKey: null,
      mySlot: null,
      connectionState: 'disconnected',
      error: null,
      lobby: null,
      publicLobbies: [],
      isLoadingLobbies: false,
      pendingGameId: null,
      pendingGamePlayerKey: null,
    });
  },
}));

// ============================================
// Helpers
// ============================================

const LOBBY_CREDENTIALS_KEY = 'kfchess_lobby_credentials';

interface LobbyCredentials {
  code: string;
  playerKey: string;
  slot: number;
}

/**
 * Save lobby credentials to sessionStorage for reconnection on refresh
 */
function saveLobbyCredentials(code: string, playerKey: string, slot: number): void {
  const credentials: LobbyCredentials = { code, playerKey, slot };
  sessionStorage.setItem(LOBBY_CREDENTIALS_KEY, JSON.stringify(credentials));
}

/**
 * Get saved lobby credentials from sessionStorage
 */
export function getSavedLobbyCredentials(): LobbyCredentials | null {
  const saved = sessionStorage.getItem(LOBBY_CREDENTIALS_KEY);
  if (!saved) return null;
  try {
    return JSON.parse(saved);
  } catch {
    return null;
  }
}

/**
 * Clear saved lobby credentials
 */
function clearLobbyCredentials(): void {
  sessionStorage.removeItem(LOBBY_CREDENTIALS_KEY);
}

/**
 * Get or create a persistent guest ID for anonymous players
 */
function getOrCreateGuestId(): string {
  const storageKey = 'kfchess_guest_id';
  let guestId = localStorage.getItem(storageKey);
  if (!guestId) {
    guestId = crypto.randomUUID();
    localStorage.setItem(storageKey, guestId);
  }
  return guestId;
}

// ============================================
// Selectors
// ============================================

export const selectIsHost = (state: LobbyState): boolean =>
  state.mySlot !== null && state.lobby?.hostSlot === state.mySlot;

export const selectMyPlayer = (state: LobbyState): LobbyPlayer | null =>
  state.mySlot !== null && state.lobby ? state.lobby.players[state.mySlot] ?? null : null;

export const selectIsAllReady = (state: LobbyState): boolean => {
  if (!state.lobby) return false;
  const hostSlot = state.lobby.hostSlot;
  const entries = Object.entries(state.lobby.players);
  if (entries.length < state.lobby.settings.playerCount) return false;
  // Host is always considered ready, only check non-host players
  return entries.every(([slot, p]) => Number(slot) === hostSlot || p.isReady);
};

export const selectIsFull = (state: LobbyState): boolean => {
  if (!state.lobby) return false;
  return Object.keys(state.lobby.players).length >= state.lobby.settings.playerCount;
};

export const selectCanStart = (state: LobbyState): boolean =>
  selectIsHost(state) && selectIsAllReady(state) && selectIsFull(state);

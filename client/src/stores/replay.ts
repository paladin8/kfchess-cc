/**
 * Replay Store - Zustand state management for replay playback
 *
 * This store manages WebSocket connection to the replay server and
 * stores the state received from the server. All game simulation
 * happens server-side; the client just renders what it receives.
 */

import { create } from 'zustand';
import type { Piece, ActiveMove, Cooldown, BoardType, GameSpeed } from './game';
import type { ConnectionState } from '../ws/types';
import { TIMING } from '../game';

// ============================================
// Types
// ============================================

interface ReplayState {
  // Connection
  gameId: string | null;
  connectionState: ConnectionState;
  error: string | null;

  // Replay metadata (from server)
  speed: GameSpeed | null;
  boardType: BoardType | null;
  players: Record<string, string> | null;
  totalTicks: number;
  winner: number | null;
  winReason: string | null;
  tickRateHz: number; // Tick rate used when replay was recorded (for backwards compat)

  // Playback state (from server)
  currentTick: number;
  lastTickTime: number; // timestamp when currentTick was last updated
  timeSinceTick: number; // milliseconds since tick started, from server
  isPlaying: boolean;

  // Game state (from server, same as live game)
  pieces: Piece[];
  activeMoves: ActiveMove[];
  cooldowns: Cooldown[];

  // Internal
  _ws: WebSocket | null;
}

interface ReplayActions {
  // Connection
  connect: (gameId: string) => void;
  disconnect: () => void;

  // Playback controls (send to server)
  play: () => void;
  pause: () => void;
  seek: (tick: number) => void;

  // Internal handlers
  _handleMessage: (event: MessageEvent) => void;
  _handleOpen: () => void;
  _handleClose: () => void;
  _handleError: (event: Event) => void;

  // Cleanup
  reset: () => void;
}

type ReplayStore = ReplayState & ReplayActions;

// ============================================
// Initial State
// ============================================

const initialState: ReplayState = {
  gameId: null,
  connectionState: 'disconnected',
  error: null,
  speed: null,
  boardType: null,
  players: null,
  totalTicks: 0,
  winner: null,
  winReason: null,
  tickRateHz: 10, // Default to 10 Hz for old replays
  currentTick: 0,
  lastTickTime: 0,
  timeSinceTick: 0,
  isPlaying: false,
  pieces: [],
  activeMoves: [],
  cooldowns: [],
  _ws: null,
};

// ============================================
// Store
// ============================================

export const useReplayStore = create<ReplayStore>((set, get) => ({
  ...initialState,

  connect: (gameId: string) => {
    const { _ws } = get();

    // Close existing connection
    if (_ws) {
      _ws.close();
    }

    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/replay/${gameId}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => get()._handleOpen();
    ws.onclose = () => get()._handleClose();
    ws.onerror = (event) => get()._handleError(event);
    ws.onmessage = (event) => get()._handleMessage(event);

    set({
      gameId,
      connectionState: 'connecting',
      error: null,
      _ws: ws,
    });
  },

  disconnect: () => {
    const { _ws } = get();
    if (_ws) {
      _ws.close();
    }
    set({ ...initialState });
  },

  play: () => {
    const { _ws, connectionState } = get();
    if (_ws && connectionState === 'connected') {
      _ws.send(JSON.stringify({ type: 'play' }));
    }
  },

  pause: () => {
    const { _ws, connectionState } = get();
    if (_ws && connectionState === 'connected') {
      _ws.send(JSON.stringify({ type: 'pause' }));
    }
  },

  seek: (tick: number) => {
    const { _ws, connectionState } = get();
    if (_ws && connectionState === 'connected') {
      _ws.send(JSON.stringify({ type: 'seek', tick }));
    }
  },

  _handleOpen: () => {
    set({ connectionState: 'connected' });
  },

  _handleClose: () => {
    set({ connectionState: 'disconnected', _ws: null });
  },

  _handleError: () => {
    const { _ws } = get();
    if (_ws) {
      _ws.close();
    }
    set({ error: 'WebSocket connection error', connectionState: 'disconnected', _ws: null });
  },

  _handleMessage: (event: MessageEvent) => {
    try {
      const message = JSON.parse(event.data);

      switch (message.type) {
        case 'replay_info':
          set({
            speed: message.speed,
            boardType: message.board_type,
            players: message.players,
            totalTicks: message.total_ticks,
            winner: message.winner,
            winReason: message.win_reason,
            tickRateHz: message.tick_rate_hz ?? 10, // Default to 10 Hz for old replays
          });
          // Don't auto-play - require user to click play
          // This ensures user interaction before audio plays (browser autoplay policy)
          break;

        case 'state':
          set({
            currentTick: message.tick,
            lastTickTime: performance.now(),
            timeSinceTick: message.time_since_tick ?? 0,
            pieces: message.pieces.map(convertPiece),
            activeMoves: message.active_moves.map(convertActiveMove),
            cooldowns: message.cooldowns.map(convertCooldown),
          });
          break;

        case 'playback_status':
          set({
            isPlaying: message.is_playing,
            currentTick: message.current_tick,
            totalTicks: message.total_ticks,
          });
          break;

        case 'game_over':
          set({
            isPlaying: false,
            winner: message.winner,
            winReason: message.reason,
          });
          break;

        case 'error':
          set({ error: message.message });
          break;
      }
    } catch (e) {
      console.error('Failed to parse replay message:', e);
    }
  },

  reset: () => {
    const { _ws } = get();
    if (_ws) {
      _ws.close();
    }
    set({ ...initialState });
  },
}));

// ============================================
// Helper Functions
// ============================================

interface ServerPiece {
  id: string;
  type: string;
  player: number;
  row: number;
  col: number;
  captured: boolean;
  moving: boolean;
  on_cooldown: boolean;
  moved?: boolean;
}

interface ServerActiveMove {
  piece_id: string;
  path: [number, number][];
  start_tick: number;
  progress: number;
}

interface ServerCooldown {
  piece_id: string;
  remaining_ticks: number;
}

function convertPiece(p: ServerPiece): Piece {
  return {
    id: p.id,
    type: p.type as Piece['type'],
    player: p.player,
    row: p.row,
    col: p.col,
    captured: p.captured,
    moving: p.moving,
    onCooldown: p.on_cooldown,
    moved: p.moved ?? false,
  };
}

function convertActiveMove(m: ServerActiveMove): ActiveMove {
  return {
    pieceId: m.piece_id,
    path: m.path,
    startTick: m.start_tick,
    progress: m.progress,
  };
}

function convertCooldown(c: ServerCooldown): Cooldown {
  return {
    pieceId: c.piece_id,
    remainingTicks: c.remaining_ticks,
  };
}

// ============================================
// Selectors
// ============================================

export const selectReplayProgress = (state: ReplayStore) => {
  if (state.totalTicks === 0) return 0;
  return (state.currentTick / state.totalTicks) * 100;
};

export const selectFormattedTime = (state: ReplayStore) => {
  // Use the replay's tick rate for accurate time display
  const ticksPerSecond = state.tickRateHz || TIMING.TICKS_PER_SECOND;
  const seconds = Math.floor(state.currentTick / ticksPerSecond);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
};

export const selectFormattedTotalTime = (state: ReplayStore) => {
  // Use the replay's tick rate for accurate time display
  const ticksPerSecond = state.tickRateHz || TIMING.TICKS_PER_SECOND;
  const seconds = Math.floor(state.totalTicks / ticksPerSecond);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
};

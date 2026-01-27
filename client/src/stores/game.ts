/**
 * Game Store - Zustand state management for the game
 *
 * Manages game state, WebSocket connection, and player actions.
 */

import { create } from 'zustand';
import * as api from '../api';
import type { ApiPiece, ApiActiveMove, ApiCooldown, CreateGameRequest } from '../api/types';
import { GameWebSocketClient } from '../ws/client';
import type {
  ConnectionState,
  JoinedMessage,
  StateUpdateMessage,
  CountdownMessage,
  GameStartedMessage,
  GameOverMessage,
  RatingUpdateMessage,
  MoveRejectedMessage,
  WsPieceState,
} from '../ws/types';
import type { RatingChangeData } from '../utils/ratings';

// ============================================
// Types
// ============================================

export type PieceType = 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';

export interface Piece {
  id: string;
  type: PieceType;
  player: number;
  row: number;
  col: number;
  captured: boolean;
  moving: boolean;
  onCooldown: boolean;
  moved: boolean; // Whether the piece has moved (for castling)
}

export interface ActiveMove {
  pieceId: string;
  path: [number, number][];
  startTick: number;
  progress: number;
}

export interface Cooldown {
  pieceId: string;
  remainingTicks: number;
}

export type GameStatus = 'waiting' | 'playing' | 'finished';
export type BoardType = 'standard' | 'four_player';
export type GameSpeed = 'standard' | 'lightning';

interface GameState {
  // Connection state
  gameId: string | null;
  playerKey: string | null;
  playerNumber: number; // 0 = spectator, 1-4 = player
  connectionState: ConnectionState;
  boardType: BoardType;
  speed: GameSpeed;
  tickRateHz: number; // Server tick rate for interpolation

  // Game state (from server)
  status: GameStatus;
  currentTick: number;
  lastTickTime: number; // timestamp when currentTick was last updated
  timeSinceTick: number; // milliseconds since tick started, from server (0-100)
  winner: number | null;
  winReason: string | null;
  pieces: Piece[];
  activeMoves: ActiveMove[];
  cooldowns: Cooldown[];

  // UI state
  selectedPieceId: string | null;
  lastError: string | null;
  countdown: number | null; // Countdown seconds before game starts (null = no countdown)

  // Rating change (for ranked games)
  ratingChange: RatingChangeData | null;

  // Audio events (for sound effects)
  captureCount: number; // Increments on each capture (for triggering capture sounds)

  // Internal
  wsClient: GameWebSocketClient | null;
}

interface GameActions {
  // Game lifecycle
  createGame: (options: CreateGameRequest) => Promise<void>;
  joinGame: (gameId: string, playerKey?: string) => Promise<void>;
  connect: () => void;
  disconnect: () => void;
  markReady: () => void;
  resyncState: () => Promise<void>;

  // Gameplay
  selectPiece: (pieceId: string | null) => void;
  makeMove: (toRow: number, toCol: number) => void;

  // Internal updates
  updateFromStateMessage: (msg: StateUpdateMessage) => void;
  handleJoined: (msg: JoinedMessage) => void;
  handleCountdown: (msg: CountdownMessage) => void;
  handleGameStarted: (msg: GameStartedMessage) => void;
  handleGameOver: (msg: GameOverMessage) => void;
  handleRatingUpdate: (msg: RatingUpdateMessage) => void;
  handleMoveRejected: (msg: MoveRejectedMessage) => void;
  setConnectionState: (state: ConnectionState) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

type GameStore = GameState & GameActions;

// ============================================
// Initial State
// ============================================

const initialState: GameState = {
  gameId: null,
  playerKey: null,
  playerNumber: 0,
  connectionState: 'disconnected',
  boardType: 'standard',
  speed: 'standard',
  tickRateHz: 30, // Default, will be overwritten by server
  status: 'waiting',
  currentTick: 0,
  lastTickTime: 0,
  timeSinceTick: 0,
  winner: null,
  winReason: null,
  pieces: [],
  activeMoves: [],
  cooldowns: [],
  selectedPieceId: null,
  lastError: null,
  countdown: null,
  ratingChange: null,
  captureCount: 0,
  wsClient: null,
};

// ============================================
// Helper Functions
// ============================================

function convertApiPiece(p: ApiPiece): Piece {
  return {
    id: p.id,
    type: p.type,
    player: p.player,
    row: p.row,
    col: p.col,
    captured: p.captured,
    moving: p.moving,
    onCooldown: p.on_cooldown,
    moved: p.moved ?? false,
  };
}

function convertApiActiveMove(m: ApiActiveMove): ActiveMove {
  return {
    pieceId: m.piece_id,
    path: m.path,
    startTick: m.start_tick,
    progress: m.progress,
  };
}

function convertApiCooldown(c: ApiCooldown): Cooldown {
  return {
    pieceId: c.piece_id,
    remainingTicks: c.remaining_ticks,
  };
}

function mergePieceUpdates(
  existing: Piece[],
  updates: WsPieceState[],
  activeMoveIds: Set<string>
): Piece[] {
  // Create maps for efficient lookup
  const existingMap = new Map(existing.map((p) => [p.id, p]));
  const updateMap = new Map(updates.map((u) => [u.id, u]));

  // Start with updated existing pieces
  const result: Piece[] = [];

  // Update existing pieces
  for (const piece of existing) {
    const update = updateMap.get(piece.id);
    if (update) {
      // Mark piece as moved if it's in an active move or was already moved
      const hasMoved = piece.moved || activeMoveIds.has(piece.id) || (update.moved ?? false);
      result.push({
        ...piece,
        row: update.row,
        col: update.col,
        captured: update.captured,
        type: update.type ?? piece.type,
        player: update.player ?? piece.player,
        moving: update.moving ?? piece.moving,
        onCooldown: update.on_cooldown ?? piece.onCooldown,
        moved: hasMoved,
      });
    } else {
      // Keep pieces that aren't in the update, but check if they're moving
      const hasMoved = piece.moved || activeMoveIds.has(piece.id);
      result.push({ ...piece, moved: hasMoved });
    }
  }

  // Add new pieces from updates that don't exist in existing
  for (const update of updates) {
    if (!existingMap.has(update.id)) {
      // Only add if we have required fields (type and player)
      if (update.type && update.player !== undefined) {
        result.push({
          id: update.id,
          type: update.type as PieceType,
          player: update.player,
          row: update.row,
          col: update.col,
          captured: update.captured,
          moving: update.moving ?? false,
          onCooldown: update.on_cooldown ?? false,
          moved: update.moved ?? activeMoveIds.has(update.id),
        });
      }
    }
  }

  return result;
}

// ============================================
// Store
// ============================================

export const useGameStore = create<GameStore>((set, get) => ({
  ...initialState,

  createGame: async (options) => {
    try {
      const response = await api.createGame(options);

      set({
        gameId: response.game_id,
        playerKey: response.player_key,
        playerNumber: response.player_number,
        boardType: response.board_type,
        speed: options.speed,
        status: 'waiting',
        lastError: null,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create game';
      set({ lastError: message });
      throw error;
    }
  },

  joinGame: async (gameId, playerKey) => {
    try {
      // Fetch initial game state
      const gameState = await api.getGameState(gameId);

      set({
        gameId,
        playerKey: playerKey ?? null,
        playerNumber: playerKey ? 1 : 0, // Will be determined by server
        boardType: gameState.board.board_type,
        speed: gameState.speed,
        status: gameState.status,
        currentTick: gameState.current_tick,
        winner: gameState.winner,
        pieces: gameState.board.pieces.map(convertApiPiece),
        activeMoves: gameState.active_moves.map(convertApiActiveMove),
        cooldowns: gameState.cooldowns.map(convertApiCooldown),
        lastError: null,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to join game';
      set({ lastError: message });
      throw error;
    }
  },

  connect: () => {
    const { gameId, playerKey, wsClient, connectionState } = get();

    if (!gameId) {
      return;
    }

    // If already connected or connecting, don't create a new connection
    if (wsClient && (connectionState === 'connected' || connectionState === 'connecting')) {
      return;
    }

    // Disconnect existing client if any
    if (wsClient) {
      wsClient.disconnect();
    }

    // Create new WebSocket client
    const client = new GameWebSocketClient({
      gameId,
      playerKey: playerKey ?? undefined,
      onStateUpdate: (msg) => get().updateFromStateMessage(msg),
      onJoined: (msg) => get().handleJoined(msg),
      onCountdown: (msg) => get().handleCountdown(msg),
      onGameStarted: (msg) => get().handleGameStarted(msg),
      onGameOver: (msg) => get().handleGameOver(msg),
      onRatingUpdate: (msg) => get().handleRatingUpdate(msg),
      onMoveRejected: (msg) => get().handleMoveRejected(msg),
      onError: (msg) => get().setError(msg.message),
      onConnectionChange: (state) => get().setConnectionState(state),
      onReconnected: () => get().resyncState(),
    });

    set({ wsClient: client });
    client.connect();
  },

  disconnect: () => {
    const { wsClient } = get();
    if (wsClient) {
      wsClient.disconnect();
    }
    set({ wsClient: null, connectionState: 'disconnected' });
  },

  resyncState: async () => {
    const { gameId } = get();
    if (!gameId) {
      return;
    }

    try {
      const gameState = await api.getGameState(gameId);
      set({
        status: gameState.status,
        speed: gameState.speed,
        currentTick: gameState.current_tick,
        winner: gameState.winner,
        pieces: gameState.board.pieces.map(convertApiPiece),
        activeMoves: gameState.active_moves.map(convertApiActiveMove),
        cooldowns: gameState.cooldowns.map(convertApiCooldown),
        // Clear any stale UI state
        selectedPieceId: null,
        countdown: null, // No countdown on rejoin - game already started
      });
    } catch (error) {
      console.error('Failed to resync state:', error);
    }
  },

  markReady: () => {
    const { wsClient } = get();
    if (wsClient) {
      wsClient.sendReady();
    }
  },


  selectPiece: (pieceId) => {
    const { pieces, playerNumber, status, countdown } = get();

    if (!pieceId) {
      set({ selectedPieceId: null });
      return;
    }

    // Can't select pieces if not playing, during countdown, or if spectator
    if (status !== 'playing' || playerNumber === 0 || countdown !== null) {
      return;
    }

    // Verify the piece belongs to the player
    const piece = pieces.find((p) => p.id === pieceId);
    if (!piece || piece.player !== playerNumber) {
      return;
    }

    // Can't select captured, moving, or on-cooldown pieces
    if (piece.captured || piece.moving || piece.onCooldown) {
      return;
    }

    // Just set selection - legal moves are computed dynamically in GameBoard
    set({ selectedPieceId: pieceId });
  },

  makeMove: (toRow, toCol) => {
    const { wsClient, selectedPieceId, countdown } = get();

    // Can't move during countdown
    if (!wsClient || !selectedPieceId || countdown !== null) {
      return;
    }

    wsClient.sendMove(selectedPieceId, toRow, toCol);

    // Don't clear selection here - wait for move confirmation or rejection
    // Selection will be cleared in updateFromStateMessage when piece starts moving
  },

  updateFromStateMessage: (msg) => {
    const { pieces: existingPieces, selectedPieceId, captureCount } = get();

    // Get IDs of pieces in active moves (they have moved)
    const activeMoveIds = new Set(msg.active_moves.map((m) => m.piece_id));

    // Merge piece updates
    const updatedPieces = mergePieceUpdates(existingPieces, msg.pieces, activeMoveIds);

    // Convert active moves and cooldowns
    const activeMoves: ActiveMove[] = msg.active_moves.map((m) => ({
      pieceId: m.piece_id,
      path: m.path,
      startTick: m.start_tick,
      progress: m.progress ?? 0,
    }));

    const cooldowns: Cooldown[] = msg.cooldowns.map((c) => ({
      pieceId: c.piece_id,
      remainingTicks: c.remaining_ticks,
    }));

    // Clear selection if the selected piece started moving
    let newSelectedPieceId = selectedPieceId;
    if (selectedPieceId) {
      const pieceIsMoving = activeMoves.some((m) => m.pieceId === selectedPieceId);
      if (pieceIsMoving) {
        newSelectedPieceId = null;
      }
    }

    // Count capture events for audio playback
    const captureEvents = msg.events.filter((e) => e.type === 'capture').length;
    const newCaptureCount = captureCount + captureEvents;

    set({
      currentTick: msg.tick,
      lastTickTime: performance.now(),
      timeSinceTick: msg.time_since_tick ?? 0,
      pieces: updatedPieces,
      activeMoves,
      cooldowns,
      selectedPieceId: newSelectedPieceId,
      captureCount: newCaptureCount,
    });
  },

  handleJoined: (msg) => {
    set({
      playerNumber: msg.player_number,
      tickRateHz: msg.tick_rate_hz ?? 30,
    });
  },

  handleCountdown: (msg) => {
    // Server sends countdown seconds (3, 2, 1)
    set({ countdown: msg.seconds });
  },

  handleGameStarted: (msg) => {
    // Clear countdown when game actually starts
    set({
      status: 'playing',
      currentTick: msg.tick,
      lastTickTime: performance.now(),
      countdown: null,
    });
  },

  handleGameOver: (msg) => {
    set({
      status: 'finished',
      winner: msg.winner,
      winReason: msg.reason,
    });
  },

  handleRatingUpdate: (msg) => {
    const { playerNumber } = get();
    const playerKey = String(playerNumber);
    const ratingData = msg.ratings[playerKey];

    if (ratingData) {
      set({
        ratingChange: {
          oldRating: ratingData.old_rating,
          newRating: ratingData.new_rating,
          oldBelt: ratingData.old_belt,
          newBelt: ratingData.new_belt,
          beltChanged: ratingData.belt_changed,
        },
      });
    }
  },

  handleMoveRejected: (msg) => {
    console.warn('Move rejected:', msg.piece_id, msg.reason);
    set({ lastError: `Move rejected: ${msg.reason}` });
  },

  setConnectionState: (state) => {
    set({ connectionState: state });
  },

  setError: (error) => {
    set({ lastError: error });
  },

  reset: () => {
    const { wsClient } = get();
    if (wsClient) {
      wsClient.disconnect();
    }
    set({ ...initialState });
  },
}));

// ============================================
// Selectors (for performance optimization)
// ============================================

export const selectPiece = (pieceId: string) => (state: GameStore) =>
  state.pieces.find((p) => p.id === pieceId);

export const selectIsMyPiece = (pieceId: string) => (state: GameStore) => {
  const piece = state.pieces.find((p) => p.id === pieceId);
  return piece?.player === state.playerNumber;
};

export const selectCanSelectPiece = (pieceId: string) => (state: GameStore) => {
  const piece = state.pieces.find((p) => p.id === pieceId);
  if (!piece) return false;
  return (
    piece.player === state.playerNumber &&
    !piece.captured &&
    !piece.moving &&
    !piece.onCooldown &&
    state.status === 'playing'
  );
};

/**
 * Check if the current player has been eliminated (their king is captured)
 * This is relevant for 4-player mode where players can be knocked out while the game continues
 */
export const selectIsPlayerEliminated = (state: GameStore) => {
  if (state.playerNumber === 0) return false; // Spectators can't be eliminated
  const myKing = state.pieces.find(
    (p) => p.type === 'K' && p.player === state.playerNumber
  );
  return myKing?.captured === true;
};

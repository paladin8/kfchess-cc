import { create } from 'zustand';

export type PieceType = 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';

export interface Piece {
  id: string;
  type: PieceType;
  player: number;
  row: number;
  col: number;
  captured: boolean;
}

export interface ActiveMove {
  pieceId: string;
  path: [number, number][];
  startTick: number;
}

export interface Cooldown {
  pieceId: string;
  startTick: number;
  duration: number;
}

export type GameStatus = 'waiting' | 'ready' | 'playing' | 'finished';

interface GameState {
  gameId: string | null;
  playerNumber: number; // 0 = spectator, 1-4 = player
  pieces: Piece[];
  activeMoves: ActiveMove[];
  cooldowns: Cooldown[];
  currentTick: number;
  status: GameStatus;
  winner: number | null;
  speed: 'standard' | 'lightning';

  // Actions
  setGameId: (gameId: string | null) => void;
  setPlayerNumber: (playerNumber: number) => void;
  updateGameState: (state: Partial<GameState>) => void;
  reset: () => void;
}

const initialState = {
  gameId: null,
  playerNumber: 0,
  pieces: [],
  activeMoves: [],
  cooldowns: [],
  currentTick: 0,
  status: 'waiting' as GameStatus,
  winner: null,
  speed: 'standard' as const,
};

export const useGameStore = create<GameState>((set) => ({
  ...initialState,

  setGameId: (gameId) => set({ gameId }),

  setPlayerNumber: (playerNumber) => set({ playerNumber }),

  updateGameState: (state) => set((prev) => ({ ...prev, ...state })),

  reset: () => set(initialState),
}));

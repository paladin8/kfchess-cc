import { create } from 'zustand';

export interface Lobby {
  id: number;
  code: string;
  name: string;
  hostId: number;
  hostUsername: string;
  speed: 'standard' | 'lightning';
  playerCount: number;
  currentPlayers: number;
  isPublic: boolean;
  isRanked: boolean;
  status: 'waiting' | 'starting' | 'in_game';
}

interface LobbyState {
  lobbies: Lobby[];
  currentLobby: Lobby | null;
  isLoading: boolean;

  // Actions
  setLobbies: (lobbies: Lobby[]) => void;
  setCurrentLobby: (lobby: Lobby | null) => void;
  setLoading: (loading: boolean) => void;
  addLobby: (lobby: Lobby) => void;
  removeLobby: (lobbyId: number) => void;
  updateLobby: (lobbyId: number, updates: Partial<Lobby>) => void;
}

export const useLobbyStore = create<LobbyState>((set) => ({
  lobbies: [],
  currentLobby: null,
  isLoading: false,

  setLobbies: (lobbies) => set({ lobbies }),

  setCurrentLobby: (currentLobby) => set({ currentLobby }),

  setLoading: (isLoading) => set({ isLoading }),

  addLobby: (lobby) =>
    set((state) => ({
      lobbies: [...state.lobbies, lobby],
    })),

  removeLobby: (lobbyId) =>
    set((state) => ({
      lobbies: state.lobbies.filter((l) => l.id !== lobbyId),
    })),

  updateLobby: (lobbyId, updates) =>
    set((state) => ({
      lobbies: state.lobbies.map((l) =>
        l.id === lobbyId ? { ...l, ...updates } : l
      ),
    })),
}));

/**
 * API Types - Type definitions for REST API communication
 */

// Piece representation from server
export interface ApiPiece {
  id: string;
  type: 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';
  player: number;
  row: number;
  col: number;
  captured: boolean;
  moving: boolean;
  on_cooldown: boolean;
  moved?: boolean; // Whether piece has moved (for castling) - tracked client-side if not sent
}

// Active move representation
export interface ApiActiveMove {
  piece_id: string;
  path: [number, number][];
  start_tick: number;
  progress: number;
}

// Cooldown representation
export interface ApiCooldown {
  piece_id: string;
  remaining_ticks: number;
}

// Board representation
export interface ApiBoard {
  board_type: 'standard' | 'four_player';
  width: number;
  height: number;
  pieces: ApiPiece[];
}

// Game state from server
export interface ApiGameState {
  game_id: string;
  status: 'waiting' | 'playing' | 'finished';
  current_tick: number;
  winner: number | null;
  board: ApiBoard;
  active_moves: ApiActiveMove[];
  cooldowns: ApiCooldown[];
}

// Create game request
export interface CreateGameRequest {
  speed: 'standard' | 'lightning';
  board_type: 'standard' | 'four_player';
  opponent: 'bot:dummy' | 'bot:random';
}

// Create game response
export interface CreateGameResponse {
  game_id: string;
  player_key: string;
  player_number: number;
  board_type: 'standard' | 'four_player';
  status: 'waiting';
}

// Make move request
export interface MakeMoveRequest {
  player_key: string;
  piece_id: string;
  to_row: number;
  to_col: number;
}

// Make move response (success)
export interface MakeMoveSuccessResponse {
  success: true;
  move: {
    piece_id: string;
    path: [number, number][];
    start_tick: number;
  };
}

// Make move response (error)
export interface MakeMoveErrorResponse {
  success: false;
  error:
    | 'game_not_found'
    | 'invalid_key'
    | 'game_over'
    | 'game_not_started'
    | 'piece_not_found'
    | 'not_your_piece'
    | 'piece_captured'
    | 'invalid_move';
  message: string;
}

export type MakeMoveResponse = MakeMoveSuccessResponse | MakeMoveErrorResponse;

// Mark ready request
export interface MarkReadyRequest {
  player_key: string;
}

// Mark ready response
export interface MarkReadyResponse {
  success: boolean;
  game_started: boolean;
  status: 'waiting' | 'playing' | 'finished';
}

// Legal moves response
export interface LegalMovesResponse {
  moves: {
    piece_id: string;
    targets: [number, number][];
  }[];
}

// API error response
export interface ApiError {
  detail: string;
}

// ============================================
// Replay Types
// ============================================

// A single move in a replay
export interface ApiReplayMove {
  tick: number;
  piece_id: string;
  to_row: number;
  to_col: number;
  player: number;
}

// Complete replay data from server
export interface ApiReplay {
  version: number;
  speed: 'standard' | 'lightning';
  board_type: 'standard' | 'four_player';
  players: Record<string, string>; // "1" -> "player_id"
  moves: ApiReplayMove[];
  total_ticks: number;
  winner: number | null;
  win_reason: string | null;
  created_at: string | null;
}

// Summary of a replay for listing
export interface ApiReplaySummary {
  game_id: string;
  speed: 'standard' | 'lightning';
  board_type: 'standard' | 'four_player';
  players: Record<string, string>;
  total_ticks: number;
  winner: number | null;
  win_reason: string | null;
  created_at: string | null;
}

// Response for listing replays
export interface ApiReplayListResponse {
  replays: ApiReplaySummary[];
  total: number;
}

// ============================================
// Auth Types
// ============================================

// User data from server (matches UserRead schema)
export interface ApiUser {
  id: number;
  email: string;
  username: string;
  picture_url: string | null;
  google_id: string | null;
  ratings: Record<string, number>;
  created_at: string;
  last_online: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
}

// Login request
export interface LoginRequest {
  username: string; // FastAPI-Users uses 'username' field for email
  password: string;
}

// Registration request
export interface RegisterRequest {
  email: string;
  password: string;
  username?: string; // Optional - will be auto-generated if not provided
}

// Update user request
export interface UpdateUserRequest {
  username?: string;
  picture_url?: string;
  password?: string;
}

// Auth error response
export interface AuthErrorResponse {
  detail: string | { code: string; reason: string };
}

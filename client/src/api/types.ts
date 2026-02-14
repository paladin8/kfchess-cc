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
  speed: 'standard' | 'lightning';
  current_tick: number;
  winner: number | null;
  players?: Record<string, PlayerDisplay>;
  board: ApiBoard;
  active_moves: ApiActiveMove[];
  cooldowns: ApiCooldown[];
}

// Create game request
export interface CreateGameRequest {
  speed: 'standard' | 'lightning';
  board_type: 'standard' | 'four_player';
  opponent: 'bot:novice' | 'bot:random';
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
  players: Record<string, PlayerDisplay>;
  moves: ApiReplayMove[];
  total_ticks: number;
  winner: number | null;
  win_reason: string | null;
  created_at: string | null;
}

// Player display info from server (name + optional picture/user ID)
export interface PlayerDisplay {
  name: string;
  picture_url: string | null;
  user_id: number | null;
  is_bot: boolean;
}

// Summary of a replay for listing
export interface ApiReplaySummary {
  game_id: string;
  speed: 'standard' | 'lightning';
  board_type: 'standard' | 'four_player';
  players: Record<string, PlayerDisplay>;
  total_ticks: number;
  winner: number | null;
  win_reason: string | null;
  created_at: string | null;
  likes: number;
  user_has_liked: boolean | null; // null if not authenticated
  is_ranked: boolean;
  campaign_level_id: number | null; // null for non-campaign games
}

// Response for like/unlike operations
export interface LikeResponse {
  likes: number;
  user_has_liked: boolean;
}

// Response for listing replays
export interface ApiReplayListResponse {
  replays: ApiReplaySummary[];
  total: number;
}

// ============================================
// Auth Types
// ============================================

// Rating stats for a single mode
export interface ApiRatingStats {
  rating: number;
  games: number;
  wins: number;
}

// User data from server (matches UserRead schema)
export interface ApiUser {
  id: number;
  email: string | null;
  username: string;
  picture_url: string | null;
  google_id: string | null;
  ratings: Record<string, ApiRatingStats | number>; // Can be old format (number) or new format (RatingStats)
  created_at: string;
  last_online: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
}

// Public user profile (excludes email and sensitive fields)
export interface ApiPublicUser {
  id: number;
  username: string;
  picture_url: string | null;
  ratings: Record<string, ApiRatingStats | number>;
  created_at: string;
  last_online: string;
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

// ============================================
// Lobby Types
// ============================================

// Lobby settings configuration
export interface LobbySettings {
  isPublic: boolean;
  speed: 'standard' | 'lightning';
  playerCount: 2 | 4;
  isRanked: boolean;
}

// A player in a lobby
export interface LobbyPlayer {
  slot: number;
  userId: number | null;
  username: string;
  pictureUrl: string | null;
  isAi: boolean;
  aiType: string | null;
  isReady: boolean;
  isConnected: boolean;
}

// Full lobby data from server
export interface Lobby {
  id: number;
  code: string;
  hostSlot: number;
  settings: LobbySettings;
  players: Record<number, LobbyPlayer>;
  status: 'waiting' | 'in_game' | 'finished';
  currentGameId: string | null;
  gamesPlayed: number;
}

// Create lobby request
export interface CreateLobbyRequest {
  settings?: Partial<LobbySettings>;
  addAi?: boolean;
  aiType?: string;
  guestId?: string;
}

// Create lobby response
export interface CreateLobbyResponse {
  id: number;
  code: string;
  playerKey: string;
  slot: number;
  lobby: Lobby;
}

// Join lobby request
export interface JoinLobbyRequest {
  preferredSlot?: number;
  guestId?: string;
}

// Join lobby response
export interface JoinLobbyResponse {
  playerKey: string;
  slot: number;
  lobby: Lobby;
}

// Lobby list item (for public lobbies)
export interface LobbyListItem {
  id: number;
  code: string;
  hostUsername: string;
  hostPictureUrl: string | null;
  settings: LobbySettings;
  playerCount: number;
  currentPlayers: number;
  status: string;
}

// Lobby list response
export interface LobbyListResponse {
  lobbies: LobbyListItem[];
}

// Get lobby response
export interface GetLobbyResponse {
  lobby: Lobby;
}

// ============================================
// Live Games Types
// ============================================

export interface LiveGamePlayer {
  slot: number;
  username: string;
  is_ai: boolean;
  user_id: number | null;
  picture_url: string | null;
}

export interface LiveGameItem {
  game_id: string;
  game_type: 'lobby' | 'campaign' | 'quickplay';
  lobby_code: string | null;
  campaign_level_id: number | null;
  players: LiveGamePlayer[];
  settings: {
    speed: string;
    playerCount: number;
    boardType: string;
  };
  current_tick: number;
  started_at: string | null;
}

export interface LiveGamesResponse {
  games: LiveGameItem[];
}

// ============================================
// Leaderboard Types
// ============================================

// Single entry in the leaderboard
export interface LeaderboardEntry {
  rank: number;
  user_id: number;
  username: string;
  picture_url: string | null;
  rating: number;
  belt: string;
  games_played: number;
  wins: number;
}

// Response for leaderboard queries
export interface LeaderboardResponse {
  mode: string;
  entries: LeaderboardEntry[];
}

// ============================================
// Campaign Types
// ============================================

// Campaign progress for a user
export interface CampaignProgress {
  levelsCompleted: Record<string, boolean>;
  beltsCompleted: Record<string, boolean>;
  currentBelt: number;
  maxBelt: number;
}

// Campaign level metadata
export interface CampaignLevel {
  levelId: number;
  belt: number;
  beltName: string;
  title: string;
  description: string;
  speed: 'standard' | 'lightning';
  playerCount: number;
  isUnlocked: boolean;
  isCompleted: boolean;
}

// Response for listing campaign levels
export interface CampaignLevelsResponse {
  levels: CampaignLevel[];
}

// Response for starting a campaign game
export interface StartCampaignGameResponse {
  gameId: string;
  playerKey: string;
  playerNumber: number;
}

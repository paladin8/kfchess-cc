/**
 * WebSocket Protocol Types
 *
 * Type definitions for WebSocket messages between client and server.
 */

// Piece state in WebSocket messages (minimal, for updates)
export interface WsPieceState {
  id: string;
  row: number;
  col: number;
  captured: boolean;
  type?: 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';
  player?: number;
  moving?: boolean;
  on_cooldown?: boolean;
  moved?: boolean; // Whether piece has moved (for castling)
}

// Active move in WebSocket messages
export interface WsActiveMove {
  piece_id: string;
  path: [number, number][];
  start_tick: number;
  progress?: number;
}

// Cooldown in WebSocket messages
export interface WsCooldown {
  piece_id: string;
  remaining_ticks: number;
}

// Game event types
export interface WsCaptureEvent {
  type: 'capture';
  capturer: string;
  captured: string;
  tick: number;
}

export interface WsPromotionEvent {
  type: 'promotion';
  piece_id: string;
  to_type: 'Q';
  tick: number;
}

export type WsGameEvent = WsCaptureEvent | WsPromotionEvent;

// ============================================
// Server -> Client Messages
// ============================================

export interface JoinedMessage {
  type: 'joined';
  player_number: number; // 0 = spectator, 1-4 = player
  tick_rate_hz: number; // Server tick rate for client synchronization
}

export interface StateUpdateMessage {
  type: 'state';
  tick: number;
  pieces: WsPieceState[];
  active_moves: WsActiveMove[];
  cooldowns: WsCooldown[];
  events: WsGameEvent[];
  time_since_tick?: number; // Milliseconds since tick started (0-100), optional for backwards compatibility
}

export interface CountdownMessage {
  type: 'countdown';
  seconds: number; // Seconds remaining (3, 2, 1)
}

export interface GameStartedMessage {
  type: 'game_started';
  tick: number;
}

export interface GameOverMessage {
  type: 'game_over';
  winner: number; // 0 for draw, 1-4 for player
  reason: 'king_captured' | 'draw_timeout' | 'resignation';
}

export interface RatingChangePayload {
  old_rating: number;
  new_rating: number;
  old_belt: string;
  new_belt: string;
  belt_changed: boolean;
}

export interface RatingUpdateMessage {
  type: 'rating_update';
  ratings: Record<string, RatingChangePayload>; // player_num (as string) -> rating change
}

export interface MoveRejectedMessage {
  type: 'move_rejected';
  piece_id: string;
  reason: string;
}

export interface PongMessage {
  type: 'pong';
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}

export type ServerMessage =
  | JoinedMessage
  | StateUpdateMessage
  | CountdownMessage
  | GameStartedMessage
  | GameOverMessage
  | RatingUpdateMessage
  | MoveRejectedMessage
  | PongMessage
  | ErrorMessage;

// ============================================
// Client -> Server Messages
// ============================================

export interface MoveClientMessage {
  type: 'move';
  piece_id: string;
  to_row: number;
  to_col: number;
}

export interface ReadyClientMessage {
  type: 'ready';
}

export interface PingClientMessage {
  type: 'ping';
}

export type ClientMessage = MoveClientMessage | ReadyClientMessage | PingClientMessage;

// ============================================
// Connection state
// ============================================

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

export interface WebSocketClientOptions {
  gameId: string;
  playerKey?: string;
  onJoined?: (msg: JoinedMessage) => void;
  onStateUpdate?: (msg: StateUpdateMessage) => void;
  onCountdown?: (msg: CountdownMessage) => void;
  onGameStarted?: (msg: GameStartedMessage) => void;
  onGameOver?: (msg: GameOverMessage) => void;
  onRatingUpdate?: (msg: RatingUpdateMessage) => void;
  onMoveRejected?: (msg: MoveRejectedMessage) => void;
  onError?: (msg: ErrorMessage) => void;
  onConnectionChange?: (state: ConnectionState) => void;
  onReconnected?: () => void;
}

/**
 * WebSocket Client - Connection management with reconnection logic
 *
 * Handles WebSocket connection to game server, message parsing,
 * and automatic reconnection on disconnect.
 */

import type {
  ClientMessage,
  ConnectionState,
  ServerMessage,
  WebSocketClientOptions,
} from './types';

const PING_INTERVAL_MS = 30000; // 30 seconds
const RECONNECT_DELAY_MS = 1000; // 1 second initial delay
const MAX_RECONNECT_DELAY_MS = 30000; // 30 seconds max delay
const MAX_RECONNECT_ATTEMPTS = 10;
const CONNECTION_TIMEOUT_MS = 10000; // 10 seconds to establish connection

// WebSocket close codes
const WS_CLOSE_GAME_NOT_FOUND = 4004;
const WS_CLOSE_SERVER_SHUTDOWN = 4301;
const WS_CLOSE_REDIRECT = 4302;

export class GameWebSocketClient {
  private ws: WebSocket | null = null;
  private options: WebSocketClientOptions;
  private connectionState: ConnectionState = 'disconnected';
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private connectionTimeout: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private intentionalClose = false;
  private hasConnectedBefore = false;
  private serverHint: string | null = null;

  constructor(options: WebSocketClientOptions) {
    this.options = options;
  }

  /**
   * Connect to the game WebSocket
   */
  connect(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    // Clean up any existing non-OPEN WebSocket (e.g., stuck in CONNECTING)
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }

    this.clearConnectionTimeout();
    this.intentionalClose = false;
    this.setConnectionState('connecting');

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    let url = `${protocol}//${host}/ws/game/${this.options.gameId}`;

    if (this.options.playerKey) {
      url += `?player_key=${encodeURIComponent(this.options.playerKey)}`;
    }

    // Append server routing hint if set (one-shot, cleared after use)
    if (this.serverHint) {
      const separator = url.includes('?') ? '&' : '?';
      url += `${separator}server=${encodeURIComponent(this.serverHint)}`;
      this.serverHint = null;
    }

    try {
      this.ws = new WebSocket(url);
      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
      this.ws.onerror = this.handleError.bind(this);

      // Timeout if connection doesn't establish (e.g., TCP connects but upgrade hangs)
      this.connectionTimeout = setTimeout(() => {
        if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
          console.warn('WebSocket connection timeout');
          this.ws.close();
        }
      }, CONNECTION_TIMEOUT_MS);
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from the WebSocket
   */
  disconnect(): void {
    this.intentionalClose = true;
    this.stopPing();
    this.clearReconnectTimeout();
    this.clearConnectionTimeout();

    if (this.ws) {
      // Clear handlers before closing to prevent stale async onclose events
      // from updating shared store state after a new client is created
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }

    this.setConnectionState('disconnected');
  }

  /**
   * Send a message to the server
   */
  send(message: ClientMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not connected, cannot send message');
      return;
    }

    this.ws.send(JSON.stringify(message));
  }

  /**
   * Send a move command
   */
  sendMove(pieceId: string, toRow: number, toCol: number): void {
    this.send({
      type: 'move',
      piece_id: pieceId,
      to_row: toRow,
      to_col: toCol,
    });
  }

  /**
   * Send ready signal
   */
  sendReady(): void {
    this.send({ type: 'ready' });
  }

  /**
   * Send resign signal
   */
  sendResign(): void {
    this.send({ type: 'resign' });
  }

  /**
   * Send draw offer
   */
  sendOfferDraw(): void {
    this.send({ type: 'offer_draw' });
  }

  /**
   * Get current connection state
   */
  getConnectionState(): ConnectionState {
    return this.connectionState;
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.connectionState === 'connected';
  }

  // ============================================
  // Private methods
  // ============================================

  private setConnectionState(state: ConnectionState): void {
    this.connectionState = state;
    this.options.onConnectionChange?.(state);
  }

  private handleOpen(): void {
    this.clearConnectionTimeout();
    const isReconnect = this.hasConnectedBefore;
    this.hasConnectedBefore = true;
    this.reconnectAttempts = 0;
    this.setConnectionState('connected');
    this.startPing();

    // Notify about reconnection so state can be resynced
    if (isReconnect) {
      this.options.onReconnected?.();
    }
  }

  private handleMessage(event: MessageEvent): void {
    let data: ServerMessage;

    try {
      data = JSON.parse(event.data);
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
      return;
    }

    switch (data.type) {
      case 'joined':
        this.options.onJoined?.(data);
        break;
      case 'state':
        this.options.onStateUpdate?.(data);
        break;
      case 'countdown':
        this.options.onCountdown?.(data);
        break;
      case 'game_started':
        this.options.onGameStarted?.(data);
        break;
      case 'game_over':
        this.options.onGameOver?.(data);
        break;
      case 'rating_update':
        this.options.onRatingUpdate?.(data);
        break;
      case 'draw_offered':
        this.options.onDrawOffered?.(data);
        break;
      case 'move_rejected':
        this.options.onMoveRejected?.(data);
        break;
      case 'pong':
        // Pong received, connection is healthy
        break;
      case 'error':
        this.options.onError?.(data);
        break;
      default:
        console.warn('Unknown WebSocket message type:', data);
    }
  }

  private handleClose(event: CloseEvent): void {
    this.clearConnectionTimeout();
    this.stopPing();
    this.ws = null;

    if (this.intentionalClose) {
      this.setConnectionState('disconnected');
      return;
    }

    if (event.code === WS_CLOSE_GAME_NOT_FOUND) {
      // Game doesn't exist — no point retrying
      this.setConnectionState('disconnected');
      return;
    }

    if (event.code === WS_CLOSE_SERVER_SHUTDOWN) {
      // Server shutting down — reconnect with jitter (round-robin, no routing hint)
      this.serverHint = null;
      this.reconnectAttempts = 0;
      setTimeout(() => this.connect(), Math.random() * 500);
      return;
    }

    if (event.code === WS_CLOSE_REDIRECT) {
      // Redirect to specific server — reconnect immediately with routing hint
      this.serverHint = event.reason;
      this.reconnectAttempts = 0;
      this.connect();
      return;
    }

    this.scheduleReconnect();
  }

  private handleError(): void {
    // The close handler will be called after this, which handles reconnection
  }

  private startPing(): void {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.intentionalClose) {
      return;
    }

    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('Max reconnection attempts reached');
      this.setConnectionState('disconnected');
      return;
    }

    this.setConnectionState('reconnecting');

    // Exponential backoff with jitter
    const delay = Math.min(
      RECONNECT_DELAY_MS * Math.pow(2, this.reconnectAttempts) + Math.random() * 1000,
      MAX_RECONNECT_DELAY_MS
    );

    this.reconnectAttempts++;
    console.log(`Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private clearReconnectTimeout(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  private clearConnectionTimeout(): void {
    if (this.connectionTimeout) {
      clearTimeout(this.connectionTimeout);
      this.connectionTimeout = null;
    }
  }
}

// Factory function for easier creation
export function createGameWebSocket(options: WebSocketClientOptions): GameWebSocketClient {
  return new GameWebSocketClient(options);
}

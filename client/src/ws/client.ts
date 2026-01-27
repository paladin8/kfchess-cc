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

export class GameWebSocketClient {
  private ws: WebSocket | null = null;
  private options: WebSocketClientOptions;
  private connectionState: ConnectionState = 'disconnected';
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private intentionalClose = false;
  private hasConnectedBefore = false;

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

    this.intentionalClose = false;
    this.setConnectionState('connecting');

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    let url = `${protocol}//${host}/ws/game/${this.options.gameId}`;

    if (this.options.playerKey) {
      url += `?player_key=${encodeURIComponent(this.options.playerKey)}`;
    }

    try {
      this.ws = new WebSocket(url);
      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
      this.ws.onerror = this.handleError.bind(this);
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

    if (this.ws) {
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

  private handleClose(): void {
    this.stopPing();
    this.ws = null;

    if (this.intentionalClose) {
      this.setConnectionState('disconnected');
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
}

// Factory function for easier creation
export function createGameWebSocket(options: WebSocketClientOptions): GameWebSocketClient {
  return new GameWebSocketClient(options);
}

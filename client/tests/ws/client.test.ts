/**
 * Tests for GameWebSocketClient - multi-server routing close codes
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { GameWebSocketClient } from '../../src/ws/client';
import type { WebSocketClientOptions } from '../../src/ws/types';

// Mock WebSocket class
class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.OPEN;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send = vi.fn();
  close = vi.fn();

  // Helper to simulate server closing the connection
  simulateClose(code: number, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    const event = new CloseEvent('close', { code, reason });
    this.onclose?.(event);
  }

  // Helper to simulate connection open
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }
}

// Replace global WebSocket with mock
const originalWebSocket = globalThis.WebSocket;

describe('GameWebSocketClient - routing close codes', () => {
  let options: WebSocketClientOptions;

  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).WebSocket = MockWebSocket;

    options = {
      gameId: 'TEST1234',
      playerKey: 'p1_testkey',
    };
  });

  afterEach(() => {
    vi.useRealTimers();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).WebSocket = originalWebSocket;
  });

  describe('normal close', () => {
    it('schedules reconnect with backoff on normal close', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(1006); // Abnormal close

      // Should schedule reconnect (reconnecting state)
      expect(client.getConnectionState()).toBe('reconnecting');
    });
  });

  describe('4301 - server shutdown', () => {
    it('reconnects with jitter on 4301', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      // Server sends 4301 (shutdown)
      ws.simulateClose(4301, '');

      // Should have scheduled a reconnect via setTimeout (jitter 0-500ms)
      // Advance timers to trigger the reconnect
      vi.advanceTimersByTime(600);

      // A new WebSocket should have been created
      expect(MockWebSocket.instances.length).toBe(2);
    });

    it('resets reconnect attempts on 4301', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      // Simulate some failed reconnects to increase the counter
      ws.simulateClose(1006);
      vi.advanceTimersByTime(5000);
      // After reconnect attempt, simulate another close
      const ws2 = MockWebSocket.instances[1];
      ws2.simulateClose(4301);

      // Advance past jitter
      vi.advanceTimersByTime(600);

      // Should have created another WebSocket (reconnect succeeded because counter was reset)
      expect(MockWebSocket.instances.length).toBe(3);
    });

    it('does not include server hint in URL on 4301', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4301, 'worker1');

      vi.advanceTimersByTime(600);

      const reconnectWs = MockWebSocket.instances[1];
      expect(reconnectWs.url).not.toContain('server=');
    });
  });

  describe('4302 - redirect', () => {
    it('reconnects immediately with server hint on 4302', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      // Server sends 4302 redirect with target server
      ws.simulateClose(4302, 'worker2');

      // Should reconnect immediately (no setTimeout needed)
      expect(MockWebSocket.instances.length).toBe(2);
    });

    it('includes server= query param in redirect URL', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4302, 'worker2');

      const reconnectWs = MockWebSocket.instances[1];
      expect(reconnectWs.url).toContain('server=worker2');
    });

    it('appends server param with & when player_key exists', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4302, 'worker3');

      const reconnectWs = MockWebSocket.instances[1];
      // URL should have player_key first, then &server=
      expect(reconnectWs.url).toContain('player_key=');
      expect(reconnectWs.url).toContain('&server=worker3');
    });

    it('uses ? separator when no player_key', () => {
      const noKeyOptions: WebSocketClientOptions = {
        gameId: 'TEST1234',
        // no playerKey (spectator)
      };
      const client = new GameWebSocketClient(noKeyOptions);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4302, 'worker1');

      const reconnectWs = MockWebSocket.instances[1];
      expect(reconnectWs.url).toContain('?server=worker1');
      expect(reconnectWs.url).not.toContain('&server=');
    });

    it('clears server hint after use (one-shot)', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4302, 'worker2');

      // First reconnect includes server hint
      const reconnectWs = MockWebSocket.instances[1];
      expect(reconnectWs.url).toContain('server=worker2');

      // Simulate that reconnect also fails (normal close)
      reconnectWs.simulateClose(1006);
      vi.advanceTimersByTime(5000);

      // Second reconnect should NOT include server hint
      const reconnectWs2 = MockWebSocket.instances[2];
      expect(reconnectWs2.url).not.toContain('server=');
    });

    it('resets reconnect attempts on 4302', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      // Redirect resets counter
      ws.simulateClose(4302, 'worker2');
      expect(MockWebSocket.instances.length).toBe(2);
    });

    it('encodes server hint in URL', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4302, 'worker with spaces');

      const reconnectWs = MockWebSocket.instances[1];
      expect(reconnectWs.url).toContain('server=worker%20with%20spaces');
    });
  });

  describe('intentional close', () => {
    it('does not reconnect on intentional disconnect', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      client.disconnect();

      expect(client.getConnectionState()).toBe('disconnected');
      expect(MockWebSocket.instances.length).toBe(1);
    });
  });
});

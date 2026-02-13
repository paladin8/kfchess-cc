/**
 * Tests for GameWebSocketClient - multi-server routing close codes
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { GameWebSocketClient } from '../../src/ws/client';
import type { WebSocketClientOptions } from '../../src/ws/types';

// Mock WebSocket class
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.CONNECTING;
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

    it('clears event handlers on disconnect to prevent stale callbacks', () => {
      const onConnectionChange = vi.fn();
      const client = new GameWebSocketClient({
        ...options,
        onConnectionChange,
      });
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      // Reset mock to track calls after disconnect
      onConnectionChange.mockClear();

      client.disconnect();

      // disconnect() itself fires onConnectionChange('disconnected')
      expect(onConnectionChange).toHaveBeenCalledWith('disconnected');
      onConnectionChange.mockClear();

      // Handlers should be cleared — stale close event should NOT update state
      expect(ws.onopen).toBeNull();
      expect(ws.onmessage).toBeNull();
      expect(ws.onclose).toBeNull();
      expect(ws.onerror).toBeNull();

      // Simulating a stale close event should be a no-op
      ws.simulateClose(1006);
      expect(onConnectionChange).not.toHaveBeenCalled();
    });

    it('stale close event does not corrupt new client state', () => {
      const onConnectionChange = vi.fn();
      const optionsWithCallback = {
        ...options,
        onConnectionChange,
      };
      const client = new GameWebSocketClient(optionsWithCallback);
      client.connect();

      const ws1 = MockWebSocket.instances[0];
      ws1.simulateOpen();

      // Disconnect old client
      client.disconnect();
      onConnectionChange.mockClear();

      // Simulate stale close event from old WebSocket (arrives async)
      // Handlers were cleared so this should be a no-op
      ws1.simulateClose(1006);
      expect(onConnectionChange).not.toHaveBeenCalled();
    });
  });

  describe('connection timeout', () => {
    it('closes WebSocket if connection not established within timeout', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      // Don't call simulateOpen — connection hangs
      expect(ws.readyState).toBe(MockWebSocket.CONNECTING);

      // Advance past the 10s connection timeout
      vi.advanceTimersByTime(10000);

      // Should have called close() on the hanging WebSocket
      expect(ws.close).toHaveBeenCalled();
    });

    it('does not close WebSocket if connection succeeds before timeout', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();

      // Advance past the timeout
      vi.advanceTimersByTime(10000);

      // close() should NOT have been called (only the close mock from potential other calls)
      expect(ws.close).not.toHaveBeenCalled();
      expect(client.getConnectionState()).toBe('connected');
    });

    it('triggers reconnect after connection timeout', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      // Connection hangs — don't call simulateOpen

      // Advance past timeout
      vi.advanceTimersByTime(10000);
      expect(ws.close).toHaveBeenCalled();

      // Simulate browser firing close event after ws.close()
      ws.simulateClose(1006);
      expect(client.getConnectionState()).toBe('reconnecting');

      // Advance past reconnect delay to trigger reconnection
      vi.advanceTimersByTime(5000);
      expect(MockWebSocket.instances.length).toBe(2);
    });

    it('clears connection timeout on disconnect', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      // Don't open — connection hanging

      // Disconnect before timeout fires
      client.disconnect();
      // disconnect() calls ws.close() once (via the cleanup in connect() is not applicable here,
      // but the explicit close in disconnect() is)
      expect(ws.close).toHaveBeenCalledTimes(1);

      // Advance past timeout — timeout should have been cleared
      ws.close.mockClear();
      vi.advanceTimersByTime(10000);
      expect(ws.close).not.toHaveBeenCalled();
    });

    it('stale timeout does not close a new WebSocket after quick reconnect', () => {
      const client = new GameWebSocketClient(options);
      client.connect(); // t=0, WS1 created, 10s timeout starts

      const ws1 = MockWebSocket.instances[0];
      // WS1 closes quickly (e.g., server rejects before upgrade)
      // handleClose clears WS1's 10s timeout
      ws1.simulateClose(1006);
      expect(client.getConnectionState()).toBe('reconnecting');

      // Reconnect fires at ~t=2s, creating WS2 with its own 10s timeout
      vi.advanceTimersByTime(5000); // t=5s
      expect(MockWebSocket.instances.length).toBe(2);
      const ws2 = MockWebSocket.instances[1];
      expect(ws2.readyState).toBe(MockWebSocket.CONNECTING);

      // Advance to t=10s — past when WS1's timeout WOULD have fired,
      // but before WS2's own timeout (which started at ~t=2s, fires at ~t=12s)
      vi.advanceTimersByTime(5000); // t=10s
      expect(ws2.close).not.toHaveBeenCalled();
    });

    it('cleans up CONNECTING WebSocket when connect() is called again', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws1 = MockWebSocket.instances[0];
      expect(ws1.readyState).toBe(MockWebSocket.CONNECTING);

      // Simulate 4302 redirect: handleClose sets ws=null, then calls connect()
      ws1.simulateClose(4302, 'worker2');

      // A new WebSocket should be created
      expect(MockWebSocket.instances.length).toBe(2);
      const ws2 = MockWebSocket.instances[1];

      // Old WebSocket's handlers should have been cleared by handleClose flow
      // (handleClose sets this.ws = null, so connect() sees no existing ws)
      expect(ws2.url).toContain('server=worker2');
    });
  });

  describe('4004 - game not found', () => {
    it('does not reconnect on game not found', () => {
      const client = new GameWebSocketClient(options);
      client.connect();

      const ws = MockWebSocket.instances[0];
      ws.simulateOpen();
      ws.simulateClose(4004);

      expect(client.getConnectionState()).toBe('disconnected');
      expect(MockWebSocket.instances.length).toBe(1);
    });
  });
});

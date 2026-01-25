import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  useReplayStore,
  selectReplayProgress,
  selectFormattedTime,
  selectFormattedTotalTime,
} from '../../src/stores/replay';

// ============================================
// Mock WebSocket
// ============================================

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  readyState: number = 0; // CONNECTING
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = 3; // CLOSED
    if (this.onclose) {
      this.onclose();
    }
  }

  // Test helpers
  simulateOpen() {
    this.readyState = 1; // OPEN
    if (this.onopen) {
      this.onopen();
    }
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }

  static reset() {
    MockWebSocket.instances = [];
  }

  static getLatest(): MockWebSocket | undefined {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }
}

// ============================================
// Test Setup
// ============================================

describe('useReplayStore', () => {
  beforeEach(() => {
    // Reset store state
    useReplayStore.getState().reset();
    // Reset mock WebSocket
    MockWebSocket.reset();
    // Mock global WebSocket
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ============================================
  // Connection Tests
  // ============================================

  describe('connect', () => {
    it('creates WebSocket with correct URL', () => {
      // Mock window.location
      vi.stubGlobal('location', {
        protocol: 'http:',
        host: 'localhost:5173',
      });

      useReplayStore.getState().connect('game-123');

      const ws = MockWebSocket.getLatest();
      expect(ws).toBeDefined();
      expect(ws?.url).toBe('ws://localhost:5173/ws/replay/game-123');
    });

    it('uses wss: for https:', () => {
      vi.stubGlobal('location', {
        protocol: 'https:',
        host: 'example.com',
      });

      useReplayStore.getState().connect('game-456');

      const ws = MockWebSocket.getLatest();
      expect(ws?.url).toBe('wss://example.com/ws/replay/game-456');
    });

    it('sets connectionState to connecting', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');

      expect(useReplayStore.getState().connectionState).toBe('connecting');
    });

    it('sets gameId', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');

      expect(useReplayStore.getState().gameId).toBe('game-123');
    });

    it('closes existing connection before opening new one', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-1');
      const firstWs = MockWebSocket.getLatest();

      useReplayStore.getState().connect('game-2');

      expect(firstWs?.readyState).toBe(3); // CLOSED
      expect(MockWebSocket.instances.length).toBe(2);
    });
  });

  describe('_handleOpen', () => {
    it('sets connectionState to connected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      MockWebSocket.getLatest()?.simulateOpen();

      expect(useReplayStore.getState().connectionState).toBe('connected');
    });
  });

  describe('_handleClose', () => {
    it('sets connectionState to disconnected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();
      ws?.close();

      expect(useReplayStore.getState().connectionState).toBe('disconnected');
    });

    it('clears _ws reference', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();
      ws?.close();

      expect(useReplayStore.getState()._ws).toBe(null);
    });
  });

  describe('_handleError', () => {
    it('sets error message', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      MockWebSocket.getLatest()?.simulateError();

      expect(useReplayStore.getState().error).toBe('WebSocket connection error');
    });

    it('sets connectionState to disconnected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      MockWebSocket.getLatest()?.simulateError();

      expect(useReplayStore.getState().connectionState).toBe('disconnected');
    });
  });

  describe('disconnect', () => {
    it('closes WebSocket', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();

      useReplayStore.getState().disconnect();

      expect(ws?.readyState).toBe(3); // CLOSED
    });

    it('resets state to initial', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      MockWebSocket.getLatest()?.simulateOpen();

      useReplayStore.getState().disconnect();

      const state = useReplayStore.getState();
      expect(state.gameId).toBe(null);
      expect(state.connectionState).toBe('disconnected');
      expect(state.pieces).toEqual([]);
    });
  });

  // ============================================
  // Playback Control Tests
  // ============================================

  describe('play', () => {
    it('sends play message when connected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();

      useReplayStore.getState().play();

      expect(ws?.sentMessages).toContainEqual(JSON.stringify({ type: 'play' }));
    });

    it('does not send when disconnected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      // Don't call simulateOpen

      useReplayStore.getState().play();

      expect(ws?.sentMessages).toEqual([]);
    });
  });

  describe('pause', () => {
    it('sends pause message when connected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();

      useReplayStore.getState().pause();

      expect(ws?.sentMessages).toContainEqual(JSON.stringify({ type: 'pause' }));
    });
  });

  describe('seek', () => {
    it('sends seek message with tick when connected', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();

      useReplayStore.getState().seek(500);

      expect(ws?.sentMessages).toContainEqual(JSON.stringify({ type: 'seek', tick: 500 }));
    });
  });

  // ============================================
  // Message Handler Tests
  // ============================================

  describe('_handleMessage', () => {
    beforeEach(() => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });
      useReplayStore.getState().connect('game-123');
      MockWebSocket.getLatest()?.simulateOpen();
    });

    describe('replay_info message', () => {
      it('updates metadata', () => {
        const ws = MockWebSocket.getLatest();
        ws?.simulateMessage({
          type: 'replay_info',
          speed: 'standard',
          board_type: 'standard',
          players: { '1': 'Alice', '2': 'Bob' },
          total_ticks: 1000,
          winner: 1,
          win_reason: 'checkmate',
        });

        const state = useReplayStore.getState();
        expect(state.speed).toBe('standard');
        expect(state.boardType).toBe('standard');
        expect(state.players).toEqual({ '1': 'Alice', '2': 'Bob' });
        expect(state.totalTicks).toBe(1000);
        expect(state.winner).toBe(1);
        expect(state.winReason).toBe('checkmate');
      });
    });

    describe('state message', () => {
      it('updates game state with converted pieces', () => {
        const ws = MockWebSocket.getLatest();
        ws?.simulateMessage({
          type: 'state',
          tick: 100,
          pieces: [
            {
              id: 'p1',
              type: 'P',
              player: 1,
              row: 6,
              col: 4,
              captured: false,
              moving: false,
              on_cooldown: true,
              moved: false,
            },
          ],
          active_moves: [
            {
              piece_id: 'r1',
              path: [[7, 0], [7, 1]],
              start_tick: 90,
              progress: 0.5,
            },
          ],
          cooldowns: [
            {
              piece_id: 'p1',
              remaining_ticks: 50,
            },
          ],
        });

        const state = useReplayStore.getState();
        expect(state.currentTick).toBe(100);

        // Check piece conversion (snake_case -> camelCase)
        expect(state.pieces[0]).toEqual({
          id: 'p1',
          type: 'P',
          player: 1,
          row: 6,
          col: 4,
          captured: false,
          moving: false,
          onCooldown: true,
          moved: false,
        });

        // Check active move conversion
        expect(state.activeMoves[0]).toEqual({
          pieceId: 'r1',
          path: [[7, 0], [7, 1]],
          startTick: 90,
          progress: 0.5,
        });

        // Check cooldown conversion
        expect(state.cooldowns[0]).toEqual({
          pieceId: 'p1',
          remainingTicks: 50,
        });
      });
    });

    describe('playback_status message', () => {
      it('updates playback state', () => {
        const ws = MockWebSocket.getLatest();
        ws?.simulateMessage({
          type: 'playback_status',
          is_playing: true,
          current_tick: 250,
          total_ticks: 1000,
        });

        const state = useReplayStore.getState();
        expect(state.isPlaying).toBe(true);
        expect(state.currentTick).toBe(250);
        expect(state.totalTicks).toBe(1000);
      });
    });

    describe('game_over message', () => {
      it('updates winner and stops playback', () => {
        const ws = MockWebSocket.getLatest();
        ws?.simulateMessage({
          type: 'game_over',
          winner: 2,
          reason: 'resignation',
        });

        const state = useReplayStore.getState();
        expect(state.isPlaying).toBe(false);
        expect(state.winner).toBe(2);
        expect(state.winReason).toBe('resignation');
      });
    });

    describe('error message', () => {
      it('sets error state', () => {
        const ws = MockWebSocket.getLatest();
        ws?.simulateMessage({
          type: 'error',
          message: 'Replay not found',
        });

        expect(useReplayStore.getState().error).toBe('Replay not found');
      });
    });

    describe('invalid message', () => {
      it('handles parse errors gracefully', () => {
        const ws = MockWebSocket.getLatest();
        // Simulate receiving invalid JSON
        if (ws?.onmessage) {
          ws.onmessage({ data: 'not valid json' } as MessageEvent);
        }

        // Should not throw, state should be unchanged
        expect(useReplayStore.getState().error).toBe(null);
      });
    });
  });

  // ============================================
  // Reset Tests
  // ============================================

  describe('reset', () => {
    it('closes WebSocket and resets all state', () => {
      vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' });

      useReplayStore.getState().connect('game-123');
      const ws = MockWebSocket.getLatest();
      ws?.simulateOpen();

      // Set some state
      ws?.simulateMessage({
        type: 'replay_info',
        speed: 'lightning',
        board_type: 'four_player',
        players: { '1': 'A', '2': 'B' },
        total_ticks: 500,
        winner: null,
        win_reason: null,
      });

      useReplayStore.getState().reset();

      const state = useReplayStore.getState();
      expect(ws?.readyState).toBe(3); // CLOSED
      expect(state.gameId).toBe(null);
      expect(state.speed).toBe(null);
      expect(state.boardType).toBe(null);
      expect(state.players).toBe(null);
      expect(state.totalTicks).toBe(0);
      expect(state.pieces).toEqual([]);
    });
  });
});

// ============================================
// Selector Tests
// ============================================

describe('Replay Selectors', () => {
  describe('selectReplayProgress', () => {
    it('returns 0 when totalTicks is 0', () => {
      const state = {
        currentTick: 0,
        totalTicks: 0,
      } as Parameters<typeof selectReplayProgress>[0];

      expect(selectReplayProgress(state)).toBe(0);
    });

    it('returns correct percentage', () => {
      const state = {
        currentTick: 250,
        totalTicks: 1000,
      } as Parameters<typeof selectReplayProgress>[0];

      expect(selectReplayProgress(state)).toBe(25);
    });

    it('returns 100 at completion', () => {
      const state = {
        currentTick: 1000,
        totalTicks: 1000,
      } as Parameters<typeof selectReplayProgress>[0];

      expect(selectReplayProgress(state)).toBe(100);
    });
  });

  describe('selectFormattedTime', () => {
    it('formats 0 ticks as 0:00', () => {
      const state = {
        currentTick: 0,
      } as Parameters<typeof selectFormattedTime>[0];

      expect(selectFormattedTime(state)).toBe('0:00');
    });

    it('formats ticks correctly (10 ticks = 1 second)', () => {
      const state = {
        currentTick: 100, // 10 seconds
      } as Parameters<typeof selectFormattedTime>[0];

      expect(selectFormattedTime(state)).toBe('0:10');
    });

    it('formats minutes correctly', () => {
      const state = {
        currentTick: 650, // 65 seconds = 1:05
      } as Parameters<typeof selectFormattedTime>[0];

      expect(selectFormattedTime(state)).toBe('1:05');
    });

    it('pads seconds with leading zero', () => {
      const state = {
        currentTick: 610, // 61 seconds = 1:01
      } as Parameters<typeof selectFormattedTime>[0];

      expect(selectFormattedTime(state)).toBe('1:01');
    });
  });

  describe('selectFormattedTotalTime', () => {
    it('formats 0 ticks as 0:00', () => {
      const state = {
        totalTicks: 0,
      } as Parameters<typeof selectFormattedTotalTime>[0];

      expect(selectFormattedTotalTime(state)).toBe('0:00');
    });

    it('formats total ticks correctly', () => {
      const state = {
        totalTicks: 6000, // 600 seconds = 10 minutes
      } as Parameters<typeof selectFormattedTotalTime>[0];

      expect(selectFormattedTotalTime(state)).toBe('10:00');
    });

    it('handles long games', () => {
      const state = {
        totalTicks: 36000, // 3600 seconds = 60 minutes
      } as Parameters<typeof selectFormattedTotalTime>[0];

      expect(selectFormattedTotalTime(state)).toBe('60:00');
    });
  });
});

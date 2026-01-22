/**
 * API Client - HTTP client for REST endpoints
 *
 * Uses relative paths because Vite proxy routes /api to the backend.
 */

import type {
  CreateGameRequest,
  CreateGameResponse,
  ApiGameState,
  MakeMoveRequest,
  MakeMoveResponse,
  MarkReadyRequest,
  MarkReadyResponse,
  LegalMovesResponse,
  ApiReplay,
} from './types';

const API_BASE = '/api';

/**
 * Base API error with status code
 */
class ApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string
  ) {
    super(message);
    this.name = 'ApiClientError';
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isBadRequest(): boolean {
    return this.status === 400;
  }

  get isServerError(): boolean {
    return this.status >= 500;
  }
}

/**
 * Error thrown when a game is not found (404)
 */
class GameNotFoundError extends ApiClientError {
  constructor(gameId: string, detail?: string) {
    super(`Game not found: ${gameId}`, 404, detail);
    this.name = 'GameNotFoundError';
  }
}

/**
 * Error thrown when player key is invalid (403)
 */
class InvalidPlayerKeyError extends ApiClientError {
  constructor(detail?: string) {
    super('Invalid player key', 403, detail);
    this.name = 'InvalidPlayerKeyError';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  context?: { gameId?: string }
): Promise<T> {
  const url = `${API_BASE}${path}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail;
    } catch {
      // Ignore JSON parse errors
    }

    // Throw specific error types based on status code
    if (response.status === 404 && context?.gameId) {
      throw new GameNotFoundError(context.gameId, detail);
    }
    if (response.status === 403) {
      throw new InvalidPlayerKeyError(detail);
    }

    throw new ApiClientError(
      `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      detail
    );
  }

  return response.json();
}

/**
 * Create a new game
 */
export async function createGame(req: CreateGameRequest): Promise<CreateGameResponse> {
  return request<CreateGameResponse>('/games', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Get current game state
 */
export async function getGameState(gameId: string): Promise<ApiGameState> {
  return request<ApiGameState>(`/games/${gameId}`, {}, { gameId });
}

/**
 * Make a move
 */
export async function makeMove(
  gameId: string,
  req: MakeMoveRequest
): Promise<MakeMoveResponse> {
  return request<MakeMoveResponse>(
    `/games/${gameId}/move`,
    {
      method: 'POST',
      body: JSON.stringify(req),
    },
    { gameId }
  );
}

/**
 * Mark player as ready to start the game
 */
export async function markReady(
  gameId: string,
  req: MarkReadyRequest
): Promise<MarkReadyResponse> {
  return request<MarkReadyResponse>(
    `/games/${gameId}/ready`,
    {
      method: 'POST',
      body: JSON.stringify(req),
    },
    { gameId }
  );
}

/**
 * Get legal moves for the player
 */
export async function getLegalMoves(
  gameId: string,
  playerKey: string
): Promise<LegalMovesResponse> {
  return request<LegalMovesResponse>(
    `/games/${gameId}/legal-moves?player_key=${encodeURIComponent(playerKey)}`,
    {},
    { gameId }
  );
}

/**
 * Get replay data for a completed game
 */
export async function getReplay(gameId: string): Promise<ApiReplay> {
  return request<ApiReplay>(`/games/${gameId}/replay`, {}, { gameId });
}

export { ApiClientError, GameNotFoundError, InvalidPlayerKeyError };

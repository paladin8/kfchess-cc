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
  ApiReplayListResponse,
  ApiUser,
  RegisterRequest,
  UpdateUserRequest,
  CreateLobbyRequest,
  CreateLobbyResponse,
  JoinLobbyRequest,
  JoinLobbyResponse,
  LobbyListResponse,
  GetLobbyResponse,
  LeaderboardResponse,
  MyRankResponse,
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

/**
 * Error thrown for authentication failures (401)
 */
class AuthenticationError extends ApiClientError {
  constructor(detail?: string) {
    super('Authentication failed', 401, detail);
    this.name = 'AuthenticationError';
  }
}

/**
 * Error thrown when user already exists during registration (400)
 */
class UserAlreadyExistsError extends ApiClientError {
  constructor(detail?: string) {
    super('User already exists', 400, detail);
    this.name = 'UserAlreadyExistsError';
  }
}

/**
 * Error thrown when lobby is not found (404)
 */
class LobbyNotFoundError extends ApiClientError {
  constructor(code: string, detail?: string) {
    super(`Lobby not found: ${code}`, 404, detail);
    this.name = 'LobbyNotFoundError';
  }
}

/**
 * Error thrown when lobby is full (409)
 */
class LobbyFullError extends ApiClientError {
  constructor(detail?: string) {
    super('Lobby is full', 409, detail);
    this.name = 'LobbyFullError';
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

/**
 * List recent replays
 */
export async function listReplays(
  limit: number = 10,
  offset: number = 0
): Promise<ApiReplayListResponse> {
  return request<ApiReplayListResponse>(
    `/replays?limit=${limit}&offset=${offset}`
  );
}

// ============================================
// Auth API Functions
// ============================================

/**
 * Get current authenticated user
 * Returns null if not authenticated (401)
 */
export async function getCurrentUser(): Promise<ApiUser | null> {
  try {
    return await request<ApiUser>('/users/me', {
      credentials: 'include', // Include cookies
    });
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

/**
 * Login with email and password
 */
export async function login(email: string, password: string): Promise<void> {
  const formData = new URLSearchParams();
  formData.append('username', email); // FastAPI-Users uses 'username' for email
  formData.append('password', password);

  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const errorBody = await response.json();
      detail = typeof errorBody.detail === 'string'
        ? errorBody.detail
        : errorBody.detail?.reason || 'Login failed';
    } catch {
      detail = 'Login failed';
    }

    if (response.status === 400) {
      throw new AuthenticationError(detail);
    }
    throw new ApiClientError('Login failed', response.status, detail);
  }
}

/**
 * Logout current user
 */
export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

/**
 * Register a new user with email and password
 */
export async function register(req: RegisterRequest): Promise<ApiUser> {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(req),
    credentials: 'include',
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const errorBody = await response.json();
      detail = typeof errorBody.detail === 'string'
        ? errorBody.detail
        : errorBody.detail?.reason || 'Registration failed';
    } catch {
      detail = 'Registration failed';
    }

    if (response.status === 400 && detail?.includes('REGISTER_USER_ALREADY_EXISTS')) {
      throw new UserAlreadyExistsError('A user with this email already exists');
    }
    throw new ApiClientError('Registration failed', response.status, detail);
  }

  return response.json();
}

/**
 * Update current user's profile
 */
export async function updateUser(req: UpdateUserRequest): Promise<ApiUser> {
  return request<ApiUser>('/users/me', {
    method: 'PATCH',
    body: JSON.stringify(req),
    credentials: 'include',
  });
}

/**
 * Request password reset email
 */
export async function forgotPassword(email: string): Promise<void> {
  await fetch(`${API_BASE}/auth/forgot-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email }),
    credentials: 'include',
  });
  // Always returns 202, even if email doesn't exist (security)
}

/**
 * Reset password with token
 */
export async function resetPassword(token: string, password: string): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/reset-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ token, password }),
    credentials: 'include',
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const errorBody = await response.json();
      detail = typeof errorBody.detail === 'string'
        ? errorBody.detail
        : errorBody.detail?.reason || 'Password reset failed';
    } catch {
      detail = 'Password reset failed';
    }
    throw new ApiClientError('Password reset failed', response.status, detail);
  }
}

/**
 * Get Google OAuth authorization URL
 */
export async function getGoogleAuthUrl(): Promise<string> {
  const response = await request<{ authorization_url: string }>('/auth/google/authorize', {
    credentials: 'include',
  });
  return response.authorization_url;
}

/**
 * Request a new verification email
 * Always returns success (202) for security - doesn't reveal if email exists
 */
export async function requestVerificationEmail(email: string): Promise<void> {
  await fetch(`${API_BASE}/auth/request-verify-token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email }),
    credentials: 'include',
  });
  // Always succeeds (202) - doesn't reveal if email exists
}

// ============================================
// Lobby API Functions
// ============================================

/**
 * Create a new lobby
 */
export async function createLobby(req: CreateLobbyRequest = {}): Promise<CreateLobbyResponse> {
  return request<CreateLobbyResponse>('/lobbies', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * List public lobbies
 */
export async function listLobbies(
  speed?: string,
  playerCount?: number,
  isRanked?: boolean
): Promise<LobbyListResponse> {
  const params = new URLSearchParams();
  if (speed) params.append('speed', speed);
  if (playerCount) params.append('playerCount', String(playerCount));
  if (isRanked !== undefined) params.append('isRanked', String(isRanked));
  const queryString = params.toString();
  return request<LobbyListResponse>(`/lobbies${queryString ? `?${queryString}` : ''}`);
}

/**
 * Get lobby by code
 */
export async function getLobby(code: string): Promise<GetLobbyResponse> {
  try {
    return await request<GetLobbyResponse>(`/lobbies/${code}`);
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 404) {
      throw new LobbyNotFoundError(code, error.detail);
    }
    throw error;
  }
}

/**
 * Join a lobby
 */
export async function joinLobby(
  code: string,
  req: JoinLobbyRequest = {}
): Promise<JoinLobbyResponse> {
  try {
    return await request<JoinLobbyResponse>(`/lobbies/${code}/join`, {
      method: 'POST',
      body: JSON.stringify(req),
    });
  } catch (error) {
    if (error instanceof ApiClientError) {
      if (error.status === 404) {
        throw new LobbyNotFoundError(code, error.detail);
      }
      if (error.status === 409) {
        throw new LobbyFullError(error.detail);
      }
    }
    throw error;
  }
}

/**
 * Delete a lobby (host only)
 */
export async function deleteLobby(code: string, playerKey: string): Promise<void> {
  try {
    await request<{ success: boolean }>(
      `/lobbies/${code}?player_key=${encodeURIComponent(playerKey)}`,
      { method: 'DELETE' }
    );
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 404) {
      throw new LobbyNotFoundError(code, error.detail);
    }
    throw error;
  }
}

// ============================================
// Leaderboard API Functions
// ============================================

/**
 * Get leaderboard for a specific rating mode
 */
export async function getLeaderboard(
  mode: string,
  limit: number = 50,
  offset: number = 0
): Promise<LeaderboardResponse> {
  return request<LeaderboardResponse>(
    `/leaderboard?mode=${encodeURIComponent(mode)}&limit=${limit}&offset=${offset}`
  );
}

/**
 * Get the current user's rank in a specific leaderboard
 * Requires authentication
 */
export async function getMyRank(mode: string): Promise<MyRankResponse> {
  return request<MyRankResponse>(
    `/leaderboard/me?mode=${encodeURIComponent(mode)}`,
    { credentials: 'include' }
  );
}

export {
  ApiClientError,
  GameNotFoundError,
  InvalidPlayerKeyError,
  AuthenticationError,
  UserAlreadyExistsError,
  LobbyNotFoundError,
  LobbyFullError,
};

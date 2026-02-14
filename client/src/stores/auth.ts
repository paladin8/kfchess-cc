import { create } from 'zustand';
import * as api from '../api/client';
import { identify, reset as resetAnalytics } from '../analytics';
import type { ApiUser, ApiRatingStats } from '../api/types';

export interface UserRatingStats {
  rating: number;
  games: number;
  wins: number;
}

export interface User {
  id: number;
  username: string;
  email: string | null;
  pictureUrl: string | null;
  ratings: Record<string, UserRatingStats>;
  isVerified: boolean;
}

// Convert API rating to UserRatingStats, handling both old and new formats
function toRatingStats(value: ApiRatingStats | number): UserRatingStats {
  if (typeof value === 'number') {
    // Old format: just a number rating
    return { rating: value, games: 0, wins: 0 };
  }
  // New format: full stats object
  return {
    rating: value.rating,
    games: value.games,
    wins: value.wins,
  };
}

// Convert API user to store user
function toUser(apiUser: ApiUser): User {
  // Convert ratings to new format
  const ratings: Record<string, UserRatingStats> = {};
  for (const [mode, value] of Object.entries(apiUser.ratings)) {
    ratings[mode] = toRatingStats(value);
  }

  return {
    id: apiUser.id,
    username: apiUser.username,
    email: apiUser.email,
    pictureUrl: apiUser.picture_url,
    ratings,
    isVerified: apiUser.is_verified,
  };
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;

  // Actions
  fetchUser: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, username?: string) => Promise<boolean>;
  logout: () => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  loginWithLichess: () => Promise<void>;
  clearError: () => void;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  error: null,

  fetchUser: async () => {
    set({ isLoading: true, error: null });
    try {
      const apiUser = await api.getCurrentUser();
      if (apiUser) {
        identify(String(apiUser.id), { username: apiUser.username, pictureUrl: apiUser.picture_url });
        set({
          user: toUser(apiUser),
          isAuthenticated: true,
          isLoading: false,
        });
      } else {
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
      }
    } catch {
      // Log sanitized error (not the full object which could contain sensitive data)
      console.error('Failed to fetch user');
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: 'Failed to fetch user',
      });
    }
  },

  login: async (email: string, password: string) => {
    // Guard against concurrent requests
    if (get().isLoading) return;

    set({ isLoading: true, error: null });
    try {
      await api.login(email, password);
      // Fetch user after successful login
      const apiUser = await api.getCurrentUser();
      if (apiUser) {
        identify(String(apiUser.id), { username: apiUser.username, pictureUrl: apiUser.picture_url });
        set({
          user: toUser(apiUser),
          isAuthenticated: true,
          isLoading: false,
        });
      } else {
        set({ isLoading: false, error: 'Login succeeded but failed to fetch user' });
        throw new Error('Failed to fetch user after login');
      }
    } catch (error) {
      let message = 'Login failed';
      if (error instanceof api.AuthenticationError) {
        message = 'Invalid email or password';
      } else if (error instanceof api.ApiClientError && error.status === 429) {
        message = 'Too many login attempts. Please wait a moment and try again.';
      } else if (error instanceof Error && error.message !== 'Failed to fetch user after login') {
        message = error.message;
      }
      set({ isLoading: false, error: message });
      throw error;
    }
  },

  register: async (email: string, password: string, username?: string): Promise<boolean> => {
    // Guard against concurrent requests
    if (get().isLoading) return false;

    set({ isLoading: true, error: null });
    try {
      await api.register({ email, password, username });

      // Try to auto-login after registration
      try {
        await api.login(email, password);
        const apiUser = await api.getCurrentUser();
        if (apiUser) {
          identify(String(apiUser.id), { username: apiUser.username, pictureUrl: apiUser.picture_url });
          set({
            user: toUser(apiUser),
            isAuthenticated: true,
            isLoading: false,
          });
          return true; // Successfully registered and logged in
        }
      } catch {
        // Login failed after successful registration
        // This is unusual but the account was created
        console.error('Auto-login failed after registration');
      }

      // If we get here, registration succeeded but auto-login failed
      // Set success state but inform user they need to log in manually
      set({
        isLoading: false,
        error: 'Account created successfully. Please log in.',
      });
      return false; // Registered but not logged in
    } catch (error) {
      let message = 'Registration failed';
      if (error instanceof api.UserAlreadyExistsError) {
        message = 'A user with this email already exists';
      } else if (error instanceof api.ApiClientError && error.status === 429) {
        message = 'Too many registration attempts. Please wait a moment and try again.';
      } else if (error instanceof api.ApiClientError && error.detail) {
        // Check for username conflict in detail message
        if (error.detail.toLowerCase().includes('username')) {
          message = 'This username is already taken. Please choose another.';
        } else {
          message = error.detail;
        }
      } else if (error instanceof Error) {
        message = error.message;
      }
      set({ isLoading: false, error: message });
      throw error;
    }
  },

  logout: async () => {
    // Guard against concurrent requests
    if (get().isLoading) return;

    set({ isLoading: true, error: null });
    try {
      await api.logout();
    } catch {
      // Log the error but still clear local state
      // The server may have failed but we should still log out locally
      console.error('Server logout may have failed. Local session cleared.');
    } finally {
      resetAnalytics();
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  loginWithGoogle: async () => {
    // Guard against concurrent requests
    if (get().isLoading) return;

    set({ isLoading: true, error: null });
    try {
      const authUrl = await api.getGoogleAuthUrl();
      // Redirect to Google OAuth
      window.location.href = authUrl;
    } catch (error) {
      let message = 'Failed to start Google login';
      if (error instanceof api.ApiClientError && error.status === 429) {
        message = 'Too many login attempts. Please wait a moment and try again.';
      } else if (error instanceof Error) {
        message = error.message;
      }
      set({ isLoading: false, error: message });
      throw error;
    }
  },

  loginWithLichess: async () => {
    // Guard against concurrent requests
    if (get().isLoading) return;

    set({ isLoading: true, error: null });
    try {
      const authUrl = await api.getLichessAuthUrl();
      // Redirect to Lichess OAuth
      window.location.href = authUrl;
    } catch (error) {
      let message = 'Failed to start Lichess login';
      if (error instanceof api.ApiClientError && error.status === 429) {
        message = 'Too many login attempts. Please wait a moment and try again.';
      } else if (error instanceof Error) {
        message = error.message;
      }
      set({ isLoading: false, error: message });
      throw error;
    }
  },

  clearError: () => set({ error: null }),

  setUser: (user) =>
    set({
      user,
      isAuthenticated: user !== null,
      isLoading: false,
    }),
}));

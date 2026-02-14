import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LichessCallback from '../../src/pages/LichessCallback';

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock auth store
const mockFetchUser = vi.fn();
vi.mock('../../src/stores/auth', () => ({
  useAuthStore: (selector: (state: { fetchUser: () => Promise<void> }) => unknown) =>
    selector({ fetchUser: mockFetchUser }),
}));

// Mock fetch
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe('LichessCallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchUser.mockResolvedValue(undefined);
  });

  it('shows loading state initially with valid params', () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });

    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?code=valid_code_1234567890&state=valid_state_1234567890']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Completing login...')).toBeInTheDocument();
  });

  it('shows error when code is missing', () => {
    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?state=valid_state_1234567890']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Missing authorization code or state. Please try logging in again.')).toBeInTheDocument();
  });

  it('shows error when state is missing', () => {
    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?code=valid_code_1234567890']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Missing authorization code or state. Please try logging in again.')).toBeInTheDocument();
  });

  it('shows error for short code', () => {
    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?code=short&state=valid_state_1234567890']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Invalid authorization parameters. Please try logging in again.')).toBeInTheDocument();
  });

  it('shows safe error for access_denied', () => {
    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?error=access_denied']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Access was denied. Please try again.')).toBeInTheDocument();
  });

  it('shows generic error for unknown error codes', () => {
    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?error=unknown_error_type']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Lichess login failed. Please try again.')).toBeInTheDocument();
  });

  it('navigates to home on successful callback', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });

    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?code=valid_code_1234567890&state=valid_state_1234567890']}>
        <LichessCallback />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });

    expect(mockFetchUser).toHaveBeenCalled();
  });

  it('shows error on failed callback response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'some error' }),
    });

    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?code=valid_code_1234567890&state=valid_state_1234567890']}>
        <LichessCallback />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Invalid login request. Please try again.')).toBeInTheDocument();
    });
  });

  it('has back to login button on error', () => {
    render(
      <MemoryRouter initialEntries={['/auth/lichess/callback?error=access_denied']}>
        <LichessCallback />
      </MemoryRouter>
    );

    expect(screen.getByText('Back to Login')).toBeInTheDocument();
  });
});

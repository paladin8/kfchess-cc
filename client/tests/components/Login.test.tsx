import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import Login from '../../src/pages/Login';

// Mock analytics
vi.mock('../../src/analytics', () => ({
  track: vi.fn(),
}));

// Mock auth store
vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({
    login: vi.fn(),
    loginWithGoogle: vi.fn(),
    loginWithLichess: vi.fn(),
    isLoading: false,
    error: null,
    clearError: vi.fn(),
  }),
}));

describe('Login', () => {
  it('renders the Lichess login button', () => {
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    expect(screen.getByText('Continue with Lichess')).toBeInTheDocument();
  });

  it('renders the Google login button', () => {
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    expect(screen.getByText('Continue with Google')).toBeInTheDocument();
  });

  it('renders the email/password form', () => {
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });
});

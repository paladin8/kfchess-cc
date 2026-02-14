import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import Register from '../../src/pages/Register';

// Mock analytics
vi.mock('../../src/analytics', () => ({
  track: vi.fn(),
}));

// Mock auth store
vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({
    register: vi.fn(),
    loginWithGoogle: vi.fn(),
    loginWithLichess: vi.fn(),
    isLoading: false,
    error: null,
    clearError: vi.fn(),
  }),
}));

describe('Register', () => {
  it('renders the Lichess login button', () => {
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    expect(screen.getByText('Continue with Lichess')).toBeInTheDocument();
  });

  it('renders the Google login button', () => {
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    expect(screen.getByText('Continue with Google')).toBeInTheDocument();
  });

  it('renders the registration form', () => {
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByLabelText('Confirm Password')).toBeInTheDocument();
  });
});

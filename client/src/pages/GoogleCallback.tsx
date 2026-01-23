import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '../stores/auth';

// Known Google OAuth error codes
const KNOWN_GOOGLE_ERRORS: Record<string, string> = {
  access_denied: 'Access was denied. Please try again.',
  invalid_scope: 'Invalid permissions requested.',
  invalid_request: 'Invalid request. Please try again.',
  server_error: 'Google server error. Please try again later.',
  temporarily_unavailable: 'Google is temporarily unavailable. Please try again later.',
};

/**
 * Google OAuth callback handler
 *
 * This page handles the redirect from Google OAuth. It:
 * 1. Extracts the authorization code and state from URL params
 * 2. Sends them to the backend to complete the OAuth flow
 * 3. Redirects to home on success or shows error on failure
 */
function GoogleCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fetchUser = useAuthStore((s) => s.fetchUser);

  const [error, setError] = useState<string | null>(null);

  // Prevent double-invoke in React 18 Strict Mode
  const hasInitiated = useRef(false);

  useEffect(() => {
    // Guard against double execution
    if (hasInitiated.current) return;
    hasInitiated.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');

    // Handle Google-side errors with sanitization
    if (errorParam) {
      const safeError = KNOWN_GOOGLE_ERRORS[errorParam] || 'Google login failed. Please try again.';
      setError(safeError);
      return;
    }

    // Validate required parameters exist and are non-empty
    if (!code || !state) {
      setError('Missing authorization code or state. Please try logging in again.');
      return;
    }

    // Basic validation: code and state should be reasonable strings
    if (code.length < 10 || state.length < 10) {
      setError('Invalid authorization parameters. Please try logging in again.');
      return;
    }

    // Send the code and state to the backend callback endpoint
    const completeOAuth = async () => {
      try {
        const response = await fetch(
          `/api/auth/google/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
          {
            method: 'GET',
            credentials: 'include',
          }
        );

        if (!response.ok) {
          let detail = 'Login failed. Please try again.';
          try {
            const errorBody = await response.json();
            // Don't reflect arbitrary error messages - use generic ones
            if (response.status === 400) {
              detail = 'Invalid login request. Please try again.';
            } else if (response.status === 429) {
              detail = 'Too many login attempts. Please wait a moment and try again.';
            } else if (typeof errorBody.detail === 'string' && errorBody.detail.includes('ALREADY_EXISTS')) {
              detail = 'An account with this email already exists. Please login with your password instead.';
            }
          } catch {
            // Ignore JSON parse errors
          }
          setError(detail);
          return;
        }

        // Success! Fetch user and redirect to home
        await fetchUser();
        navigate('/', { replace: true });
      } catch (err) {
        console.error('OAuth callback error:', err);
        setError('Failed to complete login. Please try again.');
      }
    };

    completeOAuth();
  }, [searchParams, fetchUser, navigate]);

  if (error) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Login Failed</h1>
          <div className="auth-error" role="alert" aria-live="polite">{error}</div>
          <button className="btn btn-primary" onClick={() => navigate('/login')}>
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Completing login...</h1>
        <p className="auth-loading" aria-live="polite">Please wait while we complete your login.</p>
      </div>
    </div>
  );
}

export default GoogleCallback;

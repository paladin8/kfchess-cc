import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '../stores/auth';

const VERIFY_TIMEOUT_MS = 30000; // 30 seconds

/**
 * Email verification page
 *
 * Handles the verification token from email links and verifies the user's email.
 */
function Verify() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fetchUser = useAuthStore((s) => s.fetchUser);

  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const [error, setError] = useState<string | null>(null);

  // Prevent double-invoke in React 18 Strict Mode
  const hasInitiated = useRef(false);

  useEffect(() => {
    if (hasInitiated.current) return;
    hasInitiated.current = true;

    const token = searchParams.get('token');

    if (!token) {
      setStatus('error');
      setError('Missing verification token');
      return;
    }

    // Clear token from URL for security (prevents leaking via Referer header)
    setSearchParams({}, { replace: true });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), VERIFY_TIMEOUT_MS);

    const verifyEmail = async () => {
      try {
        const response = await fetch('/api/auth/verify', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ token }),
          credentials: 'include',
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          let detail = 'Verification failed';
          try {
            const errorBody = await response.json();
            if (typeof errorBody.detail === 'string') {
              if (errorBody.detail.includes('VERIFY_USER_BAD_TOKEN')) {
                detail = 'Invalid or expired verification link. Please request a new one.';
              } else if (errorBody.detail.includes('VERIFY_USER_ALREADY_VERIFIED')) {
                // Already verified - treat as success
                setStatus('success');
                await fetchUser();
                setTimeout(() => navigate('/', { replace: true }), 2000);
                return;
              }
            }
          } catch {
            // Ignore JSON parse errors
          }
          setStatus('error');
          setError(detail);
          return;
        }

        // Success - refresh user and redirect
        setStatus('success');
        await fetchUser();
        setTimeout(() => navigate('/', { replace: true }), 2000);
      } catch (err) {
        clearTimeout(timeoutId);
        if (err instanceof Error && err.name === 'AbortError') {
          setStatus('error');
          setError('Verification timed out. Please try again.');
        } else {
          setStatus('error');
          setError('Failed to verify email. Please try again.');
        }
      }
    };

    verifyEmail();

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [searchParams, setSearchParams, fetchUser, navigate]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        {status === 'verifying' && (
          <>
            <h1>Verifying...</h1>
            <p className="auth-loading" aria-live="polite">Please wait while we verify your email.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <h1>Email Verified!</h1>
            <p className="auth-success" aria-live="polite">Your email has been verified. Redirecting to home page...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <h1>Verification Failed</h1>
            <div className="auth-error" role="alert" aria-live="polite">{error}</div>
            <button className="btn btn-primary" onClick={() => navigate('/login')}>
              Go to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default Verify;

import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import * as api from '../api/client';

function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [token, setToken] = useState<string | null>(null);

  // Extract and clear token from URL on mount
  useEffect(() => {
    const urlToken = searchParams.get('token');
    if (urlToken) {
      setToken(urlToken);
      // Clear token from URL for security (prevents leaking via Referer header)
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Still loading token from URL
  if (token === null && searchParams.get('token')) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Loading...</h1>
        </div>
      </div>
    );
  }

  // No token - show error
  if (!token) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Invalid Link</h1>
          <div className="auth-error" role="alert">
            This password reset link is invalid or has expired.
          </div>
          <Link to="/forgot-password" className="btn btn-primary btn-block">
            Request New Link
          </Link>
        </div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate passwords match
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    // Validate password length
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    if (isSubmitting) return;
    setIsSubmitting(true);

    try {
      await api.resetPassword(token, password);
      setSuccess(true);
      // Redirect to login after 3 seconds
      setTimeout(() => navigate('/login', { replace: true }), 3000);
    } catch (err) {
      if (err instanceof api.ApiClientError) {
        if (err.detail?.includes('RESET_PASSWORD_BAD_TOKEN')) {
          setError('This reset link is invalid or has expired. Please request a new one.');
        } else if (err.detail?.includes('RESET_PASSWORD_INVALID_PASSWORD')) {
          setError('Password does not meet requirements. Please use at least 8 characters.');
        } else {
          setError(err.detail || 'Failed to reset password. Please try again.');
        }
      } else {
        setError('Failed to reset password. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Password Reset!</h1>
          <p className="auth-success" aria-live="polite">
            Your password has been reset successfully. Redirecting to login...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Set New Password</h1>

        {error && <div className="auth-error" role="alert">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="password">New Password</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              disabled={isSubmitting}
              aria-describedby="password-hint"
            />
            <span id="password-hint" className="form-hint">At least 8 characters</span>
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm New Password</label>
            <input
              type="password"
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={isSubmitting}>
            {isSubmitting ? 'Resetting...' : 'Reset Password'}
          </button>
        </form>

        <div className="auth-footer">
          <p>
            <Link to="/login">Back to Login</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default ResetPassword;

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../../stores/auth';
import * as api from '../../api/client';

const RESEND_COOLDOWN_MS = 60 * 60 * 1000; // 1 hour
const STORAGE_KEY = 'lastVerificationEmailSent';

function Header() {
  const { user, isAuthenticated, isLoading, logout } = useAuthStore();
  const [verificationSent, setVerificationSent] = useState(false);
  const [sendingVerification, setSendingVerification] = useState(false);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);

  // Check for existing cooldown on mount and when user changes
  useEffect(() => {
    const checkCooldown = () => {
      const lastSent = localStorage.getItem(STORAGE_KEY);
      if (lastSent) {
        const elapsed = Date.now() - parseInt(lastSent, 10);
        if (elapsed < RESEND_COOLDOWN_MS) {
          setCooldownRemaining(Math.ceil((RESEND_COOLDOWN_MS - elapsed) / 60000));
          setVerificationSent(true);
        } else {
          localStorage.removeItem(STORAGE_KEY);
          setCooldownRemaining(0);
          setVerificationSent(false);
        }
      }
    };

    checkCooldown();
    const interval = setInterval(checkCooldown, 60000); // Update every minute
    return () => clearInterval(interval);
  }, [user?.email]);

  const handleLogout = async () => {
    await logout();
  };

  const handleResendVerification = async () => {
    if (!user?.email || sendingVerification || verificationSent) return;

    setSendingVerification(true);
    try {
      await api.requestVerificationEmail(user.email);
      localStorage.setItem(STORAGE_KEY, Date.now().toString());
      setVerificationSent(true);
      setCooldownRemaining(60);
    } finally {
      setSendingVerification(false);
    }
  };

  const showVerificationBanner = isAuthenticated && user && !user.isVerified;

  const getButtonText = () => {
    if (sendingVerification) return 'Sending...';
    if (verificationSent) {
      return cooldownRemaining > 0
        ? `Resend available in ${cooldownRemaining}m`
        : 'Email sent!';
    }
    return 'Resend verification email';
  };

  return (
    <>
      {showVerificationBanner && (
        <div className="verification-banner" role="alert">
          <span>Please verify your email address.</span>
          <button
            className="btn-link"
            onClick={handleResendVerification}
            disabled={sendingVerification || verificationSent}
          >
            {getButtonText()}
          </button>
        </div>
      )}
      <header className="header">
        <div className="header-content">
          <Link to="/" className="logo">
            Kung Fu Chess
          </Link>
          <nav className="nav">
            <Link to="/">Home</Link>
            <Link to="/lobby">Lobby</Link>
            <Link to="/campaign">Campaign</Link>
            <Link to="/replays">Replays</Link>
          </nav>
          <div className="user-menu">
            {isLoading ? (
              <span className="user-loading">...</span>
            ) : isAuthenticated && user ? (
              <>
                <span className="user-name">{user.username}</span>
                <button className="btn btn-link" onClick={handleLogout}>
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login">Login</Link>
                <Link to="/register" className="btn btn-primary btn-sm">
                  Sign Up
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
    </>
  );
}

export default Header;

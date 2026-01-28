import { useState, useEffect, useRef } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useAuthStore } from '../../stores/auth';
import * as api from '../../api/client';
import { staticUrl } from '../../config';

const RESEND_COOLDOWN_MS = 60 * 60 * 1000; // 1 hour
const STORAGE_KEY = 'lastVerificationEmailSent';

function Header() {
  const { user, isAuthenticated, isLoading, logout } = useAuthStore();
  const [verificationSent, setVerificationSent] = useState(false);
  const [sendingVerification, setSendingVerification] = useState(false);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showDropdown]);

  const handleLogout = async () => {
    setShowDropdown(false);
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
            <span className="logo-img"><img src={staticUrl('logo.png')} alt="" /></span>
            <span className="logo-text">Kung Fu Chess</span>
          </Link>
          <div className="header-right">
            <nav className="nav">
              <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-link-active' : ''}>Home</NavLink>
              <NavLink to="/lobbies" className={({ isActive }) => isActive ? 'nav-link-active' : ''}>Lobbies</NavLink>
              <NavLink to="/campaign" className={({ isActive }) => isActive ? 'nav-link-active' : ''}>Campaign</NavLink>
              <NavLink to="/watch" className={({ isActive }) => isActive ? 'nav-link-active' : ''}>Watch</NavLink>
              <a href="https://www.reddit.com/r/kfchess/" target="_blank" rel="noopener noreferrer" className="nav-secondary">Reddit</a>
              <NavLink to="/about" className={({ isActive }) => `nav-secondary ${isActive ? 'nav-link-active' : ''}`}>About</NavLink>
              <NavLink to="/privacy" className={({ isActive }) => `nav-secondary ${isActive ? 'nav-link-active' : ''}`}>Privacy</NavLink>
            </nav>

            {isLoading ? (
              <span className="user-loading">...</span>
            ) : isAuthenticated && user ? (
              /* Authenticated: Profile pic with dropdown containing Profile, Logout, and secondary links */
              <div className="header-menu-wrapper" ref={dropdownRef}>
                <button
                  className="profile-pic-button"
                  onClick={() => setShowDropdown(!showDropdown)}
                  aria-expanded={showDropdown}
                >
                  <div className="profile-pic">
                    <img src={staticUrl('default-profile.jpg')} alt={user.username} />
                  </div>
                </button>
                {showDropdown && (
                  <div className="header-dropdown">
                    <div className="header-dropdown-option">
                      <Link to="/profile" onClick={() => setShowDropdown(false)}>Profile</Link>
                    </div>
                    <div className="header-dropdown-option">
                      <button onClick={handleLogout}>Logout</button>
                    </div>
                    <div className="header-dropdown-secondary">
                      <div className="header-dropdown-divider"></div>
                      <div className="header-dropdown-option">
                        <a href="https://www.reddit.com/r/kfchess/" target="_blank" rel="noopener noreferrer" onClick={() => setShowDropdown(false)}>Reddit</a>
                      </div>
                      <div className="header-dropdown-option">
                        <Link to="/about" onClick={() => setShowDropdown(false)}>About</Link>
                      </div>
                      <div className="header-dropdown-option">
                        <Link to="/privacy" onClick={() => setShowDropdown(false)}>Privacy</Link>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* Unauthenticated: Login link on desktop, hamburger on mobile */
              <>
                <NavLink to="/login" className={({ isActive }) => `login-link ${isActive ? 'nav-link-active' : ''}`}>Login</NavLink>
                <div className="header-menu-wrapper mobile-only" ref={dropdownRef}>
                  <button
                    className="hamburger-button"
                    onClick={() => setShowDropdown(!showDropdown)}
                    aria-expanded={showDropdown}
                    aria-label="Menu"
                  >
                    <span className="hamburger-icon">
                      <span></span>
                      <span></span>
                      <span></span>
                    </span>
                  </button>
                  {showDropdown && (
                    <div className="header-dropdown">
                      <div className="header-dropdown-option">
                        <Link to="/login" onClick={() => setShowDropdown(false)}>Login</Link>
                      </div>
                      <div className="header-dropdown-divider"></div>
                      <div className="header-dropdown-option">
                        <a href="https://www.reddit.com/r/kfchess/" target="_blank" rel="noopener noreferrer" onClick={() => setShowDropdown(false)}>Reddit</a>
                      </div>
                      <div className="header-dropdown-option">
                        <Link to="/about" onClick={() => setShowDropdown(false)}>About</Link>
                      </div>
                      <div className="header-dropdown-option">
                        <Link to="/privacy" onClick={() => setShowDropdown(false)}>Privacy</Link>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </header>
    </>
  );
}

export default Header;

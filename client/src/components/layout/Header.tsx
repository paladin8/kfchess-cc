import { Link } from 'react-router-dom';

function Header() {
  return (
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
          {/* TODO: User menu */}
          <Link to="/login">Login</Link>
        </div>
      </div>
    </header>
  );
}

export default Header;

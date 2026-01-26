import { Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import AuthProvider from './components/AuthProvider';
import Home from './pages/Home';
import { Game } from './pages/Game';
import { Replay } from './pages/Replay';
import { Replays } from './pages/Replays';
import Login from './pages/Login';
import Register from './pages/Register';
import GoogleCallback from './pages/GoogleCallback';
import Verify from './pages/Verify';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Profile from './pages/Profile';
import { Lobby } from './pages/Lobby';
import { Lobbies } from './pages/Lobbies';
import About from './pages/About';
import Privacy from './pages/Privacy';

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="game/:gameId" element={<Game />} />
          <Route path="replay/:replayId" element={<Replay />} />
          <Route path="replays" element={<Replays />} />
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route path="auth/google/callback" element={<GoogleCallback />} />
          <Route path="verify" element={<Verify />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="reset-password" element={<ResetPassword />} />
          <Route path="profile" element={<Profile />} />
          <Route path="lobby/:code" element={<Lobby />} />
          <Route path="lobbies" element={<Lobbies />} />
          <Route path="about" element={<About />} />
          <Route path="privacy" element={<Privacy />} />
          {/* TODO: Add routes */}
          {/* <Route path="campaign" element={<Campaign />} /> */}
          {/* <Route path="profile/:userId" element={<Profile />} /> */}
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;

import { Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Home from './pages/Home';
import { Game } from './pages/Game';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="game/:gameId" element={<Game />} />
        {/* TODO: Add routes */}
        {/* <Route path="lobby" element={<Lobby />} /> */}
        {/* <Route path="campaign" element={<Campaign />} /> */}
        {/* <Route path="replays" element={<Replays />} /> */}
        {/* <Route path="profile/:userId" element={<Profile />} /> */}
        {/* <Route path="login" element={<Login />} /> */}
        {/* <Route path="register" element={<Register />} /> */}
      </Route>
    </Routes>
  );
}

export default App;

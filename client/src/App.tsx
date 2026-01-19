import { Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Home from './pages/Home';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        {/* TODO: Add routes */}
        {/* <Route path="game/:gameId" element={<Game />} /> */}
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

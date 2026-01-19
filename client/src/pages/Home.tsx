function Home() {
  return (
    <div className="home-page">
      <h1>Kung Fu Chess</h1>
      <p className="tagline">Real-time chess where both players move simultaneously</p>

      <div className="play-options">
        <div className="play-option">
          <h2>Quick Play</h2>
          <p>Jump into a game against an AI opponent</p>
          <button className="btn btn-primary">Play vs AI</button>
        </div>

        <div className="play-option">
          <h2>Multiplayer</h2>
          <p>Find an opponent or create a lobby</p>
          <button className="btn btn-secondary">Browse Lobbies</button>
        </div>

        <div className="play-option">
          <h2>Campaign</h2>
          <p>Progress through 64 levels and earn belts</p>
          <button className="btn btn-secondary">Start Campaign</button>
        </div>
      </div>
    </div>
  );
}

export default Home;

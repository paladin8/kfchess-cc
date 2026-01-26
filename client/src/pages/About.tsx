import './About.css';

function About() {
  return (
    <div className="about">
      <div className="about-image">
        <img src="/static/kungfuchess.jpg" alt="Original Kung Fu Chess" />
        <div className="about-image-caption">The original Kung Fu Chess.</div>
      </div>
      <div className="about-text">
        <p>
          Kung Fu Chess is a variant of chess designed for the internet age. It brings the real-time strategy aspect
          of games like StarCraft, Command &amp; Conquer, and Age of Empires to a classic setting. It was originally
          released in 2002 by Shizmoo Games and was popular through the mid-2000s. This is a reinvention of the game
          using modern technology and game design to bring out its potential. I hope you enjoy playing!
        </p>

        <p>
          If you have feedback, please stop by our{' '}
          <a href="https://www.reddit.com/r/kfchess/" target="_blank" rel="noopener noreferrer">reddit</a> or reach out to{' '}
          <a href="mailto:contact@kfchess.com">contact@kfchess.com</a>.
        </p>
      </div>
    </div>
  );
}

export default About;

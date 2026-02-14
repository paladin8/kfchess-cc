import { useEffect } from 'react';
import { track } from '../analytics';
import { staticUrl } from '../config';
import './About.css';

function About() {
  useEffect(() => { track('Visit About Page'); }, []);

  return (
    <div className="about">
      <div className="about-image">
        <img src={staticUrl('kungfuchess.jpg')} alt="Original Kung Fu Chess" />
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
          <a href="https://www.reddit.com/r/kfchess/" target="_blank" rel="noopener noreferrer">reddit</a>, reach out to{' '}
          <a href="mailto:contact@kfchess.com">contact@kfchess.com</a>, or check out the {' '}
          <a href="https://github.com/paladin8/kfchess-cc" target="_blank" rel="noopener noreferrer">code on GitHub</a>.
        </p>
      </div>
    </div>
  );
}

export default About;

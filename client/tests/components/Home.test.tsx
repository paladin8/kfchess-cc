import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import Home from '../../src/pages/Home';

describe('Home', () => {
  it('renders the title', () => {
    render(
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    );

    expect(screen.getByText('Kung Fu Chess')).toBeInTheDocument();
  });

  it('renders play options', () => {
    render(
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    );

    expect(screen.getByText('Quick Play')).toBeInTheDocument();
    expect(screen.getByText('Multiplayer')).toBeInTheDocument();
    expect(screen.getByText('Campaign')).toBeInTheDocument();
  });
});

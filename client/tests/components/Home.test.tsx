import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import Home from '../../src/pages/Home';

describe('Home', () => {
  it('renders the main heading', () => {
    render(
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    );

    expect(screen.getByText('Chess Without Turns')).toBeInTheDocument();
  });

  it('renders play options', () => {
    render(
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    );

    expect(screen.getByText('Campaign')).toBeInTheDocument();
    expect(screen.getByText('Play vs AI')).toBeInTheDocument();
    expect(screen.getByText('Play vs Friend')).toBeInTheDocument();
  });
});

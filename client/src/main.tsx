import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles/index.css';

// Note: StrictMode disabled due to conflicts with PixiJS WebGL context management.
// PixiJS doesn't handle the double-mount/unmount pattern well.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);

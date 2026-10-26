
import { createRoot } from 'react-dom/client';
import App from './app/App.tsx';
import PaymentCheckoutPage from './app/components/PaymentCheckoutPage';
import { AppErrorBoundary } from './app/components/AppErrorBoundary.tsx';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <AppErrorBoundary>
    {window.location.pathname.replace(/\/$/, '').endsWith('/checkout') ? <PaymentCheckoutPage /> : <App />}
  </AppErrorBoundary>
);
  

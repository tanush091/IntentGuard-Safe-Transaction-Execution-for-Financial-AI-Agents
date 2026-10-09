import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource/outfit/300.css';
import '@fontsource/outfit/400.css';
import '@fontsource/outfit/500.css';
import '@fontsource/outfit/600.css';
import '@fontsource/outfit/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/jetbrains-mono/700.css';
import './styles/tokens.css';
import './styles/app.css';
import App from './App.jsx';
import { AuthProvider } from './hooks/useAuth.jsx';
import { ToastProvider } from './components/ui.jsx';
import { ConsoleProvider } from './components/Widgets.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ToastProvider>
      <AuthProvider>
        <ConsoleProvider>
          <App />
        </ConsoleProvider>
      </AuthProvider>
    </ToastProvider>
  </React.StrictMode>,
);

import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Shield, LayoutDashboard, ClipboardList, Gavel, ScrollText, FlaskConical, Moon, Sun } from 'lucide-react';
import api from './services/api.js';
import { Spinner, ToastProvider, usePoll } from './components/ui.jsx';
import Overview from './views/Overview.jsx';
import Intents from './views/Intents.jsx';
import Reviews from './views/Reviews.jsx';
import Audit from './views/Audit.jsx';
// recharts is only needed on the Experiments tab; load it on demand.
const Experiments = lazy(() => import('./views/Experiments.jsx'));

const TABS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'intents', label: 'Intents', icon: ClipboardList },
  { id: 'reviews', label: 'Reviews', icon: Gavel },
  { id: 'audit', label: 'Audit', icon: ScrollText },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
];

function readHash() {
  const h = (window.location.hash || '').replace(/^#\/?/, '');
  return TABS.some((t) => t.id === h) ? h : 'overview';
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('ig-theme') || '';
    } catch {
      return '';
    }
  });
  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme);
    else document.documentElement.removeAttribute('data-theme');
    try {
      if (theme) localStorage.setItem('ig-theme', theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);
  const isDark =
    theme === 'dark' || (!theme && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  return [isDark, () => setTheme(isDark ? 'light' : 'dark')];
}

function Shell() {
  const [tab, setTab] = useState(readHash);
  const [focusIntent, setFocusIntent] = useState(null);
  const [isDark, toggleTheme] = useTheme();
  // Badge counts on the nav come from live metrics.
  const { data: m, error: mErr } = usePoll(() => api.metrics(), [], 4000);

  useEffect(() => {
    const onHash = () => setTab(readHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const goto = (id) => {
    window.location.hash = `/${id}`;
    setTab(id);
  };
  const openIntent = (id) => {
    setFocusIntent(id);
    goto('intents');
  };

  const navCount = {
    reviews: m?.open_reviews?.count,
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Shield size={22} />
          <div>
            <div className="brand-name">IntentGuard</div>
            <div className="brand-sub">Intent-consistent payments for AI agents</div>
          </div>
        </div>
        <nav className="nav">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`nav-btn ${tab === id ? 'active' : ''}`} onClick={() => goto(id)}>
              <Icon size={16} />
              <span>{label}</span>
              {navCount[id] ? <span className="nav-count">{navCount[id]}</span> : null}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <span className={`conn ${mErr ? 'down' : m ? 'up' : ''}`} title={mErr ? mErr.message : 'Gateway reachable'}>
            <i /> {mErr ? 'Gateway unreachable' : m ? 'Live' : 'Connecting…'}
          </span>
          <button className="icon-btn" onClick={toggleTheme} title="Toggle theme" aria-label="Toggle theme">
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>
      <main className="main">
        {tab === 'overview' && <Overview goto={goto} />}
        {tab === 'intents' && <Intents focus={focusIntent} onFocusConsumed={() => setFocusIntent(null)} />}
        {tab === 'reviews' && <Reviews openIntent={openIntent} />}
        {tab === 'audit' && <Audit openIntent={openIntent} />}
        {tab === 'experiments' && (
          <Suspense fallback={<Spinner label="Loading…" />}>
            <Experiments />
          </Suspense>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

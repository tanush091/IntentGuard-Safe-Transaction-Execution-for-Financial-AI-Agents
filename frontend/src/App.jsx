import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import {
  ClipboardList, FlaskConical, Gavel, LayoutDashboard, LogOut, Moon, ScrollText, Settings, ShieldCheck, Sun,
  TriangleAlert, Workflow,
} from 'lucide-react';
import { useAuth } from './hooks/useAuth.jsx';
import { usePoll } from './hooks/usePoll.js';
import api from './api/endpoints.js';
import { Spinner } from './components/ui.jsx';
import { AuditBadge } from './components/Widgets.jsx';
import { can } from './domain.js';
import Login from './pages/Login.jsx';
import Overview from './pages/Overview.jsx';
import Intents from './pages/Intents.jsx';
import IntentDetail from './pages/IntentDetail.jsx';

const Exceptions = lazy(() => import('./pages/Exceptions.jsx'));
const Reviews = lazy(() => import('./pages/Reviews.jsx'));
const Reconciliation = lazy(() => import('./pages/Reconciliation.jsx'));
const Audit = lazy(() => import('./pages/Audit.jsx'));
const Experiments = lazy(() => import('./pages/Experiments.jsx'));
const Admin = lazy(() => import('./pages/Admin.jsx'));

const PAGES = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, cap: 'metrics:read', component: Overview },
  { id: 'intents', label: 'Intents', icon: ClipboardList, cap: 'intents:read', component: Intents },
  { id: 'exceptions', label: 'Exceptions', icon: TriangleAlert, cap: 'exceptions:read', component: Exceptions },
  { id: 'reviews', label: 'Review queue', icon: Gavel, cap: 'reviews:read', component: Reviews },
  { id: 'reconciliation', label: 'Reconciliation', icon: Workflow, cap: 'reconciliation:read', component: Reconciliation },
  { id: 'audit', label: 'Audit', icon: ScrollText, cap: 'audit:read', component: Audit },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical, cap: 'metrics:read', component: Experiments },
  { id: 'admin', label: 'Admin', icon: Settings, cap: 'admin', component: Admin },
];

function parseHash() {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  return { page: parts[0] || 'overview', id: parts[1] ? decodeURIComponent(parts[1]) : null };
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
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      if (theme) localStorage.setItem('ig-theme', theme);
    } catch { /* preference only */ }
  }, [theme]);
  const dark = theme ? theme === 'dark' : !window.matchMedia?.('(prefers-color-scheme: light)').matches;
  return { dark, toggle: () => setTheme(dark ? 'light' : 'dark') };
}

function Counts({ user }) {
  const ex = usePoll(() => (can(user, 'exceptions:read') ? api.listExceptions({ limit: 200 }) : Promise.resolve(null)), [], 10000);
  const rv = usePoll(() => (can(user, 'reviews:read') ? api.listReviews({ status: 'OPEN', limit: 200 }) : Promise.resolve(null)), [], 10000);
  return { exceptions: ex.data?.items.length || 0, reviews: rv.data?.items.length || 0 };
}

function Shell({ user, logout }) {
  const [route, setRoute] = useState(parseHash);
  const { dark, toggle } = useTheme();
  const counts = Counts({ user });
  const { data: ready } = usePoll(() => api.ready().catch(() => null), [], 30000);
  useEffect(() => {
    const h = () => setRoute(parseHash());
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  const navigate = useCallback((path) => { window.location.hash = path; }, []);
  const visible = PAGES.filter((p) => can(user, p.cap));
  const page = visible.find((p) => p.id === route.page) || visible[0];
  const Page = route.page === 'intents' && route.id ? IntentDetail : page?.component;
  const badge = { exceptions: counts.exceptions, reviews: counts.reviews };
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand"><ShieldCheck className="brand-mark" size={22} /><span>IntentGuard<small>Recovery</small></span></div>
        <div className="nav">
          {visible.map((p) => (
            <a key={p.id} href={`#/${p.id}`} aria-current={page?.id === p.id ? 'page' : undefined} title={p.label}>
              <p.icon size={18} aria-hidden="true" /><span>{p.label}</span>
              {badge[p.id] > 0 && <span className="count" aria-label={`${badge[p.id]} open`}>{badge[p.id]}</span>}
            </a>
          ))}
        </div>
        <div className="sidebar-foot">
          <span className="hide-narrow muted">{user.name}</span>
          <span className="hide-narrow mono muted">{user.role}</span>
          <button className="btn btn-ghost btn-sm" onClick={logout}><LogOut size={14} /><span className="hide-narrow">Sign out</span></button>
        </div>
      </nav>
      <div className="main">
        <header className="topbar">
          <span className="sim-banner">Simulated provider · no real money</span>
          <div className="row">
            <AuditBadge user={user} />
            {ready && ready.status !== 'ready' && <span className="pill tone-rose">provider: {ready.provider}</span>}
            <button className="icon-btn" onClick={toggle} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
          </div>
        </header>
        <main className="content">
          <Suspense fallback={<Spinner label="Loading…" />}>
            {Page ? <Page id={route.id} user={user} navigate={navigate} /> : <div className="muted">No page available for your role.</div>}
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const { user, ready, logout } = useAuth();
  if (!ready) return <div className="login-wrap"><Spinner label="Starting…" /></div>;
  return user ? <Shell user={user} logout={logout} /> : <Login />;
}

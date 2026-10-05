import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, Loader2 } from 'lucide-react';
import { toneOf } from '../util.js';

// ------------------------------------------------------------------ toasts

const ToastCtx = createContext({ push: () => {} });

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (message, tone = 'info', ttl = 6000) => {
      const id = ++idRef.current;
      setToasts((t) => [...t.slice(-4), { id, message: String(message), tone }]);
      if (ttl) setTimeout(() => dismiss(id), ttl);
    },
    [dismiss],
  );

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast tone-${t.tone}`}>
            {t.tone === 'bad' ? <AlertTriangle size={16} /> : t.tone === 'good' ? <CheckCircle2 size={16} /> : <Info size={16} />}
            <span>{t.message}</span>
            <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

// ------------------------------------------------------------------ polling

/**
 * Load data with `fn` immediately and every `intervalMs` (0 = no polling).
 * Returns { data, error, loading, reload }. Errors are kept inline, never thrown.
 */
export function usePoll(fn, deps = [], intervalMs = 0) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const seq = useRef(0);

  const reload = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const d = await fnRef.current();
      if (mine === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError(e);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    reload();
    if (!intervalMs) return undefined;
    const t = setInterval(reload, intervalMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs]);

  return { data, error, loading, reload };
}

// ------------------------------------------------------------------ primitives

export function Badge({ value, tone, children, title }) {
  const t = tone || toneOf(value);
  return (
    <span className={`badge tone-${t}`} title={title}>
      {children ?? value ?? '—'}
    </span>
  );
}

export function Card({ title, icon, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <h3>
            {icon}
            {title}
          </h3>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function InlineError({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="inline-error">
      <AlertTriangle size={16} />
      <span>{error.message || String(error)}</span>
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ icon, title, children }) {
  return (
    <div className="empty">
      {icon}
      <strong>{title}</strong>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

export function Spinner({ label }) {
  return (
    <span className="spinner">
      <Loader2 size={16} className="spin" />
      {label}
    </span>
  );
}

export function Button({ busy, children, className = '', ...rest }) {
  return (
    <button className={`btn ${className}`} disabled={busy || rest.disabled} {...rest}>
      {busy ? <Loader2 size={14} className="spin" /> : null}
      {children}
    </button>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

/** Runs an async action, tracks busy state and reports failures as toasts. */
export function useAction() {
  const { push } = useToast();
  const [busy, setBusy] = useState(null);
  const run = useCallback(
    async (name, fn, successMsg) => {
      setBusy(name);
      try {
        const r = await fn();
        if (successMsg) push(typeof successMsg === 'function' ? successMsg(r) : successMsg, 'good');
        return r;
      } catch (e) {
        push(e.message || String(e), 'bad', 9000);
        return undefined;
      } finally {
        setBusy(null);
      }
    },
    [push],
  );
  return { busy, run };
}

/** Table of {key: count} maps, e.g. intents_by_state. */
export function CountList({ data, emptyText = 'None yet' }) {
  const entries = Object.entries(data || {}).sort((a, b) => (Number(b[1]) || 0) - (Number(a[1]) || 0));
  if (!entries.length) return <div className="muted small">{emptyText}</div>;
  const max = Math.max(...entries.map(([, v]) => Number(v) || 0), 1);
  return (
    <ul className="count-list">
      {entries.map(([k, v]) => (
        <li key={k}>
          <Badge value={k} />
          <div className="bar-track">
            <div className={`bar-fill tone-${toneOf(k)}`} style={{ width: `${((Number(v) || 0) / max) * 100}%` }} />
          </div>
          <span className="mono count">{v}</span>
        </li>
      ))}
    </ul>
  );
}

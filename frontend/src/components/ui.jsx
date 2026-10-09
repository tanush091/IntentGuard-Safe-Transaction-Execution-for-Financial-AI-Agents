import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react';

// ------------------------------------------------------------------ toasts

const ToastCtx = createContext({ push: () => {} });

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback((message, tone = 'info', ttl = 6000) => {
    const id = ++idRef.current;
    setToasts((t) => [...t.slice(-4), { id, message: String(message), tone }]);
    if (ttl) setTimeout(() => dismiss(id), ttl);
  }, [dismiss]);
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            {t.tone === 'bad' ? <AlertTriangle size={16} /> : t.tone === 'good' ? <CheckCircle2 size={16} /> : <Info size={16} />}
            <span>{t.message}</span>
            <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss"><X size={14} /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

/** Runs an async action, tracks which one is busy, and reports failures as toasts. */
export function useAction() {
  const { push } = useToast();
  const [busy, setBusy] = useState(null);
  const run = useCallback(async (name, fn, successMsg) => {
    setBusy(name);
    try {
      const r = await fn();
      if (successMsg) push(typeof successMsg === 'function' ? successMsg(r) : successMsg, 'good');
      return r;
    } catch (e) {
      push(e.code && e.code !== 'ERROR' ? `${e.code}: ${e.message}` : e.message || String(e), 'bad', 9000);
      return undefined;
    } finally {
      setBusy(null);
    }
  }, [push]);
  return { busy, run };
}

// ------------------------------------------------------------- primitives

export function Card({ title, icon, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <h3>{icon}{title}</h3>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
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

export function InlineError({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="inline-error" role="alert">
      <AlertTriangle size={16} />
      <span>{error.code && error.code !== 'ERROR' ? `${error.code}: ` : ''}{error.message || String(error)}</span>
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Empty({ icon, title, children }) {
  return (
    <div className="empty">
      {icon}
      <strong>{title}</strong>
      {children && <div className="muted small">{children}</div>}
    </div>
  );
}

export function Spinner({ label }) {
  return <span className="spinner"><Loader2 size={16} className="spin" />{label}</span>;
}

function useEscape(onClose) {
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
}

export function Dialog({ title, onClose, children, footer }) {
  useEscape(onClose);
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button></div>
        <div className="dialog-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Drawer({ title, onClose, children }) {
  useEscape(onClose);
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog-head"><h3 className="mono">{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button></div>
        <div className="dialog-body">{children}</div>
      </aside>
    </div>
  );
}

export function Json({ value }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

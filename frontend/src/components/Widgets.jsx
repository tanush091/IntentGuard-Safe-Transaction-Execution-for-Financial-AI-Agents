import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { ACTION_TEXT, can } from '../domain.js';
import { Button, Card, InlineError, useAction } from './ui.jsx';
import { TonePill } from './StatusPill.jsx';

// --------------------------------------------------------------- metric card

export function MetricCard({ label, value, sub, tone = '', icon }) {
  return (
    <div className={`card metric ${tone ? `tone-${tone}` : ''}`}>
      <span className="label">{icon}{label}</span>
      <span className="value">{value ?? '—'}</span>
      {sub && <span className="sub">{sub}</span>}
    </div>
  );
}

// ------------------------------------------------------------ audit badge

/** "Chain verified ✓ (N entries)" or "Chain broken at #K" (DESIGN 5.9). Reviewers and admins only. */
export function AuditBadge({ user, intervalMs = 30000 }) {
  const allowed = can(user, 'audit:verify');
  const { data, error } = usePoll(() => (allowed ? api.verifyAudit() : Promise.resolve(null)), [allowed], intervalMs);
  if (!allowed || error || !data) return null;
  return data.valid
    ? <TonePill tone="emerald" title="Hash chain recomputed"><ShieldCheck size={12} /> Chain verified ✓ ({data.entries_checked} entries)</TonePill>
    : <TonePill tone="rose" title={`chain ${data.first_break?.chain_id}`}><ShieldAlert size={12} /> Chain broken at #{data.first_break?.seq}</TonePill>;
}

// ------------------------------------------------------------ live console

const ConsoleCtx = createContext({ log: () => {}, local: [] });

export function ConsoleProvider({ children }) {
  const [local, setLocal] = useState([]);
  const log = useCallback((level, text) => {
    setLocal((l) => [...l.slice(-200), { id: `${Date.now()}-${Math.random()}`, ts: new Date().toISOString(), level, text }]);
  }, []);
  return <ConsoleCtx.Provider value={{ log, local }}>{children}</ConsoleCtx.Provider>;
}

export function useConsole() {
  return useContext(ConsoleCtx);
}

function levelOf(kind, payload) {
  if (kind === 'reconcile.lookup_failed' || kind.startsWith('auth.login_failed')) return 'error';
  if (kind === 'review.opened' || kind === 'attempt.absence_assumption_violated') return 'warn';
  if (kind === 'effect.reversal_verified' || (kind === 'intent.state' && payload?.to === 'COMPLETED')) return 'verified';
  return 'info';
}

function describe(e) {
  const p = e.payload || {};
  if (e.kind === 'intent.state') return `${e.intent_id}: ${p.from} → ${p.to}`;
  if (e.kind === 'proposal.decided') return `${e.intent_id}: proposal ${p.decision}${p.findings?.length ? ` (${p.findings.map((f) => f.check).join(', ')})` : ''}`;
  if (e.kind === 'effect.observed') return `${e.intent_id}: ${p.classification} ${p.provider_ref} ${p.status}`;
  return `${e.intent_id || 'system'}: ${e.kind}`;
}

/** Live console (DESIGN 5.8): monospace, autoscroll with pause on scroll-up, level colours. */
export function LiveConsole({ user }) {
  const { local } = useConsole();
  const allowed = can(user, 'audit:read');
  const { data } = usePoll(() => (allowed ? api.listAudit({ limit: 60 }) : Promise.resolve(null)), [allowed], 3000);
  const box = useRef(null);
  const stick = useRef(true);
  const audit = (data?.items || []).slice().reverse().map((e) => ({
    id: `a${e.seq}`, ts: e.ts, level: levelOf(e.kind, e.payload), text: describe(e),
  }));
  const lines = [...audit, ...local.map((l) => ({ ...l, level: l.level || 'step' }))]
    .sort((a, b) => String(a.ts).localeCompare(String(b.ts))).slice(-120);
  useEffect(() => {
    if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines.length]);
  return (
    <div
      className="console" ref={box} role="log" aria-live="off" tabIndex={0}
      onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24; }}
    >
      {lines.length === 0 && <div className="muted">Waiting for events…</div>}
      {lines.map((l) => (
        <div key={l.id} className={`line ${l.level}`}>
          <span>{new Date(l.ts).toLocaleTimeString()}</span><span>{l.text}</span>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------- investigator panel

/**
 * AI investigator panel (DESIGN 5.6): violet border, "AI-generated · advisory". Shows the
 * classification, summary, evidence refs, recommended action and the policy verdict. Apply is
 * disabled unless the deterministic policy gate permits the action.
 */
export function InvestigatorPanel({ intentId, investigation, user, onChange }) {
  const { busy, run } = useAction();
  const inv = investigation;
  const canApply = inv && inv.valid_output && inv.policy_verdict?.permitted && !inv.applied && can(user, 'investigations:apply');
  return (
    <Card className="ai" title="AI-generated · advisory" icon={<Sparkles size={16} color="var(--accent-violet)" />}
      actions={can(user, 'exceptions:investigate') && (
        <Button busy={busy === 'inv'} onClick={async () => { await run('inv', () => api.investigate(intentId), 'Investigation finished'); onChange?.(); }}>
          {inv ? 'Investigate again' : 'Investigate'}
        </Button>
      )}>
      {!inv ? <div className="muted small">No investigation yet. The investigator only classifies and recommends; a deterministic policy decides what may run.</div> : (
        <div className="stack">
          <div className="row">
            <TonePill tone="violet">{inv.classification}</TonePill>
            <span className="small muted">model {inv.model} · {inv.tokens?.in ?? 0}/{inv.tokens?.out ?? 0} tokens</span>
          </div>
          <p style={{ margin: 0 }}>{inv.summary}</p>
          <div className="row small">Evidence: {inv.evidence_refs?.map((r) => <span key={r} className="chip">{r}</span>)}</div>
          <div className="small"><strong>Recommended:</strong> <span className="mono">{inv.recommended_action}</span> — {ACTION_TEXT[inv.recommended_action]}</div>
          <div className={`callout ${inv.policy_verdict?.permitted ? 'ok' : 'blocked'}`}>
            Policy verdict: <strong>{inv.policy_verdict?.permitted ? 'permitted' : 'not permitted'}</strong>
            {' '}(<span className="mono">{inv.policy_verdict?.rule}</span>)
          </div>
          {inv.applied && <div className="small muted">Applied {inv.applied.outcome} by {inv.applied.by}</div>}
          <div className="row">
            <Button className="btn-primary" disabled={!canApply} busy={busy === 'apply'}
              title={canApply ? 'Run this action through the engine' : 'The policy gate does not permit this action'}
              onClick={async () => { await run('apply', () => api.applyInvestigation(inv.investigation_id), (r) => `Applied: intent is ${r.intent_state}`); onChange?.(); }}>
              Apply
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

export function ErrorCard({ error, onRetry }) {
  return error ? <InlineError error={error} onRetry={onRetry} /> : null;
}

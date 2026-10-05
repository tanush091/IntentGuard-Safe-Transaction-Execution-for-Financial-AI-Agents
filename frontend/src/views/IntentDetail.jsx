import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft, Ban, Bot, FileText, Gavel, Link2, RefreshCw, Send, ScrollText, Zap, Activity,
} from 'lucide-react';
import api from '../services/api.js';
import { Badge, Button, Card, Field, InlineError, Spinner, useAction, usePoll } from '../components/ui.jsx';
import { amountOf, minorToMajorString, money, relTime, short, ts } from '../util.js';

const KINDS = {
  proposal: { label: 'Proposal', icon: <Send size={14} /> },
  attempt: { label: 'Attempt', icon: <Zap size={14} /> },
  effect: { label: 'Effect', icon: <Activity size={14} /> },
  review: { label: 'Review', icon: <Gavel size={14} /> },
  audit: { label: 'Audit', icon: <ScrollText size={14} /> },
};
const KIND_ORDER = ['proposal', 'attempt', 'effect', 'review', 'audit'];

function Findings({ findings }) {
  if (!Array.isArray(findings) || findings.length === 0) return null;
  return (
    <ul className="findings">
      {findings.map((f, i) => (
        <li key={i}>
          {f?.decision && <Badge value={f.decision} />}
          <span className="mono small">{f?.check ?? 'check'}</span>
          <span>{f?.detail ?? (typeof f === 'string' ? f : JSON.stringify(f))}</span>
        </li>
      ))}
    </ul>
  );
}

function KV({ items }) {
  const rows = items.filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!rows.length) return null;
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt>{k}</dt>
          <dd className="mono">{v}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function buildTimeline(t) {
  if (!t) return [];
  const ev = [];
  (t.proposals || []).forEach((p) =>
    ev.push({
      kind: 'proposal', at: p.created_at, key: `p${p.id}`,
      title: <>Proposal #{p.id} from <span className="mono">{p.agent_id}</span></>,
      badges: [p.decision],
      body: (
        <>
          <KV items={[
            ['operation', p.operation], ['order', p.order_id], ['customer', p.customer_id],
            ['amount', amountOf(p)], ['request', p.request_id], ['rationale', p.rationale],
          ]} />
          <Findings findings={p.reasons} />
        </>
      ),
    }),
  );
  (t.attempts || []).forEach((a) =>
    ev.push({
      kind: 'attempt', at: a.created_at, key: `a${a.id}`,
      title: <>Attempt #{a.attempt_no} → provider</>,
      badges: [a.status],
      body: (
        <>
          <KV items={[
            ['attempt id', a.id], ['idempotency key', a.idempotency_key], ['provider ref', a.provider_ref],
            ['operation', a.operation], ['order', a.order_id], ['amount', amountOf(a)],
            ['updated', a.updated_at && a.updated_at !== a.created_at ? ts(a.updated_at) : null],
          ]} />
          {a.error && <div className="error-text">{a.error}</div>}
        </>
      ),
    }),
  );
  (t.effects || []).forEach((e) =>
    ev.push({
      kind: 'effect', at: e.observed_at, key: `e${e.id}`,
      title: <>Provider transaction <span className="mono">{e.provider_ref}</span></>,
      badges: [e.classification, e.provider_status, e.remediated ? 'REMEDIATED' : null],
      body: (
        <KV items={[
          ['operation', e.operation], ['order', e.order_id], ['customer', e.customer_id], ['amount', amountOf(e)],
          ['attempt', e.attempt_id], ['counts toward intent', e.counts_toward_intent ? 'yes' : 'no'],
          ['cancel tries', e.cancel_tries || null], ['note', e.note],
        ]} />
      ),
    }),
  );
  (t.reviews || []).forEach((r) => {
    ev.push({
      kind: 'review', at: r.created_at, key: `r${r.id}`,
      title: <>Review case #{r.id} opened: {r.reason}</>,
      badges: [r.status],
      body: (
        <>
          <KV items={[['discrepancy', money(r.discrepancy_minor, t.intent?.currency)]]} />
          {r.details && Object.keys(r.details).length > 0 && <pre className="json">{JSON.stringify(r.details, null, 2)}</pre>}
        </>
      ),
    });
    if (r.resolved_at) {
      ev.push({
        kind: 'review', at: r.resolved_at, key: `r${r.id}-res`,
        title: <>Review case #{r.id} resolved by <span className="mono">{r.resolved_by}</span></>,
        badges: [r.resolution],
        body: r.notes ? <div className="muted">{r.notes}</div> : null,
      });
    }
  });
  (t.audit || []).forEach((a) =>
    ev.push({
      kind: 'audit', at: a.created_at, key: `au${a.seq}`, seq: a.seq,
      title: <><span className="mono">{a.kind}</span> by <span className="mono">{a.actor}</span></>,
      badges: [],
      body: (
        <>
          {a.payload && Object.keys(a.payload).length > 0 && <pre className="json">{JSON.stringify(a.payload, null, 2)}</pre>}
          <div className="mono tiny muted" title={a.hash}>seq {a.seq} · hash {short(a.hash, 16)} · prev {short(a.prev_hash, 16)}</div>
        </>
      ),
    }),
  );
  return ev.sort(
    (x, y) =>
      (Number(x.at) || 0) - (Number(y.at) || 0) ||
      KIND_ORDER.indexOf(x.kind) - KIND_ORDER.indexOf(y.kind) ||
      (x.seq ?? 0) - (y.seq ?? 0),
  );
}

function ResultBox({ result }) {
  if (!result) return null;
  return (
    <div className="result-box">
      <div className="row">
        <strong>Decision</strong> <Badge value={result.decision} />
        <span className="muted">intent now</span> <Badge value={result.intent_state} />
      </div>
      <KV items={[['attempt', result.attempt_id], ['provider ref', result.provider_ref], ['proposal id', result.proposal_id]]} />
      <Findings findings={result.findings} />
    </div>
  );
}

function ProposalForm({ intent, onDone }) {
  const { busy, run } = useAction();
  const blank = useMemo(
    () => ({
      agent_id: 'dashboard-agent',
      operation: intent.operation,
      customer_id: intent.customer_id,
      order_id: intent.order_id,
      amount: minorToMajorString(intent.amount_minor),
      currency: intent.currency,
      rationale: '',
    }),
    [intent.id], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const [f, setF] = useState(blank);
  const [result, setResult] = useState(null);
  useEffect(() => setF(blank), [blank]);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    const r = await run('propose', () => api.submitProposal(intent.id, { ...f, amount: String(f.amount).trim() }));
    if (r) {
      setResult(r);
      onDone();
    }
  };

  const tampered = ['operation', 'customer_id', 'order_id', 'amount', 'currency'].filter(
    (k) => String(f[k]).trim() !== String(blank[k]),
  );

  return (
    <form onSubmit={submit} className="stack-sm">
      <p className="muted small">
        Pre-filled from the authorized intent. Change the amount, order or customer to see the gateway reject a
        mismatched proposal.
      </p>
      <div className="form-grid compact">
        <Field label="Agent id"><input value={f.agent_id} onChange={set('agent_id')} /></Field>
        <Field label="Operation">
          <select value={f.operation} onChange={set('operation')}>
            <option value="REFUND">REFUND</option>
            <option value="PAYMENT_AUTHORIZATION">PAYMENT_AUTHORIZATION</option>
          </select>
        </Field>
        <Field label="Order"><input value={f.order_id} onChange={set('order_id')} /></Field>
        <Field label="Customer"><input value={f.customer_id} onChange={set('customer_id')} /></Field>
        <Field label="Amount"><input value={f.amount} onChange={set('amount')} inputMode="decimal" /></Field>
        <Field label="Currency"><input value={f.currency} onChange={set('currency')} maxLength={3} /></Field>
        <Field label="Rationale"><input value={f.rationale} onChange={set('rationale')} /></Field>
      </div>
      <div className="row">
        <Button className="btn-primary" type="submit" busy={busy === 'propose'}>
          <Send size={14} /> Submit proposal
        </Button>
        {tampered.length > 0 && (
          <>
            <span className="badge tone-warn">differs from intent: {tampered.join(', ')}</span>
            <button type="button" className="btn btn-sm" onClick={() => setF(blank)}>Reset</button>
          </>
        )}
      </div>
      <ResultBox result={result} />
    </form>
  );
}

function AgentForm({ intent, onDone }) {
  const { busy, run } = useAction();
  const [ticket, setTicket] = useState(intent.ticket || '');
  const [out, setOut] = useState(null);
  useEffect(() => setTicket(intent.ticket || ''), [intent.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = async (e) => {
    e.preventDefault();
    const r = await run('agent', () => api.runAgent(intent.id, { ticket: ticket.trim() || null }));
    if (r) {
      setOut(r);
      onDone();
    }
  };

  return (
    <form onSubmit={go} className="stack-sm">
      <Field label="Ticket text" hint="The agent extracts a proposal from this text; the gateway then checks it against the intent.">
        <textarea rows={3} value={ticket} onChange={(e) => setTicket(e.target.value)} placeholder="e.g. Please refund 1500 for ORD-204, customer C-17" />
      </Field>
      <div className="row">
        <Button className="btn-primary" type="submit" busy={busy === 'agent'}>
          <Bot size={14} /> Run agent
        </Button>
      </div>
      {out && (
        <div className="result-box">
          <div className="row">
            <strong>Extractor</strong> <span className="mono">{out.extractor}</span>
          </div>
          {out.extraction_error && <div className="error-text">Extraction failed: {out.extraction_error}</div>}
          {out.extracted && (
            <KV items={Object.entries(out.extracted).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])} />
          )}
          {out.result && <ResultBox result={out.result} />}
        </div>
      )}
    </form>
  );
}

export default function IntentDetail({ id, onBack }) {
  const { data, error, reload } = usePoll(() => api.intent(id), [id], 4000);
  const { busy, run } = useAction();
  const [tab, setTab] = useState('proposal');
  const [shown, setShown] = useState(() => new Set(KIND_ORDER));
  const [actor, setActor] = useState('');

  const intent = data?.intent;
  useEffect(() => {
    if (intent && !actor) setActor(intent.operator_id || '');
  }, [intent, actor]);

  const events = useMemo(() => buildTimeline(data), [data]);
  const visible = events.filter((e) => shown.has(e.kind));
  const counts = useMemo(() => {
    const c = {};
    events.forEach((e) => { c[e.kind] = (c[e.kind] || 0) + 1; });
    return c;
  }, [events]);

  const toggle = (k) =>
    setShown((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  return (
    <div className="stack">
      <div className="row-between">
        <button className="btn btn-ghost" onClick={onBack}>
          <ArrowLeft size={14} /> All intents
        </button>
        <button className="icon-btn" onClick={reload} title="Refresh"><RefreshCw size={14} /></button>
      </div>
      <InlineError error={error} onRetry={reload} />
      {!data && !error && <Spinner label="Loading intent…" />}
      {intent && (
        <>
          <Card
            title={<>Intent <span className="mono">{intent.id}</span></>}
            icon={<FileText size={16} />}
            actions={<Badge value={intent.state} />}
          >
            <div className="intent-summary">
              <div>
                <div className="big">{amountOf(intent)}</div>
                <div className="muted">{intent.operation} · order <span className="mono">{intent.order_id}</span> · customer{' '}
                  <span className="mono">{intent.customer_id}</span></div>
              </div>
              <KV items={[
                ['operator', intent.operator_id], ['attempts', intent.attempt_count],
                ['key generation', intent.key_generation], ['created', ts(intent.created_at)],
                ['updated', `${ts(intent.updated_at)} (${relTime(intent.updated_at)})`],
                ['unknown since', intent.unknown_since ? ts(intent.unknown_since) : null],
                ['next check', intent.next_check_at ? `${ts(intent.next_check_at)} (${relTime(intent.next_check_at)})` : null],
                ['watch until', intent.watch_until ? ts(intent.watch_until) : null],
              ]} />
            </div>
            {intent.ticket && <blockquote className="ticket">{intent.ticket}</blockquote>}
          </Card>

          <div className="grid-detail">
            <Card
              title="Timeline"
              icon={<Link2 size={16} />}
              actions={
                <div className="chips">
                  {KIND_ORDER.map((k) => (
                    <button key={k} className={`chip ${shown.has(k) ? 'on' : ''}`} onClick={() => toggle(k)}>
                      {KINDS[k].label} <span className="mono">{counts[k] || 0}</span>
                    </button>
                  ))}
                </div>
              }
            >
              {visible.length === 0 ? (
                <div className="muted">No events to show.</div>
              ) : (
                <ol className="timeline">
                  {visible.map((e) => (
                    <li key={e.key} className={`tl-item kind-${e.kind}`}>
                      <div className="tl-dot">{KINDS[e.kind].icon}</div>
                      <div className="tl-content">
                        <div className="tl-head">
                          <span className="tl-kind">{KINDS[e.kind].label}</span>
                          <span className="tl-title">{e.title}</span>
                          {e.badges.filter(Boolean).map((b) => <Badge key={b} value={b} />)}
                          <span className="tl-time" title={ts(e.at)}>{ts(e.at)}</span>
                        </div>
                        {e.body && <div className="tl-body">{e.body}</div>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </Card>

            <div className="stack">
              <Card title="Actions">
                <div className="tabs-inline">
                  {[['proposal', 'Structured proposal'], ['agent', 'Run agent'], ['ops', 'Reconcile / revoke']].map(([k, l]) => (
                    <button key={k} className={`tab-inline ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>
                  ))}
                </div>
                {tab === 'proposal' && <ProposalForm intent={intent} onDone={reload} />}
                {tab === 'agent' && <AgentForm intent={intent} onDone={reload} />}
                {tab === 'ops' && (
                  <div className="stack-sm">
                    <p className="muted small">Reconcile asks the provider for the true outcome of unknown attempts now, instead of waiting for the worker.</p>
                    <Button
                      busy={busy === 'reconcile'}
                      onClick={async () => {
                        await run('reconcile', () => api.reconcile(intent.id), (r) => `Reconciled; intent is ${r?.intent_state ?? 'updated'}`);
                        reload();
                      }}
                    >
                      <RefreshCw size={14} /> Reconcile now
                    </Button>
                    <hr />
                    <p className="muted small">Revoking withdraws the authorization. Only allowed before any effect exists.</p>
                    <div className="row">
                      <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="actor id" aria-label="Revoking actor" />
                      <Button
                        className="btn-danger"
                        busy={busy === 'revoke'}
                        disabled={!actor.trim()}
                        onClick={async () => {
                          if (!window.confirm(`Revoke intent ${intent.id}?`)) return;
                          await run('revoke', () => api.revoke(intent.id, actor.trim()), 'Intent revoked');
                          reload();
                        }}
                      >
                        <Ban size={14} /> Revoke
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

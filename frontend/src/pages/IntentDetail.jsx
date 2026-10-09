import React, { useState } from 'react';
import { ArrowLeft, Bot, Ban, RefreshCw, Send } from 'lucide-react';
import api from '../api/endpoints.js';
import { newIdempotencyKey } from '../api/client.js';
import { usePoll } from '../hooks/usePoll.js';
import { Button, Card, Dialog, Field, InlineError, Spinner, useAction } from '../components/ui.jsx';
import { DecisionPill, StatusPill, TonePill } from '../components/StatusPill.jsx';
import Pipeline from '../components/Pipeline.jsx';
import Timeline from '../components/Timeline.jsx';
import { InvestigatorPanel } from '../components/Widgets.jsx';
import { can, formatMoney, formatTime } from '../domain.js';

const EXCEPTION_STATES = ['UNKNOWN', 'RECONCILING', 'DISCREPANCY', 'CANCEL_REQUESTED', 'ESCALATED'];
const LIVE_PROVIDER_STATUSES = ['PENDING', 'COMPLETED'];

function ProposalForm({ intent, onDone }) {
  const [f, setF] = useState({ operation: intent.operation, customer_id: intent.customer_id, order_id: intent.order_id,
    amount: intent.authorized_amount, currency: intent.currency, rationale: '' });
  const { busy, run } = useAction();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="stack" onSubmit={async (e) => {
      e.preventDefault();
      const r = await run('propose', () => api.propose(intent.intent_id, { ...f, amount: String(f.amount).trim() }, newIdempotencyKey()),
        (x) => `${x.decision}${x.reason ? ` (${x.reason})` : ''}: intent is ${x.state}`);
      if (r) onDone(r);
    }}>
      <div className="form-grid">
        <Field label="Operation"><select value={f.operation} onChange={set('operation')}><option>REFUND</option><option>PAYMENT_AUTHORIZATION</option></select></Field>
        <Field label="Customer"><input value={f.customer_id} onChange={set('customer_id')} /></Field>
        <Field label="Order"><input value={f.order_id} onChange={set('order_id')} /></Field>
        <Field label="Amount"><input value={f.amount} onChange={set('amount')} inputMode="decimal" /></Field>
        <Field label="Currency"><input value={f.currency} onChange={set('currency')} maxLength={3} /></Field>
        <Field label="Rationale"><input value={f.rationale} onChange={set('rationale')} /></Field>
      </div>
      <p className="tiny muted" style={{ margin: 0 }}>Change a field (e.g. amount ×10, ORD-240) to watch the gateway block it before any provider call.</p>
      <div><Button className="btn-primary" busy={busy === 'propose'} type="submit"><Send size={14} /> Submit proposal</Button></div>
    </form>
  );
}

export default function IntentDetail({ id, user, navigate }) {
  const { data: intent, error, loading, reload } = usePoll(() => api.getIntent(id), [id], 3000);
  const { data: tl, reload: reloadTl } = usePoll(() => api.timeline(id), [id], 3000);
  const { data: history, reload: reloadHist } = usePoll(() => api.history(id), [id], 5000);
  const { busy, run } = useAction();
  const [lastResult, setLastResult] = useState(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const refresh = () => { reload(); reloadTl(); reloadHist(); };

  if (loading && !intent) return <Spinner label="Loading intent…" />;
  if (error && !intent) return <InlineError error={error} onRetry={reload} />;
  const inv = history?.investigations?.[history.investigations.length - 1];
  const isException = EXCEPTION_STATES.includes(intent.state);
  const terminal = intent.state === 'CANCELLED' || intent.state === 'CLOSED';
  // Live provider effects that do not count toward this authorization (wrong amount, duplicate, ...).
  const unintended = intent.effects.filter((e) => !e.counts_toward_intent && !e.remediated
    && LIVE_PROVIDER_STATUSES.includes(e.status));
  const unintendedTotal = unintended.reduce((sum, e) => sum + Number(e.amount), 0);
  return (
    <div className="stack">
      <div className="row-between">
        <div className="row">
          <button className="icon-btn" onClick={() => navigate('/intents')} aria-label="Back to intents"><ArrowLeft size={18} /></button>
          <h2 className="mono select-all">{intent.intent_id}</h2>
          <StatusPill state={intent.state} />
          {intent.verified && <TonePill tone="emerald">provider-verified</TonePill>}
          {intent.open_review_case_id && <button className="chip" onClick={() => navigate('/reviews')}>{intent.open_review_case_id}</button>}
        </div>
        <Button onClick={refresh}><RefreshCw size={14} /> Refresh</Button>
      </div>

      <Card>
        <dl className="meta-grid">
          <div><dt>Operation</dt><dd>{intent.operation}</dd></div>
          <div><dt>Customer</dt><dd className="mono">{intent.customer_id}</dd></div>
          <div><dt>Order</dt><dd className="mono">{intent.order_id}</dd></div>
          <div><dt>Authorized</dt><dd className="money">{formatMoney(intent.authorized_amount, intent.currency)}</dd></div>
          <div><dt>Counted toward authorization</dt><dd className="money">{formatMoney(intent.effect_amount, intent.currency)}</dd></div>
          {unintended.length > 0 && (
            <div><dt>Unintended effect at provider</dt><dd className="money text-rose">{formatMoney(unintendedTotal.toFixed(2), intent.currency)}</dd></div>
          )}
          <div><dt>Authorized by</dt><dd className="mono">{intent.operator_id}</dd></div>
          <div><dt>Attempts</dt><dd>{intent.attempt_count} · key generation {intent.generation}</dd></div>
          <div><dt>Created</dt><dd>{formatTime(intent.created_at)}</dd></div>
        </dl>
        {intent.ticket_text && <p className="small muted">Ticket: “{intent.ticket_text}”</p>}
      </Card>

      <Card title="Pipeline"><Pipeline intent={intent} /></Card>

      <div className="grid-2">
        <Card title="Act as the agent">
          {lastResult && (
            <div className="callout small" style={{ marginBottom: 12 }}>
              Last decision: <DecisionPill decision={lastResult.decision} /> {lastResult.reason && <span className="mono">{lastResult.reason}</span>}
              {lastResult.extraction && <> · extracted by {lastResult.extraction.model}</>}
            </div>
          )}
          {terminal && (
            <div className="muted small">This intent is {intent.state.toLowerCase()}; the gateway accepts no further proposals for it.</div>
          )}
          {!terminal && can(user, 'agent:run') && intent.ticket_text && (
            <div className="row" style={{ marginBottom: 12 }}>
              <Button busy={busy === 'agent'} onClick={async () => {
                const r = await run('agent', () => api.runAgent(intent.intent_id, null), (x) => `${x.decision}: intent is ${x.state}`);
                if (r) { setLastResult(r); refresh(); }
              }}><Bot size={14} /> Run agent on the ticket</Button>
            </div>
          )}
          {!terminal && (can(user, 'proposals:create') ? <ProposalForm intent={intent} onDone={(r) => { setLastResult(r); refresh(); }} />
            : <div className="muted small">Your role cannot submit proposals.</div>)}
        </Card>
        <div className="stack">
          {isException && <InvestigatorPanel intentId={intent.intent_id} investigation={inv} user={user} onChange={refresh} />}
          {can(user, 'cancel') && !terminal && (
            <Card title="Cancel">
              <p className="small muted" style={{ marginTop: 0 }}>
                With no live effect the intent is cancelled at once. A pending refund or a hold is cancelled at the provider and
                the cancellation is verified first. A completed refund cannot be cancelled.
              </p>
              <Button className="btn-danger" onClick={() => setConfirmCancel(true)}><Ban size={14} /> Cancel intent</Button>
            </Card>
          )}
        </div>
      </div>

      <Card title="Timeline"><Timeline events={tl?.events || []} history={history} /></Card>

      <Card title="Attempts">
        <div className="table-wrap">
          <table className="table cards">
            <thead><tr><th>Attempt</th><th>Status</th><th className="num">Amount</th><th>Order</th><th>Provider transaction</th><th>Started</th><th>Error</th><th /></tr></thead>
            <tbody>
              {intent.attempts.map((a) => (
                <tr key={a.attempt_id}>
                  <td data-label="Attempt" className="mono">{a.attempt_id}</td>
                  <td data-label="Status"><TonePill tone={{ SUCCEEDED: 'emerald', UNKNOWN: 'cyan', SUBMITTING: 'cyan', RECONCILED: 'slate', FAILED: 'rose' }[a.status]}>{a.status}</TonePill></td>
                  <td data-label="Amount" className="num money">{formatMoney(a.amount, a.currency)}</td>
                  <td data-label="Order" className="mono">{a.order_id}</td>
                  <td data-label="Provider" className="mono">{a.provider_transaction_id || '—'}</td>
                  <td data-label="Started" className="small">{formatTime(a.started_at)}</td>
                  <td data-label="Error" className="small muted">{a.error || ''}</td>
                  <td>{can(user, 'reconcile') && ['UNKNOWN', 'SUBMITTING'].includes(a.status) && (
                    <Button className="btn-sm" busy={busy === a.attempt_id} onClick={async () => {
                      const r = await run(a.attempt_id, () => api.reconcileAttempt(a.attempt_id), (x) => `${x.outcome}; next: ${x.next_action}`);
                      if (r) refresh();
                    }}>Reconcile</Button>
                  )}</td>
                </tr>
              ))}
              {intent.attempts.length === 0 && <tr><td colSpan={8} className="muted">No provider call yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Effects at the provider">
        <div className="table-wrap">
          <table className="table cards">
            <thead><tr><th>Effect</th><th>Provider transaction</th><th>Class</th><th>Status</th><th className="num">Amount</th><th>Order</th><th>Customer</th><th>Note</th></tr></thead>
            <tbody>
              {intent.effects.map((e) => (
                <tr key={e.effect_id}>
                  <td data-label="Effect" className="mono">{e.effect_id}</td>
                  <td data-label="Provider" className="mono">{e.provider_transaction_id}</td>
                  <td data-label="Class"><TonePill tone={e.classification === 'INTENDED' ? 'emerald' : 'rose'}>{e.classification}</TonePill></td>
                  <td data-label="Status">{e.status}{e.remediated ? ' · remediated' : ''}</td>
                  <td data-label="Amount" className="num money">{formatMoney(e.amount, e.currency)}</td>
                  <td data-label="Order" className="mono">{e.order_id}</td>
                  <td data-label="Customer" className="mono">{e.customer_id}</td>
                  <td data-label="Note" className="small muted">{e.note || ''}</td>
                </tr>
              ))}
              {intent.effects.length === 0 && <tr><td colSpan={8} className="muted">No effect observed at the provider.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Proposals and decisions">
        <div className="table-wrap">
          <table className="table cards">
            <thead><tr><th>Proposal</th><th>Agent</th><th>Status</th><th>Decision</th><th>Reasons</th><th className="num">Amount</th><th>Order</th><th>When</th></tr></thead>
            <tbody>
              {intent.proposals.map((p) => (
                <tr key={p.proposal_id}>
                  <td data-label="Proposal" className="mono">{p.proposal_id}</td>
                  <td data-label="Agent" className="mono small">{p.agent_id}</td>
                  <td data-label="Status"><StatusPill state={p.status} /></td>
                  <td data-label="Decision"><DecisionPill decision={p.decision?.decision} /></td>
                  <td data-label="Reasons" className="mono small">{p.decision?.reasons?.join(', ')}</td>
                  <td data-label="Amount" className="num money">{formatMoney(p.amount, p.currency)}</td>
                  <td data-label="Order" className="mono">{p.order_id}</td>
                  <td data-label="When" className="small">{formatTime(p.created_at)}</td>
                </tr>
              ))}
              {intent.proposals.length === 0 && <tr><td colSpan={8} className="muted">No proposals yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {confirmCancel && (
        <Dialog title={`Cancel ${intent.intent_id}?`} onClose={() => setConfirmCancel(false)}
          footer={<><Button onClick={() => setConfirmCancel(false)}>Keep</Button>
            <Button className="btn-danger" busy={busy === 'cancel'} onClick={async () => {
              const r = await run('cancel', () => api.cancel(intent.intent_id), (x) => `Intent is ${x.state}`);
              setConfirmCancel(false);
              if (r) refresh();
            }}>Cancel intent</Button></>}>
          <p className="small">State now: <StatusPill state={intent.state} />. The gateway verifies any cancellation at the provider before reporting it.</p>
        </Dialog>
      )}
    </div>
  );
}

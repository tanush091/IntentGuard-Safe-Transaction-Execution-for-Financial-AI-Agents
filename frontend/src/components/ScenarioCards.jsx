import React, { useEffect, useState } from 'react';
import api from '../api/endpoints.js';
import { newIdempotencyKey } from '../api/client.js';
import { can } from '../domain.js';
import { useConsole } from './Widgets.jsx';
import { useToast } from './ui.jsx';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(intentId, states, log, timeoutMs = 20000) {
  const end = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < end) {
    const i = await api.getIntent(intentId);
    if (i.state !== last) {
      log('step', `${intentId} is ${i.state}`);
      last = i.state;
    }
    if (states.includes(i.state)) return i;
    await sleep(1000);
  }
  return api.getIntent(intentId);
}

/**
 * The four prescribed demo scenarios as one-click cards (DESIGN 5.7). Each run creates a fresh demo
 * order (simulator only), so the scenarios can be repeated, then drives the public API exactly as
 * an operator and an agent would. Steps are written to the live console.
 */
export const SCENARIOS = [
  {
    id: 'barrier', badge: 'SAFETY BARRIER', tone: 'rose', title: 'Unauthorized amount',
    text: 'Operator approves ₹1,500; the agent proposes ₹15,000. The gateway rejects it before any provider call.',
    async run({ log }) {
      const order = await api.demoOrder({ customer_id: 'C-17', amount: '5000' });
      const a = await api.createAuthorization({ customer_id: 'C-17', order_id: order.order_id, authorized_amount: '1500.00',
        currency: 'INR', ticket_text: `Refund ₹1,500 for ${order.order_id} to C-17` });
      log('step', `authorized ${a.intent_id}: refund ₹1,500 on ${order.order_id}`);
      const r = await api.propose(a.intent_id, { operation: 'REFUND', customer_id: 'C-17', order_id: order.order_id,
        amount: '15000.00', currency: 'INR', rationale: 'agent hallucinated ×10' }, newIdempotencyKey());
      log(r.decision === 'REJECT' ? 'verified' : 'error', `agent proposed ₹15,000 → ${r.decision} (${r.reasons.join(', ')}); no provider call`);
      return a.intent_id;
    },
  },
  {
    id: 'reconcile', badge: 'ACTIVE RECONCILIATION', tone: 'cyan', title: 'Lost response',
    text: 'The provider executes the refund but the response is lost. The gateway reconciles instead of paying twice.',
    needsFaults: true,
    async run({ log }) {
      const order = await api.demoOrder({ customer_id: 'C-17', amount: '8000' });
      await api.injectFault({ kind: 'TIMEOUT_AFTER_EXECUTION', order_id: order.order_id });
      log('warn', `fault armed: response to the next refund on ${order.order_id} will be lost`);
      const a = await api.createAuthorization({ customer_id: 'C-17', order_id: order.order_id, authorized_amount: '2000.00',
        currency: 'INR', ticket_text: `Please refund ₹2,000 on ${order.order_id} for customer C-17` });
      const r = await api.runAgent(a.intent_id);
      log('step', `agent (${r.extraction.source}) proposed → ${r.decision}; state ${r.state}`);
      const done = await waitFor(a.intent_id, ['COMPLETED', 'ESCALATED'], log);
      const ledger = await api.ledger(order.order_id);
      log(done.state === 'COMPLETED' ? 'verified' : 'warn', `${a.intent_id} ${done.state}; provider holds ${ledger.length} refund(s) for ${order.order_id}`);
      return a.intent_id;
    },
  },
  {
    id: 'duplicate', badge: 'DUPLICATE SUPPRESSION', tone: 'amber', title: 'Agent restart',
    text: 'The agent restarts and sends the same instruction with a new request id. No second refund is created.',
    async run({ log }) {
      const order = await api.demoOrder({ customer_id: 'C-17', amount: '12000' });
      const a = await api.createAuthorization({ customer_id: 'C-17', order_id: order.order_id, authorized_amount: '1200.00',
        currency: 'INR', ticket_text: `Refund ₹1,200 for ${order.order_id} to C-17` });
      const body = { operation: 'REFUND', customer_id: 'C-17', order_id: order.order_id, amount: '1200.00', currency: 'INR' };
      const r1 = await api.propose(a.intent_id, { ...body, request_id: 'agent-run-1' }, newIdempotencyKey());
      log('step', `first proposal → ${r1.decision}; state ${r1.state}; provider ${r1.provider_transaction_id}`);
      const r2 = await api.propose(a.intent_id, { ...body, request_id: 'agent-run-2-after-restart' }, newIdempotencyKey());
      log(r2.decision === 'DUPLICATE' ? 'verified' : 'error', `after restart → ${r2.decision} (${r2.reasons.join(', ')}); same provider transaction ${r2.provider_transaction_id}`);
      return a.intent_id;
    },
  },
  {
    id: 'escalation', badge: 'HUMAN ESCALATION', tone: 'amber', title: 'Incorrect completed effect',
    text: 'The provider pays ₹10,000 instead of ₹1,000 and refuses the cancellation. The case is escalated, never reported as reversed.',
    needsFaults: true,
    async run({ log }) {
      const order = await api.demoOrder({ customer_id: 'C-71', amount: '20000' });
      await api.injectFault({ kind: 'CORRUPT_AMOUNT', order_id: order.order_id, params: { factor: 10 } });
      await api.injectFault({ kind: 'FAILED_CANCELLATION', order_id: order.order_id });
      log('warn', `faults armed on ${order.order_id}: wrong amount ×10, cancellation will fail`);
      const a = await api.createAuthorization({ customer_id: 'C-71', order_id: order.order_id, authorized_amount: '1000.00',
        currency: 'INR', ticket_text: `Refund ₹1,000 for ${order.order_id} to C-71` });
      const r = await api.runAgent(a.intent_id);
      log('step', `agent proposed → ${r.decision}; state ${r.state}`);
      const done = await waitFor(a.intent_id, ['ESCALATED'], log, 10000);
      log(done.state === 'ESCALATED' ? 'warn' : 'error', `${a.intent_id} ${done.state}: open the review queue to resolve it`);
      return a.intent_id;
    },
  },
];

export default function ScenarioCards({ user, onOpen }) {
  const { log } = useConsole();
  const { push } = useToast();
  const [faults, setFaults] = useState('checking');
  const [running, setRunning] = useState(null);
  const allowed = can(user, 'dev') && can(user, 'authorizations:create');

  useEffect(() => {
    if (!allowed) return;
    api.devFaults().then(() => setFaults('ok')).catch((e) => setFaults(e.status === 404 ? 'off' : 'error'));
  }, [allowed]);

  if (!allowed) return <div className="muted small">Demo scenarios need an operator, reviewer or admin account.</div>;
  return (
    <div className="stack">
      {faults === 'off' && <div className="callout warn small">SIMULATOR_MODE is off, so the demo scenarios are disabled.</div>}
      <div className="scenarios">
        {SCENARIOS.map((s) => (
          <button key={s.id} className="scenario" disabled={!!running || faults !== 'ok'}
            onClick={async () => {
              setRunning(s.id);
              log('step', `▶ ${s.title}`);
              try {
                const iid = await s.run({ log });
                onOpen?.(iid);
              } catch (e) {
                log('error', `${s.title} failed: ${e.code || ''} ${e.message}`);
                push(e.message, 'bad');
              } finally {
                setRunning(null);
              }
            }}>
            <span className={`badge tone-${s.tone}`}>{s.badge}</span>
            <strong>{running === s.id ? 'Running…' : s.title}</strong>
            <p>{s.text}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

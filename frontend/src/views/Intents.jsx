import React, { useEffect, useMemo, useState } from 'react';
import { ClipboardList, Plus, X } from 'lucide-react';
import api from '../services/api.js';
import { Badge, Button, Card, Empty, Field, InlineError, Spinner, useAction, usePoll } from '../components/ui.jsx';
import IntentDetail from './IntentDetail.jsx';
import { amountOf, minorToMajorString, money, relTime, short, ts } from '../util.js';

// Enum values from intentguard/domain.py (labels only; counts come from the API).
const KNOWN_STATES = [
  'AUTHORIZED', 'IN_FLIGHT', 'PENDING_SETTLEMENT', 'OUTCOME_UNKNOWN', 'RETRYABLE',
  'DISCREPANCY', 'NEEDS_REVIEW', 'COMPLETED', 'REVOKED', 'CLOSED',
];
const OPERATIONS = ['REFUND', 'PAYMENT_AUTHORIZATION'];

function NewIntentForm({ onCreated, onCancel }) {
  const ops = usePoll(() => api.operators(), []);
  const orders = usePoll(() => api.orders(), []);
  const { busy, run } = useAction();

  const [operatorId, setOperatorId] = useState('');
  const [orderId, setOrderId] = useState('');
  const [operation, setOperation] = useState('REFUND');
  const [amount, setAmount] = useState('');
  const [ticket, setTicket] = useState('');

  const operator = useMemo(() => (ops.data || []).find((o) => o.id === operatorId), [ops.data, operatorId]);
  const order = useMemo(() => (orders.data || []).find((o) => o.id === orderId), [orders.data, orderId]);
  const permitted = operator?.permitted_operations?.length ? operator.permitted_operations : OPERATIONS;

  useEffect(() => {
    if (!operatorId && ops.data?.length) setOperatorId(ops.data.find((o) => o.active !== false)?.id || ops.data[0].id);
  }, [ops.data, operatorId]);
  useEffect(() => {
    if (!orderId && orders.data?.length) setOrderId(orders.data[0].id);
  }, [orders.data, orderId]);
  useEffect(() => {
    if (operator && !permitted.includes(operation)) setOperation(permitted[0]);
  }, [operator, permitted, operation]);

  const submit = async (e) => {
    e.preventDefault();
    if (!order) return;
    const r = await run(
      'create',
      () =>
        api.createIntent({
          operator_id: operatorId,
          customer_id: order.customer_id,
          order_id: order.id,
          operation,
          amount: String(amount).trim(),
          currency: order.currency || 'INR',
          ticket: ticket.trim() || null,
        }),
      (res) => `Intent ${short(res?.id, 14)} authorized`,
    );
    if (r) onCreated(r);
  };

  return (
    <Card
      title="Authorize a new intent"
      icon={<Plus size={16} />}
      actions={
        <button className="icon-btn" onClick={onCancel} aria-label="Close">
          <X size={16} />
        </button>
      }
    >
      <InlineError error={ops.error || orders.error} onRetry={() => { ops.reload(); orders.reload(); }} />
      <form className="form-grid" onSubmit={submit}>
        <Field label="Operator">
          <select value={operatorId} onChange={(e) => setOperatorId(e.target.value)} required>
            {(ops.data || []).map((o) => (
              <option key={o.id} value={o.id} disabled={o.active === false}>
                {o.name} ({o.id}){o.active === false ? ' — inactive' : ''}
              </option>
            ))}
          </select>
          {operator && (
            <span className="field-hint">
              Limit {money(operator.limit_minor, order?.currency || 'INR')} · may {(operator.permitted_operations || []).join(', ')}
            </span>
          )}
        </Field>
        <Field label="Order">
          <select value={orderId} onChange={(e) => setOrderId(e.target.value)} required>
            {(orders.data || []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.id} · {o.customer_id} · {amountOf(o)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Customer" hint="Taken from the selected order">
          <input value={order?.customer_id ?? ''} readOnly />
        </Field>
        <Field label="Operation">
          <select value={operation} onChange={(e) => setOperation(e.target.value)}>
            {permitted.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
        </Field>
        <Field label={`Amount (${order?.currency || 'INR'}, major units)`} hint={order ? `Order total ${amountOf(order)}` : null}>
          <input
            inputMode="decimal"
            placeholder={order ? minorToMajorString(order.amount_minor) : '0.00'}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            pattern="^\d+(\.\d{1,2})?$"
            title="A decimal amount like 1500 or 1500.00"
            required
          />
        </Field>
        <Field label="Ticket text (optional)" hint="Stored on the intent; the agent can extract a proposal from it">
          <textarea rows={2} value={ticket} onChange={(e) => setTicket(e.target.value)} placeholder="Customer support ticket…" />
        </Field>
        <div className="form-actions">
          <Button className="btn-primary" type="submit" busy={busy === 'create'} disabled={!order || !operatorId}>
            Authorize intent
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default function Intents({ focus, onFocusConsumed }) {
  const [stateFilter, setStateFilter] = useState('');
  const [selected, setSelected] = useState(focus || null);
  useEffect(() => {
    if (focus) {
      setSelected(focus);
      if (onFocusConsumed) onFocusConsumed();
    }
  }, [focus]); // eslint-disable-line react-hooks/exhaustive-deps
  const [showForm, setShowForm] = useState(false);
  const { data, error, loading, reload } = usePoll(() => api.intents({ state: stateFilter, limit: 200 }), [stateFilter], 4000);
  const metrics = usePoll(() => api.metrics(), [], 4000);

  const stateOptions = useMemo(() => {
    const live = Object.keys(metrics.data?.intents_by_state || {});
    return Array.from(new Set([...KNOWN_STATES, ...live]));
  }, [metrics.data]);

  if (selected) {
    return <IntentDetail id={selected} onBack={() => { setSelected(null); reload(); }} />;
  }

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Intents</h2>
        <div className="row">
          <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)} aria-label="Filter by state">
            <option value="">All states</option>
            {stateOptions.map((s) => (
              <option key={s} value={s}>
                {s}
                {metrics.data?.intents_by_state?.[s] !== undefined ? ` (${metrics.data.intents_by_state[s]})` : ''}
              </option>
            ))}
          </select>
          <Button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            <Plus size={14} /> New intent
          </Button>
        </div>
      </div>

      {showForm && (
        <NewIntentForm
          onCancel={() => setShowForm(false)}
          onCreated={(intent) => {
            setShowForm(false);
            reload();
            if (intent?.id) setSelected(intent.id);
          }}
        />
      )}

      <InlineError error={error} onRetry={reload} />
      {loading && !data && <Spinner label="Loading intents…" />}
      {data && data.length === 0 && (
        <Empty icon={<ClipboardList size={28} />} title="No intents">
          {stateFilter ? `Nothing in state ${stateFilter}.` : 'Authorize one with “New intent”.'}
        </Empty>
      )}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table clickable-rows">
            <thead>
              <tr>
                <th>Intent</th>
                <th>State</th>
                <th>Operation</th>
                <th>Order</th>
                <th>Customer</th>
                <th className="num">Amount</th>
                <th>Operator</th>
                <th className="num">Attempts</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {data.map((i) => (
                <tr key={i.id} onClick={() => setSelected(i.id)}>
                  <td className="mono" title={i.id}>{short(i.id, 14)}</td>
                  <td><Badge value={i.state} /></td>
                  <td>{i.operation}</td>
                  <td className="mono">{i.order_id}</td>
                  <td className="mono">{i.customer_id}</td>
                  <td className="num mono">{amountOf(i)}</td>
                  <td>{i.operator_id}</td>
                  <td className="num mono">{i.attempt_count ?? 0}</td>
                  <td title={ts(i.updated_at)}>{relTime(i.updated_at ?? i.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

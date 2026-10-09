import React, { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { Button, Dialog, Field, InlineError, Spinner, useAction } from '../components/ui.jsx';
import { StatusPill } from '../components/StatusPill.jsx';
import { INTENT_STATES, can, formatMoney, relTime, stateMeta } from '../domain.js';

function NewAuthorization({ onClose, onCreated }) {
  const { data: orders } = usePoll(() => api.listOrders(), [], 0);
  const [f, setF] = useState({ order_id: '', operation: 'REFUND', authorized_amount: '', ticket_text: '' });
  const { busy, run } = useAction();
  const order = orders?.items.find((o) => o.order_id === f.order_id);
  useEffect(() => {
    if (!f.order_id && orders?.items.length) setF((x) => ({ ...x, order_id: orders.items[0].order_id }));
  }, [orders]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = async () => {
    const r = await run('create', () => api.createAuthorization({
      customer_id: order.customer_id, order_id: f.order_id, operation: f.operation,
      authorized_amount: String(f.authorized_amount).trim(), currency: order.currency,
      ticket_text: f.ticket_text.trim() || null,
    }), (x) => `Authorized ${x.intent_id}`);
    if (r) onCreated(r.intent_id);
  };
  return (
    <Dialog title="Authorize a new intent" onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button className="btn-primary" busy={busy === 'create'} disabled={!order || !f.authorized_amount} onClick={submit}>Authorize</Button></>}>
      <Field label="Order" hint={order ? `Customer ${order.customer_id} · order total ${formatMoney(order.amount, order.currency)}` : null}>
        <select value={f.order_id} onChange={(e) => setF({ ...f, order_id: e.target.value })}>
          {(orders?.items || []).map((o) => <option key={o.order_id} value={o.order_id}>{o.order_id} · {o.customer_id}</option>)}
        </select>
      </Field>
      <Field label="Operation">
        <select value={f.operation} onChange={(e) => setF({ ...f, operation: e.target.value })}>
          <option value="REFUND">Refund</option><option value="PAYMENT_AUTHORIZATION">Payment authorization (hold)</option>
        </select>
      </Field>
      <Field label={`Amount (${order?.currency || 'INR'}, major units)`}>
        <input inputMode="decimal" value={f.authorized_amount} onChange={(e) => setF({ ...f, authorized_amount: e.target.value })} placeholder="1500.00" />
      </Field>
      <Field label="Ticket text (optional, read by the agent)">
        <textarea value={f.ticket_text} onChange={(e) => setF({ ...f, ticket_text: e.target.value })} placeholder="e.g. Please refund ₹1,500 for ORD-204, customer C-17" />
      </Field>
    </Dialog>
  );
}

export default function Intents({ user, navigate }) {
  const [state, setState] = useState('');
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [creating, setCreating] = useState(false);
  const { data, error, loading, reload } = usePoll(() => api.listIntents({ state, limit: 50 }), [state], 5000);
  useEffect(() => {
    if (data) {
      setItems(data.items);
      setCursor(data.next_cursor);
    }
  }, [data]);
  const more = async () => {
    const page = await api.listIntents({ state, limit: 50, cursor });
    setItems((x) => [...x, ...page.items]);
    setCursor(page.next_cursor);
  };
  return (
    <div className="stack">
      <div className="row-between">
        <h2>Intents</h2>
        <div className="row">
          <select value={state} onChange={(e) => setState(e.target.value)} aria-label="Filter by state">
            <option value="">All states</option>
            {INTENT_STATES.map((s) => <option key={s} value={s}>{s} · {stateMeta(s).label}</option>)}
          </select>
          {can(user, 'authorizations:create') && <Button className="btn-primary" onClick={() => setCreating(true)}><Plus size={14} /> New authorization</Button>}
        </div>
      </div>
      <InlineError error={error} onRetry={reload} />
      {loading && !data ? <Spinner label="Loading intents…" /> : (
        <div className="card table-wrap">
          <table className="table cards">
            <thead><tr><th>Intent</th><th>State</th><th>Operation</th><th>Order</th><th>Customer</th><th className="num">Authorized</th><th className="num">Effect</th><th>Updated</th></tr></thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.intent_id} className="clickable" tabIndex={0}
                  onClick={() => navigate(`/intents/${i.intent_id}`)} onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/intents/${i.intent_id}`); }}>
                  <td data-label="Intent" className="mono">{i.intent_id}</td>
                  <td data-label="State"><StatusPill state={i.state} /></td>
                  <td data-label="Operation" className="small">{i.operation}</td>
                  <td data-label="Order" className="mono">{i.order_id}</td>
                  <td data-label="Customer" className="mono">{i.customer_id}</td>
                  <td data-label="Authorized" className="num money">{formatMoney(i.authorized_amount, i.currency)}</td>
                  <td data-label="Effect" className="num money">{formatMoney(i.effect_amount, i.currency)}</td>
                  <td data-label="Updated" className="small muted">{relTime(i.updated_at)}</td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={8} className="muted">Nothing here yet.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {cursor && <Button onClick={more}>Load more</Button>}
      {creating && <NewAuthorization onClose={() => setCreating(false)} onCreated={(iid) => { setCreating(false); navigate(`/intents/${iid}`); }} />}
    </div>
  );
}

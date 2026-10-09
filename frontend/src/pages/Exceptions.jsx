import React from 'react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { Card, Empty, InlineError, Spinner } from '../components/ui.jsx';
import { StatusPill, TonePill } from '../components/StatusPill.jsx';
import { InvestigatorPanel } from '../components/Widgets.jsx';
import { formatMoney, relTime } from '../domain.js';

/** Stuck, unknown, discrepant and escalated intents, with the AI investigator (DESIGN 6). */
export default function Exceptions({ user, navigate }) {
  const { data, error, loading, reload } = usePoll(() => api.listExceptions({ limit: 50 }), [], 5000);
  if (loading && !data) return <Spinner label="Loading exceptions…" />;
  const items = data?.items || [];
  return (
    <div className="stack">
      <h2>Exceptions</h2>
      <p className="muted small" style={{ margin: 0 }}>
        Intents whose outcome is unknown, reconciled without an effect, discrepant, being cancelled or held for review.
        The investigator only recommends; a deterministic policy decides what may run.
      </p>
      <InlineError error={error} onRetry={reload} />
      {items.length === 0 && <Empty title="No exceptions">Every intent is settled or progressing normally.</Empty>}
      {items.map((i) => (
        <div key={i.intent_id} className="grid-2">
          <Card title={<button className="chip" onClick={() => navigate(`/intents/${i.intent_id}`)}>{i.intent_id}</button>}
            actions={<StatusPill state={i.state} />}>
            <dl className="meta-grid">
              <div><dt>Operation</dt><dd>{i.operation}</dd></div>
              <div><dt>Order · customer</dt><dd className="mono">{i.order_id} · {i.customer_id}</dd></div>
              <div><dt>Authorized</dt><dd className="money">{formatMoney(i.authorized_amount, i.currency)}</dd></div>
              <div><dt>Attempts</dt><dd>{i.attempt_count}</dd></div>
              <div><dt>Updated</dt><dd>{relTime(i.updated_at)}</dd></div>
              {i.latest_investigation && <div><dt>Last investigation</dt><dd><TonePill tone="violet">{i.latest_investigation.recommended_action}</TonePill></dd></div>}
            </dl>
          </Card>
          <InvestigatorPanel intentId={i.intent_id} investigation={i.latest_investigation} user={user} onChange={reload} />
        </div>
      ))}
    </div>
  );
}

import React, { useState } from 'react';
import { AlertTriangle, Ban, CheckCircle2, Copy, Search, Timer, Zap } from 'lucide-react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { Card, InlineError } from '../components/ui.jsx';
import { LiveConsole, MetricCard } from '../components/Widgets.jsx';
import ScenarioCards from '../components/ScenarioCards.jsx';
import { StatusPill } from '../components/StatusPill.jsx';
import { formatMoney, relTime } from '../domain.js';

const pct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`);

export default function Overview({ user, navigate }) {
  const [window, setWindow] = useState('24h');
  const { data: m, error, reload } = usePoll(() => api.metrics(window), [window], 5000);
  const { data: recent } = usePoll(() => api.listIntents({ limit: 8 }), [], 5000);
  const intents = m?.intents || {};
  const live = m?.live_unintended_effects;
  return (
    <div className="stack">
      <div className="row-between">
        <h2>Overview</h2>
        <select value={window} onChange={(e) => setWindow(e.target.value)} aria-label="Time window">
          {['1h', '24h', '7d', '30d', 'all'].map((w) => <option key={w}>{w}</option>)}
        </select>
      </div>
      <InlineError error={error} onRetry={reload} />
      <div className="grid-cards">
        <MetricCard label="Completed" icon={<CheckCircle2 size={14} />} tone="emerald" value={intents.completed} sub={`${intents.total ?? 0} intents in ${window}`} />
        <MetricCard label="Blocked" icon={<Ban size={14} />} tone="rose" value={intents.blocked} sub="proposals rejected or held, nothing executed" />
        <MetricCard label="Verifying" icon={<Search size={14} />} tone="cyan" value={intents.unknown} sub="outcome being reconciled" />
        <MetricCard label="Escalated" icon={<AlertTriangle size={14} />} tone="amber" value={intents.escalated}
          sub={m ? `${m.open_reviews.count} open review(s), ${formatMoney(m.open_reviews.discrepancy_minor / 100)} at stake` : null} />
        <MetricCard label="Duplicates suppressed" icon={<Copy size={14} />} value={m?.duplicates_suppressed} />
        <MetricCard label="Auto-resolved rate" icon={<Zap size={14} />} value={pct(m?.auto_resolved_rate)} sub="exceptions settled without a human" />
        <MetricCard label="Median time to verified" icon={<Timer size={14} />}
          value={m?.median_time_to_verified_s != null ? `${m.median_time_to_verified_s.toFixed(1)} s` : '—'} sub="first attempt → COMPLETED" />
      </div>
      {live && live.count > 0 && (
        <div className="callout warn">{live.count} live unintended effect(s), {formatMoney(live.amount_minor / 100)}: see Exceptions and the review queue.</div>
      )}
      <Card title="Demo scenarios">
        <ScenarioCards user={user} onOpen={(iid) => navigate(`/intents/${iid}`)} />
      </Card>
      <div className="grid-2">
        <Card title="Live console"><LiveConsole user={user} /></Card>
        <Card title="Recent intents" actions={<button className="btn btn-sm" onClick={() => navigate('/intents')}>All intents</button>}>
          <table className="table cards">
            <tbody>
              {(recent?.items || []).map((i) => (
                <tr key={i.intent_id} className="clickable" onClick={() => navigate(`/intents/${i.intent_id}`)}>
                  <td data-label="Intent" className="mono">{i.intent_id}</td>
                  <td data-label="State"><StatusPill state={i.state} /></td>
                  <td data-label="Amount" className="num money">{formatMoney(i.authorized_amount, i.currency)}</td>
                  <td data-label="Updated" className="muted small">{relTime(i.updated_at)}</td>
                </tr>
              ))}
              {recent && recent.items.length === 0 && <tr><td className="muted">No intents yet. Run a demo scenario.</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

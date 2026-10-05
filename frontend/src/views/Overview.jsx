import React from 'react';
import { Activity, AlertOctagon, ClipboardList, FileCheck2, Gavel, Send, Zap } from 'lucide-react';
import api from '../services/api.js';
import { Card, CountList, InlineError, Spinner, usePoll } from '../components/ui.jsx';
import AuditBadge from '../components/AuditBadge.jsx';
import { money, sumValues } from '../util.js';

function Tile({ label, value, sub, tone = 'info', icon, onClick }) {
  return (
    <div className={`tile tone-border-${tone} ${onClick ? 'clickable' : ''}`} onClick={onClick}>
      <div className="tile-label">
        {icon}
        {label}
      </div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

export default function Overview({ goto }) {
  const { data: m, error, reload } = usePoll(() => api.metrics(), [], 4000);

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Live overview</h2>
        <AuditBadge />
      </div>
      <InlineError error={error} onRetry={reload} />
      {!m && !error && <Spinner label="Loading metrics…" />}
      {m && (
        <>
          <div className="tiles">
            <Tile
              label="Intents"
              icon={<ClipboardList size={16} />}
              value={sumValues(m.intents_by_state)}
              sub={`${Object.keys(m.intents_by_state || {}).length} distinct states`}
              onClick={() => goto('intents')}
            />
            <Tile
              label="Open review cases"
              icon={<Gavel size={16} />}
              tone={(m.open_reviews?.count ?? 0) > 0 ? 'bad' : 'good'}
              value={m.open_reviews?.count ?? 0}
              sub={`Discrepancy ${money(m.open_reviews?.discrepancy_minor ?? 0)}`}
              onClick={() => goto('reviews')}
            />
            <Tile
              label="Live unintended effects"
              icon={<AlertOctagon size={16} />}
              tone={(m.live_unintended_effects?.count ?? 0) > 0 ? 'bad' : 'good'}
              value={m.live_unintended_effects?.count ?? 0}
              sub={`Exposure ${money(m.live_unintended_effects?.amount_minor ?? 0)}`}
            />
            <Tile
              label="Proposals"
              icon={<Send size={16} />}
              value={sumValues(m.proposals_by_decision)}
              sub={`${m.proposals_by_decision?.APPROVED ?? 0} approved · ${m.proposals_by_decision?.REJECTED ?? 0} rejected`}
            />
            <Tile
              label="Provider attempts"
              icon={<Zap size={16} />}
              value={sumValues(m.attempts_by_status)}
              sub={`${m.attempts_by_status?.UNKNOWN ?? 0} with unknown outcome`}
              tone={(m.attempts_by_status?.UNKNOWN ?? 0) > 0 ? 'warn' : 'info'}
            />
            <Tile
              label="Observed effects"
              icon={<Activity size={16} />}
              value={sumValues(m.effects_by_class)}
              sub={`${m.effects_by_class?.INTENDED ?? 0} intended`}
            />
          </div>

          <div className="grid-2">
            <Card title="Intents by state" icon={<ClipboardList size={16} />}>
              <CountList data={m.intents_by_state} emptyText="No intents yet. Create one on the Intents tab." />
            </Card>
            <Card title="Proposals by decision" icon={<FileCheck2 size={16} />}>
              <CountList data={m.proposals_by_decision} emptyText="No proposals submitted yet." />
            </Card>
            <Card title="Attempts by status" icon={<Zap size={16} />}>
              <CountList data={m.attempts_by_status} emptyText="No provider calls yet." />
            </Card>
            <Card title="Effects by classification" icon={<Activity size={16} />}>
              <CountList data={m.effects_by_class} emptyText="No provider transactions observed yet." />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

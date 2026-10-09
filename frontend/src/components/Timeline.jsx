import React, { useState } from 'react';
import {
  AlertTriangle, ArrowRight, Ban, CheckCircle2, CircleDot, FileSearch, RefreshCw, Search, Send, Shield, Sparkles,
} from 'lucide-react';
import { Drawer, Json } from './ui.jsx';
import { formatTime } from '../domain.js';

const ICON = {
  AUTHORIZED: Shield, DECISION: CircleDot, ATTEMPT_RESERVED: Send, ATTEMPT_RESULT: ArrowRight,
  PROVIDER_OBSERVATION: Search, RECONCILED: CheckCircle2, ATTEMPT_UNKNOWN: Search, CONTROLLED_RETRY: RefreshCw,
  PROVIDER_UNREACHABLE: AlertTriangle, REVERSAL_VERIFIED: CheckCircle2, ESCALATED: AlertTriangle,
  REVIEW_RESOLVED: CheckCircle2, STATE: ArrowRight, CANCEL_REQUESTED: Ban, CANCELLED: Ban,
  INVESTIGATION: Sparkles, INVESTIGATION_APPLIED: Sparkles,
};

function findEvidence(history, ref) {
  if (!history || !ref) return null;
  return (
    history.attempts?.find((a) => a.attempt_id === ref)
    || history.effects?.find((e) => e.provider_transaction_id === ref || e.effect_id === ref)
    || history.review_cases?.find((r) => r.case_id === ref)
    || history.webhook_events?.find((w) => w.webhook_event_id === ref || w.object_id === ref)
    || null
  );
}

/** Intent timeline (DESIGN 5.3): newest at the bottom, evidence chips open the raw record. */
export default function Timeline({ events = [], history }) {
  const [open, setOpen] = useState(null);
  if (!events.length) return <div className="muted small">No events yet.</div>;
  return (
    <>
      <ol className="timeline">
        {events.map((e) => {
          const Icon = ICON[e.kind] || FileSearch;
          return (
            <li key={e.seq}>
              <time dateTime={e.ts} title={formatTime(e.ts)}>{new Date(e.ts).toLocaleTimeString()}</time>
              <Icon size={14} aria-hidden="true" />
              <span><strong className="small">{e.kind.replaceAll('_', ' ').toLowerCase()}</strong> · {e.summary}</span>
              {e.ref ? <button className="chip" onClick={() => setOpen(e.ref)} title="Show the record">{e.ref}</button> : <span />}
            </li>
          );
        })}
      </ol>
      {open && (
        <Drawer title={open} onClose={() => setOpen(null)}>
          {findEvidence(history, open) ? <Json value={findEvidence(history, open)} />
            : <div className="muted small">No stored record for this reference.</div>}
        </Drawer>
      )}
    </>
  );
}

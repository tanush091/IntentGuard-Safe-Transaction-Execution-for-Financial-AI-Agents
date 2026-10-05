import React, { useState } from 'react';
import { Gavel, CheckCircle2 } from 'lucide-react';
import api from '../services/api.js';
import { Badge, Button, Card, Empty, Field, InlineError, Spinner, useAction, usePoll } from '../components/ui.jsx';
import { money, relTime, short, ts } from '../util.js';

// ReviewResolution enum (intentguard/domain.py)
const RESOLUTIONS = [
  ['CONFIRMED_COMPLETED', 'Reviewer verified the intended effect'],
  ['CONFIRMED_NO_EFFECT', 'Verified nothing executed; retry allowed'],
  ['MANUALLY_REMEDIATED', 'Discrepancy fixed outside the system'],
  ['CLOSED_UNFULFILLED', 'Give up on the intent'],
];

function ResolveForm({ rc, onDone }) {
  const { busy, run } = useAction();
  const [reviewer, setReviewer] = useState('');
  const [resolution, setResolution] = useState(RESOLUTIONS[0][0]);
  const [notes, setNotes] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    const r = await run(
      'resolve',
      () => api.resolveReview(rc.id, { reviewer_id: reviewer.trim(), resolution, notes }),
      (res) => `Case #${rc.id} resolved; intent is ${res?.intent_state ?? 'updated'}`,
    );
    if (r) onDone();
  };

  return (
    <form className="form-grid compact" onSubmit={submit}>
      <Field label="Reviewer id">
        <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} required placeholder="e.g. op-asha" />
      </Field>
      <Field label="Resolution" hint={RESOLUTIONS.find(([k]) => k === resolution)?.[1]}>
        <select value={resolution} onChange={(e) => setResolution(e.target.value)}>
          {RESOLUTIONS.map(([k]) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
      </Field>
      <Field label="Notes">
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <div className="form-actions">
        <Button className="btn-primary" type="submit" busy={busy === 'resolve'} disabled={!reviewer.trim()}>
          <CheckCircle2 size={14} /> Resolve case
        </Button>
      </div>
    </form>
  );
}

export default function Reviews({ openIntent }) {
  const [status, setStatus] = useState('OPEN');
  const [expanded, setExpanded] = useState(null);
  const { data, error, loading, reload } = usePoll(() => api.reviews(status), [status], 4000);

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Review queue</h2>
        <div className="seg">
          {['OPEN', 'RESOLVED'].map((s) => (
            <button key={s} className={status === s ? 'active' : ''} onClick={() => setStatus(s)}>
              {s === 'OPEN' ? 'Open' : 'Resolved'}
            </button>
          ))}
        </div>
      </div>
      <InlineError error={error} onRetry={reload} />
      {loading && !data && <Spinner label="Loading reviews…" />}
      {data && data.length === 0 && (
        <Empty icon={<Gavel size={28} />} title={status === 'OPEN' ? 'No open review cases' : 'No resolved cases yet'}>
          Cases appear here when the gateway cannot verify or automatically remediate an outcome.
        </Empty>
      )}
      {data &&
        data.map((rc) => (
          <Card
            key={rc.id}
            title={<>Case #{rc.id} · {rc.reason}</>}
            icon={<Gavel size={16} />}
            actions={<Badge value={rc.status} />}
          >
            <div className="review-meta">
              <div>
                <span className="muted">Intent </span>
                <button className="link mono" onClick={() => openIntent(rc.intent_id)} title={rc.intent_id}>
                  {short(rc.intent_id, 18)}
                </button>
              </div>
              <div>
                <span className="muted">Discrepancy </span>
                <strong className={rc.discrepancy_minor ? 'text-bad' : ''}>{money(rc.discrepancy_minor, rc.currency || 'INR')}</strong>
              </div>
              <div title={ts(rc.created_at)}>
                <span className="muted">Opened </span>{relTime(rc.created_at)}
              </div>
              {rc.resolved_at && (
                <div title={ts(rc.resolved_at)}>
                  <span className="muted">Resolved </span>{relTime(rc.resolved_at)} by <span className="mono">{rc.resolved_by}</span>
                </div>
              )}
              {rc.resolution && <Badge value={rc.resolution} tone="info" />}
            </div>
            {rc.notes && <p className="muted">{rc.notes}</p>}
            {rc.details && Object.keys(rc.details).length > 0 && (
              <details>
                <summary className="small muted">Details</summary>
                <pre className="json">{JSON.stringify(rc.details, null, 2)}</pre>
              </details>
            )}
            {rc.status === 'OPEN' &&
              (expanded === rc.id ? (
                <ResolveForm rc={rc} onDone={() => { setExpanded(null); reload(); }} />
              ) : (
                <Button onClick={() => setExpanded(rc.id)}>Resolve…</Button>
              ))}
          </Card>
        ))}
    </div>
  );
}

import React, { useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { Button, Dialog, Empty, Field, InlineError, Spinner, useAction } from '../components/ui.jsx';
import { TonePill } from '../components/StatusPill.jsx';
import { RESOLUTIONS, can, formatMoney, formatTime, relTime } from '../domain.js';

function ResolveDialog({ rc, onClose, onDone }) {
  const [resolution, setResolution] = useState(RESOLUTIONS[0][0]);
  const [note, setNote] = useState('');
  const { busy, run } = useAction();
  return (
    <Dialog title={`Resolve ${rc.case_id}`} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button className="btn-primary" busy={busy === 'r'} onClick={async () => {
          const r = await run('r', () => api.resolveReview(rc.case_id, resolution, note), (x) => `Resolved: intent is ${x.intent_state}`);
          if (r) onDone();
        }}><CheckCircle2 size={14} /> Resolve case</Button></>}>
      <div className="callout warn small">{rc.reason} · {formatMoney(rc.discrepancy_amount, rc.currency)} at stake · intent {rc.intent_id}</div>
      <Field label="Resolution">
        <select value={resolution} onChange={(e) => setResolution(e.target.value)}>
          {RESOLUTIONS.map(([v, text]) => <option key={v} value={v}>{v} — {text}</option>)}
        </select>
      </Field>
      <Field label="Note (appended to the audit log)"><textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <p className="tiny muted" style={{ margin: 0 }}>The operator who authorized an intent cannot resolve its case (separation of duties).</p>
    </Dialog>
  );
}

export default function Reviews({ user, navigate }) {
  const [status, setStatus] = useState('OPEN');
  const [open, setOpen] = useState(null);
  const { data, error, loading, reload } = usePoll(() => api.listReviews({ status, limit: 100 }), [status], 5000);
  if (loading && !data) return <Spinner label="Loading review cases…" />;
  const items = data?.items || [];
  return (
    <div className="stack">
      <div className="row-between">
        <h2>Review queue</h2>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="OPEN">Open</option><option value="RESOLVED">Resolved</option><option value="">All</option>
        </select>
      </div>
      <InlineError error={error} onRetry={reload} />
      {items.length === 0 ? <Empty title={status === 'OPEN' ? 'No open cases' : 'No cases'} /> : (
        <div className="card table-wrap">
          <table className="table cards">
            <thead><tr><th>Case</th><th>Intent</th><th>Reason</th><th className="num">At stake</th><th>Status</th><th>Opened</th><th /></tr></thead>
            <tbody>
              {items.map((rc) => (
                <tr key={rc.case_id}>
                  <td data-label="Case" className="mono">{rc.case_id}</td>
                  <td data-label="Intent"><button className="chip" onClick={() => navigate(`/intents/${rc.intent_id}`)}>{rc.intent_id}</button></td>
                  <td data-label="Reason" className="small">{rc.reason}</td>
                  <td data-label="At stake" className="num money">{formatMoney(rc.discrepancy_amount, rc.currency)}</td>
                  <td data-label="Status">{rc.status === 'OPEN' ? <TonePill tone="amber">Open</TonePill>
                    : <span title={`${rc.resolution} by ${rc.resolved_by} at ${formatTime(rc.resolved_at)}`}><TonePill tone="emerald">{rc.resolution}</TonePill></span>}</td>
                  <td data-label="Opened" className="small muted">{relTime(rc.created_at)}</td>
                  <td>{rc.status === 'OPEN' && can(user, 'reviews:resolve') && <Button className="btn-sm" onClick={() => setOpen(rc)}>Resolve ✓</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && <ResolveDialog rc={open} onClose={() => setOpen(null)} onDone={() => { setOpen(null); reload(); }} />}
    </div>
  );
}

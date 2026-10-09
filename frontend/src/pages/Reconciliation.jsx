import React, { useState } from 'react';
import { Play } from 'lucide-react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { Button, Card, Empty, InlineError, Json, useAction } from '../components/ui.jsx';
import { TonePill } from '../components/StatusPill.jsx';
import { can, formatTime, relTime } from '../domain.js';

export default function Reconciliation({ user, navigate }) {
  const [kind, setKind] = useState('');
  const runs = usePoll(() => api.listRuns({ limit: 30 }), [], 10000);
  const mismatches = usePoll(() => api.listMismatches({ kind, status: 'OPEN', limit: 100 }), [kind], 10000);
  const { busy, run } = useAction();
  const [detail, setDetail] = useState(null);
  return (
    <div className="stack">
      <div className="row-between">
        <h2>Reconciliation</h2>
        {can(user, 'reconciliation:run') && (
          <Button className="btn-primary" busy={busy === 'run'} onClick={async () => {
            await run('run', () => api.triggerRun(), (r) => `Matching run ${r.run_id}: ${r.mismatches_found} new mismatch(es)`);
            runs.reload(); mismatches.reload();
          }}><Play size={14} /> Run matching</Button>
        )}
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        A matching run compares the gateway ledger with the provider order by order. It never moves money or resolves
        anything by itself; a reviewer marks each mismatch as handled.
      </p>
      <Card title="Open mismatches" actions={
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
          <option value="">All kinds</option>{['MISSING', 'DUPLICATE', 'AMOUNT', 'ORDER', 'CUSTOMER'].map((k) => <option key={k}>{k}</option>)}
        </select>}>
        <InlineError error={mismatches.error} onRetry={mismatches.reload} />
        {(mismatches.data?.items || []).length === 0 ? <Empty title="No open mismatches" /> : (
          <div className="table-wrap">
            <table className="table cards">
              <thead><tr><th>Mismatch</th><th>Kind</th><th>Intent</th><th>Provider transaction</th><th>Order</th><th>Reason</th><th>Detected</th><th /></tr></thead>
              <tbody>
                {mismatches.data.items.map((m) => (
                  <tr key={m.mismatch_id}>
                    <td data-label="Mismatch" className="mono"><button className="chip" onClick={() => setDetail(m)}>{m.mismatch_id}</button></td>
                    <td data-label="Kind"><TonePill tone="amber">{m.kind}</TonePill></td>
                    <td data-label="Intent">{m.intent_id ? <button className="chip" onClick={() => navigate(`/intents/${m.intent_id}`)}>{m.intent_id}</button> : '—'}</td>
                    <td data-label="Provider" className="mono">{m.provider_transaction_id || '—'}</td>
                    <td data-label="Order" className="mono">{m.order_id || '—'}</td>
                    <td data-label="Reason" className="small">{m.details?.reason}</td>
                    <td data-label="Detected" className="small muted">{relTime(m.detected_at)}</td>
                    <td>{can(user, 'mismatches:resolve') && (
                      <Button className="btn-sm" busy={busy === m.mismatch_id} onClick={async () => {
                        await run(m.mismatch_id, () => api.resolveMismatch(m.mismatch_id, 'handled'), 'Marked as handled');
                        mismatches.reload();
                      }}>Handled</Button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Runs">
        <InlineError error={runs.error} onRetry={runs.reload} />
        <div className="table-wrap">
          <table className="table cards">
            <thead><tr><th>Run</th><th>Kind</th><th>By</th><th>Started</th><th className="num">Examined</th><th className="num">Resolved</th><th className="num">Escalated</th><th className="num">Mismatches</th><th className="num">Errors</th></tr></thead>
            <tbody>
              {(runs.data?.items || []).map((r) => (
                <tr key={r.run_id}>
                  <td data-label="Run" className="mono">{r.run_id}</td>
                  <td data-label="Kind">{r.kind}</td>
                  <td data-label="By" className="mono small">{r.triggered_by}</td>
                  <td data-label="Started" className="small">{formatTime(r.started_at)}</td>
                  <td data-label="Examined" className="num">{r.examined}</td>
                  <td data-label="Resolved" className="num">{r.resolved}</td>
                  <td data-label="Escalated" className="num">{r.escalated}</td>
                  <td data-label="Mismatches" className="num">{r.mismatches_found}</td>
                  <td data-label="Errors" className="num">{r.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {detail && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setDetail(null); }}>
          <aside className="drawer" role="dialog" aria-label={detail.mismatch_id}>
            <div className="dialog-head"><h3 className="mono">{detail.mismatch_id}</h3><button className="icon-btn" onClick={() => setDetail(null)} aria-label="Close">×</button></div>
            <div className="dialog-body"><Json value={detail} /></div>
          </aside>
        </div>
      )}
    </div>
  );
}

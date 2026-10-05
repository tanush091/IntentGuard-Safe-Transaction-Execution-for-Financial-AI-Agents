import React, { useState } from 'react';
import { ScrollText, ShieldCheck } from 'lucide-react';
import api from '../services/api.js';
import { Badge, Button, Card, Empty, InlineError, Spinner, useAction, usePoll } from '../components/ui.jsx';
import { relTime, short, ts } from '../util.js';

export default function Audit({ openIntent }) {
  const [limit, setLimit] = useState(100);
  const [chain, setChain] = useState('');
  const { data, error, loading, reload } = usePoll(
    () => api.audit({ limit, intent_id: chain.trim() || undefined }),
    [limit, chain],
    4000,
  );
  const { busy, run } = useAction();
  const [verify, setVerify] = useState(null);
  const [open, setOpen] = useState(null);

  const doVerify = async () => {
    const r = await run('verify', () => api.verifyAudit());
    if (r) setVerify({ ...r, at: Date.now() / 1000 });
  };

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Audit log</h2>
        <div className="row">
          <input placeholder="Filter by intent id (chain)" value={chain} onChange={(e) => setChain(e.target.value)} />
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="Limit">
            {[50, 100, 250, 500, 1000].map((n) => <option key={n} value={n}>last {n}</option>)}
          </select>
          <Button className="btn-primary" busy={busy === 'verify'} onClick={doVerify}>
            <ShieldCheck size={14} /> Verify chain
          </Button>
        </div>
      </div>

      {verify && (
        <div className={`banner tone-${verify.ok ? 'good' : 'bad'}`}>
          {verify.ok ? (
            <>Hash chains verified: {verify.checked ?? 0} events across {verify.chains ?? 0} chains are intact.</>
          ) : (
            <>Chain verification FAILED at seq {verify.broken_at_seq ?? '?'}{verify.chain_id ? ` in chain ${verify.chain_id}` : ''}.</>
          )}
          <span className="muted small"> (checked {relTime(verify.at)})</span>
        </div>
      )}

      <InlineError error={error} onRetry={reload} />
      {loading && !data && <Spinner label="Loading audit events…" />}
      {data && data.length === 0 && <Empty icon={<ScrollText size={28} />} title="No audit events" />}
      {data && data.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="num">Seq</th>
                  <th>Time</th>
                  <th>Chain (intent)</th>
                  <th>Kind</th>
                  <th>Actor</th>
                  <th>Hash</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((e) => (
                  <React.Fragment key={e.seq}>
                    <tr>
                      <td className="num mono">{e.seq}</td>
                      <td title={ts(e.created_at)}>{ts(e.created_at)}</td>
                      <td>
                        <button className="link mono" onClick={() => openIntent(e.chain_id)} title={e.chain_id}>
                          {short(e.chain_id, 16)}
                        </button>
                      </td>
                      <td><Badge value={e.kind} tone="info" /></td>
                      <td className="mono">{e.actor}</td>
                      <td className="mono tiny" title={`hash ${e.hash}\nprev ${e.prev_hash}`}>{short(e.hash, 12)}</td>
                      <td>
                        <button className="btn btn-sm btn-ghost" onClick={() => setOpen(open === e.seq ? null : e.seq)}>
                          {open === e.seq ? 'Hide' : 'Payload'}
                        </button>
                      </td>
                    </tr>
                    {open === e.seq && (
                      <tr className="sub-row">
                        <td colSpan={7}>
                          <pre className="json">{JSON.stringify(e.payload ?? {}, null, 2)}</pre>
                          <div className="mono tiny muted">prev_hash {e.prev_hash}<br />hash {e.hash}</div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import api from '../api/endpoints.js';
import { Button, Card, Drawer, InlineError, Json, useAction } from '../components/ui.jsx';
import { TonePill } from '../components/StatusPill.jsx';
import { can, formatTime } from '../domain.js';

/** Audit log search and hash-chain verification (DESIGN 5.9). */
export default function Audit({ user, navigate }) {
  const [filters, setFilters] = useState({ intent_id: '', actor: '', kind: '' });
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [error, setError] = useState(null);
  const [verify, setVerify] = useState(null);
  const [open, setOpen] = useState(null);
  const { busy, run } = useAction();

  const load = async (append = false) => {
    try {
      const page = await api.listAudit({ ...filters, limit: 100, cursor: append ? cursor : undefined });
      setItems((x) => (append ? [...x, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setError(null);
    } catch (e) {
      setError(e);
    }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Audit log</h2>
        {can(user, 'audit:verify') && (
          <div className="row">
            {verify && (verify.valid
              ? <TonePill tone="emerald">Chain verified ✓ ({verify.entries_checked} entries)</TonePill>
              : <TonePill tone="rose">Chain broken at #{verify.first_break?.seq}</TonePill>)}
            <Button className="btn-primary" busy={busy === 'verify'} onClick={async () => setVerify(await run('verify', () => api.verifyAudit()))}>
              <ShieldCheck size={14} /> Verify chain
            </Button>
          </div>
        )}
      </div>
      <Card>
        <form className="row" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <input placeholder="Intent id (chain)" value={filters.intent_id} onChange={(e) => setFilters({ ...filters, intent_id: e.target.value })} />
          <input placeholder="Actor" value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} />
          <input placeholder="Kind (e.g. intent.state)" value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })} />
          <Button type="submit">Search</Button>
        </form>
      </Card>
      <InlineError error={error} onRetry={() => load()} />
      <div className="card table-wrap">
        <table className="table cards">
          <thead><tr><th className="num">Seq</th><th>Time</th><th>Chain</th><th>Actor</th><th>Kind</th><th>Hash</th></tr></thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.seq} className="clickable" onClick={() => setOpen(e)}>
                <td data-label="Seq" className="num mono">{e.seq}</td>
                <td data-label="Time" className="small">{formatTime(e.ts)}</td>
                <td data-label="Chain">{e.intent_id ? <button className="chip" onClick={(ev) => { ev.stopPropagation(); navigate(`/intents/${e.intent_id}`); }}>{e.intent_id}</button> : <span className="mono small">{e.chain_id}</span>}</td>
                <td data-label="Actor" className="mono small">{e.actor}</td>
                <td data-label="Kind" className="mono small">{e.kind}</td>
                <td data-label="Hash" className="mono tiny muted">{e.hash.slice(0, 16)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cursor && <Button onClick={() => load(true)}>Load more</Button>}
      {open && <Drawer title={`#${open.seq} ${open.kind}`} onClose={() => setOpen(null)}><Json value={open} /></Drawer>}
    </div>
  );
}

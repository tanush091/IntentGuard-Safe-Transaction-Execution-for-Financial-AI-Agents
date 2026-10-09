import React, { useEffect, useState } from 'react';
import { KeyRound, Power, UserPlus } from 'lucide-react';
import api from '../api/endpoints.js';
import { usePoll } from '../hooks/usePoll.js';
import { Button, Card, Dialog, Field, InlineError, useAction } from '../components/ui.jsx';
import { TonePill } from '../components/StatusPill.jsx';
import { formatMoney, formatTime } from '../domain.js';

const ROLES = ['operator', 'reviewer', 'admin', 'agent'];

function NewUser({ onClose, onDone }) {
  const [f, setF] = useState({ name: '', email: '', role: 'operator', password: '', limit: '5000', ops: ['REFUND'] });
  const { busy, run } = useAction();
  const agent = f.role === 'agent';
  return (
    <Dialog title="Create user or agent principal" onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button className="btn-primary" busy={busy === 'u'} onClick={async () => {
        const r = await run('u', () => api.createUser({
          name: f.name, role: f.role, email: agent ? null : f.email, password: agent ? null : f.password,
          permitted_operations: agent ? [] : f.ops, limit: agent ? '0' : f.limit,
        }), (x) => `Created ${x.id}`);
        if (r) onDone();
      }}>Create</Button></>}>
      <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="Role"><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
      {!agent && <>
        <Field label="Email"><input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Password" hint="At least 12 characters"><input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label="May authorize">
          <select multiple value={f.ops} onChange={(e) => setF({ ...f, ops: [...e.target.selectedOptions].map((o) => o.value) })}>
            <option value="REFUND">REFUND</option><option value="PAYMENT_AUTHORIZATION">PAYMENT_AUTHORIZATION</option>
          </select>
        </Field>
        <Field label="Per-intent limit (INR)"><input value={f.limit} onChange={(e) => setF({ ...f, limit: e.target.value })} inputMode="decimal" /></Field>
      </>}
    </Dialog>
  );
}

function Users() {
  const { data, error, reload } = usePoll(() => api.listUsers({ limit: 200 }), [], 0);
  const { busy, run } = useAction();
  const [creating, setCreating] = useState(false);
  return (
    <Card title="Users and service principals" actions={<Button onClick={() => setCreating(true)}><UserPlus size={14} /> New</Button>}>
      <InlineError error={error} onRetry={reload} />
      <div className="table-wrap">
        <table className="table cards">
          <thead><tr><th>Id</th><th>Name</th><th>Email</th><th>Role</th><th>May authorize</th><th className="num">Limit</th><th>Status</th><th /></tr></thead>
          <tbody>
            {(data?.items || []).map((u) => (
              <tr key={u.id}>
                <td data-label="Id" className="mono">{u.id}</td>
                <td data-label="Name">{u.name}</td>
                <td data-label="Email" className="small">{u.email || '—'}</td>
                <td data-label="Role">
                  <select value={u.role} aria-label={`Role of ${u.id}`} onChange={async (e) => { await run(u.id, () => api.patchUser(u.id, { role: e.target.value }), 'Role changed; existing sessions ended'); reload(); }}>
                    {ROLES.map((r) => <option key={r}>{r}</option>)}
                  </select>
                </td>
                <td data-label="May authorize" className="small">{u.permitted_operations.join(', ') || '—'}</td>
                <td data-label="Limit" className="num money">{formatMoney(u.limit, u.currency)}</td>
                <td data-label="Status">{u.active ? <TonePill tone="emerald">active</TonePill> : <TonePill tone="slate">inactive</TonePill>}{u.locked && <TonePill tone="amber">locked</TonePill>}</td>
                <td><Button className="btn-sm" busy={busy === `a${u.id}`} onClick={async () => { await run(`a${u.id}`, () => api.patchUser(u.id, { active: !u.active })); reload(); }}>{u.active ? 'Deactivate' : 'Activate'}</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating && <NewUser onClose={() => setCreating(false)} onDone={() => { setCreating(false); reload(); }} />}
    </Card>
  );
}

function ServiceTokens() {
  const { data, reload } = usePoll(() => api.listServiceTokens(), [], 0);
  const users = usePoll(() => api.listUsers({ limit: 200 }), [], 0);
  const agents = (users.data?.items || []).filter((u) => u.role === 'agent' && u.active);
  const [f, setF] = useState({ principal_id: '', intent_ids: '', customer_ids: '' });
  const [issued, setIssued] = useState(null);
  const { busy, run } = useAction();
  useEffect(() => { if (!f.principal_id && agents.length) setF((x) => ({ ...x, principal_id: agents[0].id })); }, [agents.length]); // eslint-disable-line
  const list = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
  return (
    <Card title="Agent tokens" icon={<KeyRound size={16} />}>
      <p className="small muted" style={{ marginTop: 0 }}>Short-lived (≤ 5 min), scoped to intents or customers. Agents can only propose for, and read, what the token names.</p>
      <div className="form-grid">
        <label className="field"><span className="field-label">Agent</span><select value={f.principal_id} onChange={(e) => setF({ ...f, principal_id: e.target.value })}>{agents.map((a) => <option key={a.id}>{a.id}</option>)}</select></label>
        <label className="field"><span className="field-label">Intent ids (comma-separated)</span><input value={f.intent_ids} onChange={(e) => setF({ ...f, intent_ids: e.target.value })} placeholder="INT-1001" /></label>
        <label className="field"><span className="field-label">Customer ids</span><input value={f.customer_ids} onChange={(e) => setF({ ...f, customer_ids: e.target.value })} placeholder="C-17" /></label>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <Button className="btn-primary" busy={busy === 'issue'} disabled={!f.principal_id} onClick={async () => {
          const r = await run('issue', () => api.issueServiceToken({ principal_id: f.principal_id, intent_ids: list(f.intent_ids), customer_ids: list(f.customer_ids) }));
          if (r) { setIssued(r); reload(); }
        }}>Issue token</Button>
      </div>
      {issued && <div className="callout ok small" style={{ marginTop: 12 }}>Copy it now; it is not shown again (expires {formatTime(issued.expires_at)}):<pre className="json select-all">{issued.token}</pre></div>}
      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table className="table cards">
          <thead><tr><th>jti</th><th>Agent</th><th>Scopes</th><th>Expires</th><th>Status</th><th /></tr></thead>
          <tbody>
            {(data?.items || []).map((t) => (
              <tr key={t.jti}>
                <td data-label="jti" className="mono tiny">{t.jti.slice(0, 12)}…</td>
                <td data-label="Agent" className="mono">{t.principal_id}</td>
                <td data-label="Scopes" className="mono tiny">{t.scopes.join(' ')}</td>
                <td data-label="Expires" className="small">{formatTime(t.expires_at)}</td>
                <td data-label="Status">{t.active ? <TonePill tone="emerald">active</TonePill> : <TonePill tone="slate">{t.revoked_at ? 'revoked' : 'expired'}</TonePill>}</td>
                <td>{t.active && <Button className="btn-sm" onClick={async () => { await run(t.jti, () => api.revokeServiceToken(t.jti), 'Revoked'); reload(); }}>Revoke</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Policies() {
  const { data, error, reload } = usePoll(() => api.getPolicies(), [], 0);
  const [f, setF] = useState(null);
  const { busy, run } = useAction();
  useEffect(() => { if (data) setF({ ...data, max_amount: data.max_amount ?? '' }); }, [data]);
  if (!f) return <Card title="Policies"><InlineError error={error} onRetry={reload} /></Card>;
  const save = async (body) => { const r = await run('p', () => api.putPolicies(body), 'Policies saved and audited'); if (r) reload(); };
  return (
    <Card title="Policies" icon={<Power size={16} />}>
      <div className={`callout ${f.kill_switch ? 'blocked' : 'ok'}`} style={{ marginBottom: 12 }}>
        Kill switch is <strong>{f.kill_switch ? 'ON: every new proposal is held for review' : 'off'}</strong>
        <div style={{ marginTop: 8 }}><Button className={f.kill_switch ? '' : 'btn-danger'} busy={busy === 'p'} onClick={() => save({ kill_switch: !f.kill_switch })}>{f.kill_switch ? 'Turn off' : 'Turn on kill switch'}</Button></div>
      </div>
      <div className="form-grid">
        <Field label="Max amount per intent (INR)" hint="Empty = no policy limit"><input value={f.max_amount} onChange={(e) => setF({ ...f, max_amount: e.target.value })} inputMode="decimal" /></Field>
        <Field label="Attempt budget"><input type="number" min={1} max={20} value={f.attempt_budget} onChange={(e) => setF({ ...f, attempt_budget: Number(e.target.value) })} /></Field>
        <Field label="Absence window (s)"><input type="number" min={0} value={f.absence_window_s} onChange={(e) => setF({ ...f, absence_window_s: Number(e.target.value) })} /></Field>
        <Field label="Escalate unknown after (s)"><input type="number" min={1} value={f.unknown_review_after_s} onChange={(e) => setF({ ...f, unknown_review_after_s: Number(e.target.value) })} /></Field>
        <Field label="Separation of duties"><select value={String(f.separation_of_duties)} onChange={(e) => setF({ ...f, separation_of_duties: e.target.value === 'true' })}><option value="true">on</option><option value="false">off</option></select></Field>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <Button className="btn-primary" busy={busy === 'p'} onClick={() => save({
          ...(f.max_amount === '' ? { clear_max_amount: true } : { max_amount: String(f.max_amount) }),
          attempt_budget: f.attempt_budget, absence_window_s: f.absence_window_s,
          unknown_review_after_s: f.unknown_review_after_s, separation_of_duties: f.separation_of_duties,
        })}>Save</Button>
      </div>
    </Card>
  );
}

function Providers() {
  const { data, reload } = usePoll(() => api.getProviders(), [], 0);
  const p = data?.items?.[0];
  const [f, setF] = useState({ base_url: '', timeout_s: '', webhook_secret: '' });
  const { busy, run } = useAction();
  useEffect(() => { if (p) setF({ base_url: p.base_url, timeout_s: p.timeout_s, webhook_secret: '' }); }, [p?.base_url, p?.timeout_s]); // eslint-disable-line
  if (!p) return null;
  return (
    <Card title="Provider connection">
      <div className="row small" style={{ marginBottom: 12 }}><TonePill tone="amber">simulator</TonePill> mode {p.mode} · webhook secret {p.webhook_secret_set ? 'set' : 'not set'}</div>
      <div className="form-grid">
        <Field label="Base URL"><input value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} /></Field>
        <Field label="Timeout (s)"><input type="number" value={f.timeout_s} onChange={(e) => setF({ ...f, timeout_s: e.target.value })} /></Field>
        <Field label="Webhook secret" hint="Write-only: never shown again"><input type="password" autoComplete="new-password" value={f.webhook_secret} onChange={(e) => setF({ ...f, webhook_secret: e.target.value })} /></Field>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <Button className="btn-primary" busy={busy === 'pr'} onClick={async () => {
          const body = { base_url: f.base_url, timeout_s: Number(f.timeout_s) };
          if (f.webhook_secret) body.webhook_secret = f.webhook_secret;
          const r = await run('pr', () => api.putProvider('paysim', body), 'Provider updated');
          if (r) { setF((x) => ({ ...x, webhook_secret: '' })); reload(); }
        }}>Save</Button>
      </div>
    </Card>
  );
}

export default function Admin() {
  return (
    <div className="stack">
      <h2>Admin</h2>
      <Policies />
      <Users />
      <ServiceTokens />
      <Providers />
    </div>
  );
}

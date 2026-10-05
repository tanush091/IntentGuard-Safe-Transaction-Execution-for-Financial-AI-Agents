import React from 'react';
import { ShieldCheck, ShieldAlert, RefreshCw } from 'lucide-react';
import api from '../services/api.js';
import { usePoll } from './ui.jsx';

/** Live result of GET /api/audit/verify. */
export default function AuditBadge({ intervalMs = 15000, showButton = true }) {
  const { data, error, loading, reload } = usePoll(() => api.verifyAudit(), [], intervalMs);

  let content;
  if (error) {
    content = (
      <span className="badge tone-warn" title={error.message}>
        <ShieldAlert size={14} /> Audit check unavailable
      </span>
    );
  } else if (!data) {
    content = <span className="badge tone-muted">Verifying audit chain…</span>;
  } else if (data.ok) {
    content = (
      <span className="badge tone-good" title={`${data.checked ?? '?'} events across ${data.chains ?? '?'} chains`}>
        <ShieldCheck size={14} /> Audit chain intact · {data.checked ?? 0} events / {data.chains ?? 0} chains
      </span>
    );
  } else {
    content = (
      <span className="badge tone-bad">
        <ShieldAlert size={14} /> Audit chain BROKEN at seq {data.broken_at_seq ?? '?'}
        {data.chain_id ? ` (chain ${data.chain_id})` : ''}
      </span>
    );
  }

  return (
    <span className="audit-badge">
      {content}
      {showButton && (
        <button className="icon-btn" onClick={reload} title="Verify now" disabled={loading && !data}>
          <RefreshCw size={14} />
        </button>
      )}
    </span>
  );
}

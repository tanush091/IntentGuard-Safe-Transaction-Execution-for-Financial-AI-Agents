import React from 'react';
import { REASON_TEXT, pipelineStages, stateMeta } from '../domain.js';

const LABELS = ['Authorized', 'Proposed', 'Validated', 'Executing', 'Outcome'];
const STATUS_TEXT = { passed: 'passed', active: 'in progress', verifying: 'being verified', blocked: 'blocked',
  escalated: 'needs a human', done: 'verified', closed: 'resolved by a reviewer', idle: 'not reached' };

/**
 * Five-node state pipeline (DESIGN 5.1). A blocked proposal shows a callout with the reason code and
 * plain-language text; UNKNOWN/RECONCILING render as a dashed "Verifying" node, never as an error.
 */
export default function Pipeline({ intent }) {
  const nodes = pipelineStages(intent);
  const last = intent?.proposals?.[intent.proposals.length - 1];
  const decision = last?.decision;
  const blocked = decision && decision.decision !== 'ALLOW' && !intent.proposals.some((p) => p.decision?.decision === 'ALLOW');
  const terminal = stateMeta(intent?.state).label;
  return (
    <div className="stack">
      <ol className="pipeline" aria-label="Intent pipeline">
        {LABELS.map((label, i) => (
          <li key={label} className={`pipe-node ${nodes[i]}`} aria-label={`${label}: ${STATUS_TEXT[nodes[i]]}`}>
            <span className="pipe-label">{i === 4 && nodes[4] !== 'idle' ? terminal : label}</span>
            <span className="tiny">{i === 3 && nodes[3] === 'verifying' ? 'Verifying' : STATUS_TEXT[nodes[i]]}</span>
          </li>
        ))}
      </ol>
      {blocked && (
        <div className="callout blocked" role="status">
          <strong>{decision.decision}</strong> · <span className="mono">{decision.reasons?.join(', ')}</span>
          <div>{(decision.reasons || []).map((r) => REASON_TEXT[r]).filter(Boolean).join(' ')}</div>
          <div className="small muted">No provider call was made for this proposal.</div>
        </div>
      )}
      {['UNKNOWN', 'RECONCILING'].includes(intent?.state) && (
        <div className="callout verifying" role="status">
          Being verified: the provider outcome is not known yet. The gateway reconciles before any retry;
          this is not a failure.
        </div>
      )}
    </div>
  );
}

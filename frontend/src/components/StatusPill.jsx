import React from 'react';
import { Activity, AlertTriangle, Ban, Check, Circle, Search, Shield, Undo2, X } from 'lucide-react';
import { DECISION_META, stateMeta } from '../domain.js';

const ICONS = { shield: Shield, activity: Activity, search: Search, alert: AlertTriangle, undo: Undo2, check: Check,
  x: X, ban: Ban, dot: Circle };
const KIND_CLASS = { active: 'state-active', verifying: 'state-verifying', completed: 'state-completed',
  blocked: 'state-blocked', escalated: 'state-escalated' };

/** State pill: icon + label + colour (DESIGN 5.2). "Verifying" is never shown as failed. */
export function StatusPill({ state, title }) {
  const m = stateMeta(state);
  const Icon = ICONS[m.icon] || Circle;
  return (
    <span className={`pill tone-${m.tone} ${KIND_CLASS[m.kind] || ''}`} title={title || state} aria-label={`${m.label} (${state})`}>
      <Icon size={12} aria-hidden="true" />{m.label}
    </span>
  );
}

export function DecisionPill({ decision }) {
  const m = DECISION_META[decision] || { label: decision || '—', tone: 'slate' };
  return <span className={`pill tone-${m.tone}`} title={decision}>{m.label}</span>;
}

export function TonePill({ tone = 'slate', children, title }) {
  return <span className={`pill tone-${tone}`} title={title}>{children}</span>;
}

/**
 * Domain vocabulary for the UI (docs/API.md section 1.6, docs/DESIGN.md section 3).
 * State names mirror backend/intentguard/domain.py; colour is never the only signal (label + icon).
 */

export const INTENT_STATES = [
  'AUTHORIZED', 'IN_FLIGHT', 'EXECUTING', 'UNKNOWN', 'RECONCILING', 'DISCREPANCY',
  'CANCEL_REQUESTED', 'ESCALATED', 'COMPLETED', 'CANCELLED', 'CLOSED',
];

/** state -> {label, tone, kind, icon}. kind drives the pill class (DESIGN 5.2). */
export const STATE_META = {
  AUTHORIZED: { label: 'Authorized', tone: 'indigo', kind: 'authorized', icon: 'shield' },
  IN_FLIGHT: { label: 'Executing', tone: 'cyan', kind: 'active', icon: 'activity' },
  EXECUTING: { label: 'Executing', tone: 'cyan', kind: 'active', icon: 'activity' },
  UNKNOWN: { label: 'Verifying', tone: 'cyan', kind: 'verifying', icon: 'search' },
  RECONCILING: { label: 'Verifying', tone: 'cyan', kind: 'verifying', icon: 'search' },
  DISCREPANCY: { label: 'Needs review', tone: 'amber', kind: 'escalated', icon: 'alert' },
  CANCEL_REQUESTED: { label: 'Cancelling', tone: 'amber', kind: 'escalated', icon: 'undo' },
  ESCALATED: { label: 'Needs review', tone: 'amber', kind: 'escalated', icon: 'alert' },
  COMPLETED: { label: 'Completed ✓', tone: 'emerald', kind: 'completed', icon: 'check' },
  CANCELLED: { label: 'Cancelled', tone: 'slate', kind: 'cancelled', icon: 'x' },
  CLOSED: { label: 'Closed', tone: 'slate', kind: 'cancelled', icon: 'x' },
  // proposal-level outcomes
  PROPOSED: { label: 'Proposed', tone: 'indigo', kind: 'authorized', icon: 'dot' },
  VALIDATED: { label: 'Validated', tone: 'indigo', kind: 'authorized', icon: 'check' },
  REJECTED: { label: 'Blocked', tone: 'rose', kind: 'blocked', icon: 'ban' },
  BLOCKED: { label: 'Blocked', tone: 'rose', kind: 'blocked', icon: 'ban' },
};

export const DECISION_META = {
  ALLOW: { label: 'Allowed', tone: 'emerald' },
  REJECT: { label: 'Rejected', tone: 'rose' },
  DUPLICATE: { label: 'Duplicate suppressed', tone: 'amber' },
  HOLD_FOR_REVIEW: { label: 'Held for review', tone: 'amber' },
};

/** Plain-language text for reason codes (shown in the blocked callout). */
export const REASON_TEXT = {
  AMOUNT_EXCEEDS_AUTHORIZATION: 'The proposed amount is larger than the operator authorized.',
  AMOUNT_BELOW_AUTHORIZATION: 'The proposed amount differs from the authorization (smaller).',
  ORDER_MISMATCH: 'The proposal names a different order than the authorization.',
  CUSTOMER_MISMATCH: 'The proposal names a different customer than the authorization.',
  CURRENCY_MISMATCH: 'The proposal uses a different currency.',
  OPERATION_MISMATCH: 'The proposal asks for a different operation.',
  EXCEEDS_REMAINING_BALANCE: 'The order does not have enough remaining balance.',
  OPERATOR_NOT_PERMITTED: 'The authorizing operator is no longer permitted to approve this.',
  POLICY_LIMIT_EXCEEDED: 'The amount is above the admin policy limit.',
  ALREADY_COMPLETED: 'The authorized effect already exists; nothing new was sent.',
  ATTEMPT_IN_PROGRESS: 'Another attempt is in progress; the gateway owns this intent.',
  HELD_FOR_REVIEW: 'The intent is held for a human reviewer.',
  ATTEMPT_BUDGET_EXHAUSTED: 'The attempt budget is used up; a reviewer must decide.',
  KILL_SWITCH: 'The kill switch is on: every new proposal is held for review.',
  INTENT_NOT_ACTIVE: 'The intent is cancelled or closed.',
};

export const RESOLUTIONS = [
  ['ACCEPTED_AS_IS', 'The verified intended effect stands as the outcome'],
  ['REFUND_RECOVERED_OUT_OF_BAND', 'The wrong effect was handled outside the system; retry with a fresh key'],
  ['WRITTEN_OFF', 'Give up on the intent and close it'],
  ['CONFIRMED_NO_EFFECT', 'Verified that nothing executed; a controlled retry is allowed'],
  ['OTHER', 'Close the case with a note; nothing is assumed'],
];

export const ACTION_TEXT = {
  MARK_COMPLETED: 'Mark completed (re-reads the matching transaction from the provider)',
  WAIT_AND_RECHECK: 'Wait and re-check on the next worker pass',
  CONTROLLED_RETRY: 'Controlled retry under the same rules as the worker',
  CANCEL_PENDING: 'Cancel the pending wrong effect and verify the cancellation',
  ESCALATE: 'Open a review case',
};

export function stateMeta(state) {
  return STATE_META[state] || { label: state || '—', tone: 'slate', kind: 'other', icon: 'dot' };
}

/**
 * The five-node pipeline (DESIGN 5.1): Authorized -> Proposed -> Validated -> Executing -> Terminal.
 * Returns one status per node: 'passed' | 'active' | 'verifying' | 'blocked' | 'escalated' | 'done' | 'idle'.
 */
export function pipelineStages(intent) {
  const nodes = ['idle', 'idle', 'idle', 'idle', 'idle'];
  if (!intent) return nodes;
  const state = intent.state;
  const proposals = intent.proposals || [];
  const last = proposals[proposals.length - 1];
  const decision = last?.decision?.decision;
  const allowed = proposals.some((p) => p.decision?.decision === 'ALLOW');
  nodes[0] = 'passed';
  if (!last) {
    // Cancelled (or closed by a reviewer) before any proposal: a normal end, not an escalation.
    nodes[1] = state === 'CANCELLED' || state === 'CLOSED' ? 'idle' : 'active';
    if (state === 'CANCELLED') nodes[4] = 'done';
    if (state === 'CLOSED') nodes[4] = 'closed';
    return nodes;
  }
  nodes[1] = 'passed';
  if (!allowed) {
    nodes[2] = decision === 'REJECT' || decision === 'HOLD_FOR_REVIEW' ? 'blocked' : 'active';
    nodes[4] = decision === 'HOLD_FOR_REVIEW' ? 'escalated' : 'blocked';
    return nodes;
  }
  nodes[2] = 'passed';
  if (state === 'IN_FLIGHT' || state === 'EXECUTING') nodes[3] = 'active';
  else if (state === 'UNKNOWN' || state === 'RECONCILING') nodes[3] = 'verifying';
  else nodes[3] = 'passed';
  if (state === 'COMPLETED' || state === 'CANCELLED') nodes[4] = 'done';
  else if (state === 'ESCALATED') nodes[4] = 'escalated';
  else if (state === 'CLOSED') nodes[4] = 'closed';
  // The gateway is still recovering on its own (remediating an unintended effect, or cancelling).
  else if (state === 'DISCREPANCY' || state === 'CANCEL_REQUESTED') nodes[4] = 'active';
  return nodes;
}

/** Role capabilities, mirroring backend/gateway_api/security.py (the server enforces them). */
const OPERATOR = ['intents:read', 'authorizations:create', 'proposals:create', 'agent:run', 'reconcile', 'cancel',
  'exceptions:read', 'exceptions:investigate', 'investigations:apply', 'reviews:read', 'audit:read',
  'metrics:read', 'orders:read', 'reconciliation:read', 'dev'];
const REVIEWER = [...OPERATOR, 'reviews:resolve', 'audit:verify', 'reconciliation:run', 'mismatches:resolve'];
const CAPS = { operator: OPERATOR, reviewer: REVIEWER, admin: [...REVIEWER, 'admin'], agent: [] };

export function can(user, cap) {
  return !!user && (CAPS[user.role] || []).includes(cap);
}

export function formatMoney(amount, currency = 'INR') {
  if (amount === null || amount === undefined || amount === '') return '—';
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  const symbols = { INR: '₹', USD: '$', EUR: '€', GBP: '£' };
  const s = n.toLocaleString(currency === 'INR' ? 'en-IN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${symbols[currency] || `${currency} `}${s}`;
}

export function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function relTime(iso) {
  if (!iso) return '—';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(s)) return iso;
  if (s < 5) return 'just now';
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

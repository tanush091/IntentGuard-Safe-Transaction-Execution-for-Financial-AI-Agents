// Formatting helpers. Nothing here encodes data; it only renders what the API returns.

const SYMBOLS = { INR: '₹', USD: '$', EUR: '€', GBP: '£' };

export function money(minor, currency = 'INR') {
  if (minor === null || minor === undefined || Number.isNaN(Number(minor))) return '—';
  const sym = SYMBOLS[(currency || '').toUpperCase()] ?? `${currency || ''} `;
  const major = Number(minor) / 100;
  return `${sym}${major.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Prefer the server's own amount_display; fall back to formatting amount_minor. */
export function amountOf(row) {
  if (!row) return '—';
  return row.amount_display ?? money(row.amount_minor, row.currency);
}

export function ts(epoch) {
  if (epoch === null || epoch === undefined) return '—';
  const d = new Date(Number(epoch) * 1000);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

export function relTime(epoch) {
  if (epoch === null || epoch === undefined) return '';
  const s = Math.round(Date.now() / 1000 - Number(epoch));
  if (Number.isNaN(s)) return '';
  if (s < 0) return `in ${fmtDur(-s)}`;
  return `${fmtDur(s)} ago`;
}

function fmtDur(s) {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export function short(id, n = 10) {
  if (!id) return '—';
  const s = String(id);
  return s.length > n + 2 ? `${s.slice(0, n)}…` : s;
}

export function sumValues(obj) {
  if (!obj || typeof obj !== 'object') return 0;
  return Object.values(obj).reduce((a, b) => a + (Number(b) || 0), 0);
}

export function minorToMajorString(minor) {
  if (minor === null || minor === undefined) return '';
  const n = Number(minor);
  if (Number.isNaN(n)) return '';
  return (n / 100).toFixed(2);
}

/** Tone used for badges, keyed by enum value from the backend. */
const TONES = {
  // intent states
  AUTHORIZED: 'info', IN_FLIGHT: 'info', PENDING_SETTLEMENT: 'info',
  OUTCOME_UNKNOWN: 'warn', RETRYABLE: 'warn', DISCREPANCY: 'bad', NEEDS_REVIEW: 'bad',
  COMPLETED: 'good', REVOKED: 'muted', CLOSED: 'muted',
  // decisions
  APPROVED: 'good', REJECTED: 'bad', DUPLICATE: 'warn', IN_PROGRESS: 'info', HELD: 'bad',
  // attempt statuses
  SUBMITTING: 'info', ACKNOWLEDGED: 'good', UNKNOWN: 'warn', NO_EFFECT: 'muted',
  // provider statuses
  PENDING: 'info', CANCELLED: 'muted', FAILED: 'bad',
  // effect classes
  INTENDED: 'good', MISMATCH: 'bad',
  // reviews
  OPEN: 'bad', RESOLVED: 'good',
  PASS: 'good', FAIL: 'bad',
};

export function toneOf(value) {
  return TONES[String(value || '').toUpperCase()] || 'muted';
}

export function errMsg(e) {
  return (e && e.message) || String(e);
}

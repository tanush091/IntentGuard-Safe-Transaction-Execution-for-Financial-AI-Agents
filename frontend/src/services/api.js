/**
 * API client for the IntentGuard gateway (gateway_api/main.py).
 * All requests go through /api, which Vite (dev) and nginx (docker) proxy to the gateway.
 */

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function detailToText(detail) {
  if (detail == null) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg, type}]
    return detail
      .map((d) => (d && d.msg ? `${(d.loc || []).slice(1).join('.') || 'body'}: ${d.msg}` : JSON.stringify(d)))
      .join('; ');
  }
  return JSON.stringify(detail);
}

async function request(path, { method = 'GET', body, query } = {}) {
  let url = `${BASE}${path}`;
  if (query) {
    const qs = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(`Network error: cannot reach gateway (${e.message})`, 0, null);
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const msg = detailToText(data && data.detail) || (typeof data === 'string' && data) || res.statusText;
    throw new ApiError(`${method} ${path} failed (${res.status}): ${msg}`, res.status, data);
  }
  return data;
}

export const api = {
  metrics: () => request('/metrics'),
  operators: () => request('/operators'),
  orders: () => request('/orders'),

  intents: ({ state, limit } = {}) => request('/intents', { query: { state, limit } }),
  intent: (id) => request(`/intents/${encodeURIComponent(id)}`),
  createIntent: (body) => request('/intents', { method: 'POST', body }),
  submitProposal: (id, body) => request(`/intents/${encodeURIComponent(id)}/proposals`, { method: 'POST', body }),
  runAgent: (id, body) => request(`/intents/${encodeURIComponent(id)}/agent`, { method: 'POST', body }),
  reconcile: (id) => request(`/intents/${encodeURIComponent(id)}/reconcile`, { method: 'POST' }),
  revoke: (id, actor) => request(`/intents/${encodeURIComponent(id)}/revoke`, { method: 'POST', body: { actor } }),

  reviews: (status) => request('/reviews', { query: { status } }),
  resolveReview: (caseId, body) =>
    request(`/reviews/${encodeURIComponent(caseId)}/resolve`, { method: 'POST', body }),

  audit: ({ intent_id, limit } = {}) => request('/audit', { query: { intent_id, limit } }),
  verifyAudit: () => request('/audit/verify'),

  latestExperiment: () => request('/experiments/latest'),
};

export default api;

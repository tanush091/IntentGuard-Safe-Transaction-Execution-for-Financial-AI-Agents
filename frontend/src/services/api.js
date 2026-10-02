/**
 * API client service for IntentGuard Safety Gateway.
 */

const BASE_URL = '/api';

export async function fetchMetrics() {
  try {
    const res = await fetch(`${BASE_URL}/experiments/metrics`);
    if (!res.ok) throw new Error('Failed to fetch metrics');
    return await res.json();
  } catch (err) {
    console.error(err);
    return null;
  }
}

export async function fetchIntents(limit = 20) {
  try {
    const res = await fetch(`${BASE_URL}/intents?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch intents');
    return await res.json();
  } catch (err) {
    console.error(err);
    return [];
  }
}

export async function createIntent(payload) {
  const res = await fetch(`${BASE_URL}/intents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return await res.json();
}

export async function submitProposal(payload) {
  const res = await fetch(`${BASE_URL}/proposals`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return await res.json();
}

export async function fetchAuditEvents(limit = 30) {
  try {
    const res = await fetch(`${BASE_URL}/transactions/audit-events?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch audit events');
    return await res.json();
  } catch (err) {
    console.error(err);
    return [];
  }
}

export async function fetchReviewCases() {
  try {
    const res = await fetch(`${BASE_URL}/reviews`);
    if (!res.ok) throw new Error('Failed to fetch review cases');
    return await res.json();
  } catch (err) {
    console.error(err);
    return [];
  }
}

export async function resolveReviewCase(caseId, notes) {
  const res = await fetch(`${BASE_URL}/reviews/${caseId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution_notes: notes, action: 'RESOLVE' })
  });
  return await res.json();
}

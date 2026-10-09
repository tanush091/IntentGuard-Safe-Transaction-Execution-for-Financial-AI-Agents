/**
 * HTTP client for the gateway API (docs/API.md). All requests go to /api, which Vite (dev) and
 * nginx (docker) proxy to the gateway.
 *
 * Tokens (docs/SECURITY.md 3.4): the access token is kept in memory only; the refresh token is an
 * HttpOnly cookie the browser sends to /api/auth/refresh together with the CSRF header. A 401 on an
 * API call triggers one refresh (shared by concurrent callers) and one retry.
 */

const BASE = '/api';
const CSRF_HEADER = 'X-IntentGuard-CSRF';

export class ApiError extends Error {
  constructor({ status, code, message, details, requestId }) {
    super(message || code || `HTTP ${status}`);
    this.status = status;
    this.code = code || 'ERROR';
    this.details = details || {};
    this.requestId = requestId || null;
  }
}

let accessToken = null;
let refreshing = null;
let onAuthLost = () => {};

export function setAccessToken(token) {
  accessToken = token;
}

export function hasAccessToken() {
  return !!accessToken;
}

export function setOnAuthLost(fn) {
  onAuthLost = fn;
}

export function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function parse(res) {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function toApiError(status, body) {
  const e = body && typeof body === 'object' && body.error ? body.error : null;
  if (e) {
    return new ApiError({ status, code: e.code, message: e.message, details: e.details, requestId: e.request_id });
  }
  return new ApiError({ status, code: status === 0 ? 'NETWORK' : 'HTTP_ERROR',
    message: typeof body === 'string' && body ? body : `HTTP ${status}` });
}

/** Rotate the refresh cookie and store the new access token. Returns the login payload or null. */
export async function refreshSession(fetchImpl = fetch) {
  if (!refreshing) {
    // Concurrent callers share one in-flight refresh; it is forgotten as soon as it settles.
    refreshing = (async () => {
      try {
        const res = await fetchImpl(`${BASE}/auth/refresh`, {
          method: 'POST', credentials: 'same-origin', headers: { [CSRF_HEADER]: '1' },
        });
        if (!res.ok) return null;
        const body = await parse(res);
        accessToken = body.access_token;
        return body;
      } catch {
        return null;
      }
    })().finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function request(path, { method = 'GET', body, query, idempotencyKey, auth = true,
  fetchImpl = fetch, retried = false } = {}) {
  let url = `${BASE}${path}`;
  if (query) {
    const qs = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  let res;
  try {
    res = await fetchImpl(url, {
      method, headers, credentials: 'same-origin', body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError({ status: 0, code: 'NETWORK', message: `Cannot reach the gateway (${e.message})` });
  }
  if (res.status === 401 && auth && !retried) {
    const refreshed = await refreshSession(fetchImpl);
    if (refreshed) return request(path, { method, body, query, idempotencyKey, auth, fetchImpl, retried: true });
    accessToken = null;
    onAuthLost();
  }
  const data = await parse(res);
  if (!res.ok) throw toApiError(res.status, data);
  return data;
}

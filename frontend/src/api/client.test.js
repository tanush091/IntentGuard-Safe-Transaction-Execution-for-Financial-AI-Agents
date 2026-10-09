import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError, request, setAccessToken, setOnAuthLost, toApiError } from './client.js';

function response(status, body, calls) {
  return { ok: status >= 200 && status < 300, status, text: async () => (body === undefined ? '' : JSON.stringify(body)) };
}

function fakeFetch(script) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init });
    const step = script.shift();
    return typeof step === 'function' ? step(url, init) : step;
  };
  return { impl, calls };
}

describe('error envelope (API 1.4)', () => {
  it('maps the envelope to ApiError fields', () => {
    const e = toApiError(422, { error: { code: 'VALIDATION_ERROR', message: 'bad', details: { x: 1 }, request_id: 'req_1' } });
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.message, e.requestId, e.details.x]).toEqual([422, 'VALIDATION_ERROR', 'bad', 'req_1', 1]);
  });
});

describe('request', () => {
  beforeEach(() => setAccessToken('old'));

  it('sends the bearer token and the Idempotency-Key header', async () => {
    const { impl, calls } = fakeFetch([response(200, { ok: true })]);
    await request('/intents', { method: 'POST', body: { a: 1 }, idempotencyKey: 'k1', fetchImpl: impl });
    expect(calls[0].url).toBe('/api/intents');
    expect(calls[0].init.headers.Authorization).toBe('Bearer old');
    expect(calls[0].init.headers['Idempotency-Key']).toBe('k1');
  });

  it('refreshes once on 401 with the CSRF header, then retries with the new token', async () => {
    const { impl, calls } = fakeFetch([
      response(401, { error: { code: 'TOKEN_EXPIRED', message: 'expired' } }),
      response(200, { access_token: 'new', user: { id: 'u' }, expires_in: 900 }),
      response(200, { items: [] }),
    ]);
    const out = await request('/intents', { fetchImpl: impl });
    expect(out).toEqual({ items: [] });
    expect(calls[1].url).toBe('/api/auth/refresh');
    expect(calls[1].init.headers['X-IntentGuard-CSRF']).toBe('1');
    expect(calls[2].init.headers.Authorization).toBe('Bearer new');
  });

  it('signals auth loss when the refresh fails', async () => {
    let lost = false;
    setOnAuthLost(() => { lost = true; });
    const { impl } = fakeFetch([
      response(401, { error: { code: 'INVALID_TOKEN', message: 'no' } }),
      response(401, { error: { code: 'INVALID_REFRESH_TOKEN', message: 'no' } }),
    ]);
    await expect(request('/intents', { fetchImpl: impl })).rejects.toMatchObject({ status: 401 });
    expect(lost).toBe(true);
  });

  it('treats a decision as data, not an error (API contract rule 2)', async () => {
    const { impl } = fakeFetch([response(200, { decision: 'REJECT', reason: 'AMOUNT_EXCEEDS_AUTHORIZATION' })]);
    await expect(request('/intents/INT-1/proposals', { method: 'POST', body: {}, fetchImpl: impl }))
      .resolves.toMatchObject({ decision: 'REJECT' });
  });

  it('reports network failures as ApiError with status 0', async () => {
    const impl = async () => { throw new Error('down'); };
    await expect(request('/intents', { fetchImpl: impl })).rejects.toMatchObject({ status: 0, code: 'NETWORK' });
  });
});

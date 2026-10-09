/**
 * Every gateway route the dashboard calls, in one table. scripts/check-contract.mjs compares this
 * table with docs/api/openapi.json (exported from the backend) and fails the build on drift.
 */

import { newIdempotencyKey, request } from './client.js';

export const ROUTES = {
  login: ['POST', '/auth/login'],
  logout: ['POST', '/auth/logout'],
  me: ['GET', '/auth/me'],
  createAuthorization: ['POST', '/authorizations'],
  listIntents: ['GET', '/intents'],
  getIntent: ['GET', '/intents/{intent_id}'],
  timeline: ['GET', '/intents/{intent_id}/timeline'],
  history: ['GET', '/intents/{intent_id}/history'],
  cancel: ['POST', '/intents/{intent_id}/cancel'],
  propose: ['POST', '/intents/{intent_id}/proposals'],
  runAgent: ['POST', '/intents/{intent_id}/agent'],
  reconcileAttempt: ['POST', '/attempts/{attempt_id}/reconcile'],
  listRuns: ['GET', '/reconciliation/runs'],
  triggerRun: ['POST', '/reconciliation/runs'],
  listMismatches: ['GET', '/reconciliation/mismatches'],
  resolveMismatch: ['POST', '/reconciliation/mismatches/{mismatch_id}/resolve'],
  listExceptions: ['GET', '/exceptions'],
  investigate: ['POST', '/exceptions/{intent_id}/investigate'],
  getInvestigation: ['GET', '/investigations/{investigation_id}'],
  applyInvestigation: ['POST', '/investigations/{investigation_id}/apply'],
  listReviews: ['GET', '/review-cases'],
  getReview: ['GET', '/review-cases/{case_id}'],
  resolveReview: ['POST', '/review-cases/{case_id}/resolve'],
  listAudit: ['GET', '/audit'],
  verifyAudit: ['GET', '/audit/verify'],
  metrics: ['GET', '/metrics/summary'],
  experiments: ['GET', '/experiments/latest'],
  listOrders: ['GET', '/orders'],
  listUsers: ['GET', '/admin/users'],
  createUser: ['POST', '/admin/users'],
  patchUser: ['PATCH', '/admin/users/{user_id}'],
  listServiceTokens: ['GET', '/admin/service-tokens'],
  issueServiceToken: ['POST', '/admin/service-tokens'],
  revokeServiceToken: ['DELETE', '/admin/service-tokens/{jti}'],
  getPolicies: ['GET', '/admin/policies'],
  putPolicies: ['PUT', '/admin/policies'],
  getProviders: ['GET', '/admin/providers'],
  putProvider: ['PUT', '/admin/providers/{name}'],
  ready: ['GET', '/ready'],
  devFaults: ['GET', '/dev/faults'],
  injectFault: ['POST', '/dev/faults'],
  clearFaults: ['DELETE', '/dev/faults'],
  ledger: ['GET', '/dev/ledger'],
  demoOrder: ['POST', '/dev/orders'],
  tick: ['POST', '/dev/worker/tick'],
};

function call(name, params = {}, opts = {}) {
  const [method, template] = ROUTES[name];
  const path = template.replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(params[k]));
  return request(path, { method, ...opts });
}

/** A fresh Idempotency-Key per user action protects against double submits. */
const once = () => ({ idempotencyKey: newIdempotencyKey() });

export const api = {
  login: (email, password) => call('login', {}, { body: { email, password }, auth: false }),
  logout: () => call('logout', {}, { auth: false }),
  me: () => call('me'),

  createAuthorization: (body) => call('createAuthorization', {}, { body, ...once() }),
  listIntents: (query) => call('listIntents', {}, { query }),
  getIntent: (intent_id) => call('getIntent', { intent_id }),
  timeline: (intent_id) => call('timeline', { intent_id }),
  history: (intent_id) => call('history', { intent_id }),
  cancel: (intent_id, note = '') => call('cancel', { intent_id }, { body: { note }, ...once() }),
  propose: (intent_id, body, idempotencyKey) => call('propose', { intent_id }, { body, idempotencyKey }),
  runAgent: (intent_id, ticket_text) => call('runAgent', { intent_id }, { body: { ticket_text }, ...once() }),
  reconcileAttempt: (attempt_id) => call('reconcileAttempt', { attempt_id }),

  listRuns: (query) => call('listRuns', {}, { query }),
  triggerRun: () => call('triggerRun', {}, { query: { wait: 'true' } }),
  listMismatches: (query) => call('listMismatches', {}, { query }),
  resolveMismatch: (mismatch_id, note) => call('resolveMismatch', { mismatch_id }, { body: { note } }),

  listExceptions: (query) => call('listExceptions', {}, { query }),
  investigate: (intent_id) => call('investigate', { intent_id }, once()),
  getInvestigation: (investigation_id) => call('getInvestigation', { investigation_id }),
  applyInvestigation: (investigation_id) => call('applyInvestigation', { investigation_id }, once()),

  listReviews: (query) => call('listReviews', {}, { query }),
  getReview: (case_id) => call('getReview', { case_id }),
  resolveReview: (case_id, resolution, note) =>
    call('resolveReview', { case_id }, { body: { resolution, note }, ...once() }),

  listAudit: (query) => call('listAudit', {}, { query }),
  verifyAudit: () => call('verifyAudit'),
  metrics: (window = '24h') => call('metrics', {}, { query: { window } }),
  experiments: () => call('experiments'),
  listOrders: () => call('listOrders'),

  listUsers: (query) => call('listUsers', {}, { query }),
  createUser: (body) => call('createUser', {}, { body }),
  patchUser: (user_id, body) => call('patchUser', { user_id }, { body }),
  listServiceTokens: () => call('listServiceTokens'),
  issueServiceToken: (body) => call('issueServiceToken', {}, { body }),
  revokeServiceToken: (jti) => call('revokeServiceToken', { jti }),
  getPolicies: () => call('getPolicies'),
  putPolicies: (body) => call('putPolicies', {}, { body }),
  getProviders: () => call('getProviders'),
  putProvider: (name, body) => call('putProvider', { name }, { body }),
  ready: () => call('ready', {}, { auth: false }),

  devFaults: () => call('devFaults'),
  injectFault: (body) => call('injectFault', {}, { body }),
  clearFaults: () => call('clearFaults'),
  ledger: (order_id) => call('ledger', {}, { query: { order_id } }),
  demoOrder: (body) => call('demoOrder', {}, { body }),
  tick: () => call('tick'),
};

export default api;

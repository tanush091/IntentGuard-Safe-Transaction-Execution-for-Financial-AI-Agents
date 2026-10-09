import { describe, expect, it } from 'vitest';
import { INTENT_STATES, STATE_META, can, formatMoney, pipelineStages, stateMeta } from './domain.js';

const proposal = (decision) => ({ decision: { decision } });

describe('state presentation (DESIGN 3, TEST_PLAN 13)', () => {
  it('has a label and tone for every backend intent state', () => {
    INTENT_STATES.forEach((s) => {
      expect(STATE_META[s]).toBeDefined();
      expect(STATE_META[s].label).toBeTruthy();
    });
  });

  it('shows UNKNOWN and RECONCILING as Verifying, never as failed', () => {
    for (const s of ['UNKNOWN', 'RECONCILING']) {
      expect(stateMeta(s).label).toBe('Verifying');
      expect(stateMeta(s).kind).toBe('verifying');
      expect(stateMeta(s).label.toLowerCase()).not.toContain('fail');
    }
  });

  it('falls back safely for an unknown value', () => {
    expect(stateMeta('SOMETHING_NEW').label).toBe('SOMETHING_NEW');
  });
});

describe('pipeline (DESIGN 5.1)', () => {
  it('waits at Proposed with no proposal', () => {
    expect(pipelineStages({ state: 'AUTHORIZED', proposals: [] })).toEqual(['passed', 'active', 'idle', 'idle', 'idle']);
  });

  it('marks a rejected proposal as blocked before execution', () => {
    expect(pipelineStages({ state: 'AUTHORIZED', proposals: [proposal('REJECT')] }))
      .toEqual(['passed', 'passed', 'blocked', 'idle', 'blocked']);
  });

  it('renders an unknown outcome as a verifying node', () => {
    expect(pipelineStages({ state: 'UNKNOWN', proposals: [proposal('ALLOW')] })[3]).toBe('verifying');
  });

  it('completes, and escalates', () => {
    expect(pipelineStages({ state: 'COMPLETED', proposals: [proposal('ALLOW')] })).toEqual(['passed', 'passed', 'passed', 'passed', 'done']);
    expect(pipelineStages({ state: 'ESCALATED', proposals: [proposal('ALLOW')] })[4]).toBe('escalated');
  });

  it('distinguishes a reviewer-closed case and automatic recovery from escalation', () => {
    expect(pipelineStages({ state: 'CLOSED', proposals: [proposal('ALLOW')] })[4]).toBe('closed');
    expect(pipelineStages({ state: 'CANCEL_REQUESTED', proposals: [proposal('ALLOW')] })[4]).toBe('active');
    expect(pipelineStages({ state: 'DISCREPANCY', proposals: [proposal('ALLOW')] })[4]).toBe('active');
    expect(pipelineStages({ state: 'CANCELLED', proposals: [] })).toEqual(['passed', 'idle', 'idle', 'idle', 'done']);
  });

  it('keeps a later allowed proposal ahead of an earlier rejection', () => {
    expect(pipelineStages({ state: 'COMPLETED', proposals: [proposal('REJECT'), proposal('ALLOW')] })[4]).toBe('done');
  });
});

describe('role gating mirrors the server (SECURITY 4)', () => {
  it('operators cannot resolve reviews, verify audit or administer', () => {
    const op = { role: 'operator' };
    expect(can(op, 'proposals:create')).toBe(true);
    expect(can(op, 'reviews:resolve')).toBe(false);
    expect(can(op, 'audit:verify')).toBe(false);
    expect(can(op, 'admin')).toBe(false);
  });

  it('reviewers resolve, admins administer, agents get nothing in the UI', () => {
    expect(can({ role: 'reviewer' }, 'reviews:resolve')).toBe(true);
    expect(can({ role: 'reviewer' }, 'admin')).toBe(false);
    expect(can({ role: 'admin' }, 'admin')).toBe(true);
    expect(can({ role: 'agent' }, 'intents:read')).toBe(false);
    expect(can(null, 'intents:read')).toBe(false);
  });
});

describe('money', () => {
  it('formats decimal strings with the currency symbol and two decimals', () => {
    expect(formatMoney('1500.00', 'INR')).toBe('₹1,500.00');
    expect(formatMoney(null)).toBe('—');
  });
});

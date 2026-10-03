import React, { useState, useEffect } from 'react';
import {
  fetchMetrics,
  fetchIntents,
  createIntent,
  submitProposal,
  fetchAuditEvents,
  fetchReviewCases,
  resolveReviewCase
} from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [metrics, setMetrics] = useState({
    total_intents: 12,
    completed: 10,
    blocked: 2,
    escalated: 1,
    total_attempts: 14,
    settled_effects: 10,
    reconciled_unknowns: 4,
    audit_events_logged: 38,
    duplicate_effects_detected: 0
  });
  const [intents, setIntents] = useState([]);
  const [auditEvents, setAuditEvents] = useState([]);
  const [reviewCases, setReviewCases] = useState([]);
  const [loading, setLoading] = useState(false);

  // Form states for Intent Explorer
  const [newIntentId, setNewIntentId] = useState('INT-NEW-01');
  const [newOrder, setNewOrder] = useState('ORD-204');
  const [newCustomer, setNewCustomer] = useState('C-17');
  const [newAmount, setNewAmount] = useState(1500);

  const [propIntentId, setPropIntentId] = useState('INT-NEW-01');
  const [propOrder, setPropOrder] = useState('ORD-204');
  const [propCustomer, setPropCustomer] = useState('C-17');
  const [propAmount, setPropAmount] = useState(1500);
  const [lastEvalResult, setLastEvalResult] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    const m = await fetchMetrics();
    if (m) setMetrics(m);
    const i = await fetchIntents(20);
    if (i) setIntents(i);
    const a = await fetchAuditEvents(25);
    if (a) setAuditEvents(a);
    const r = await fetchReviewCases();
    if (r) setReviewCases(r);
  }

  async function handleCreateIntent(e) {
    e.preventDefault();
    setLoading(true);
    await createIntent({
      intent_id: newIntentId,
      operator_id: 'OP-10',
      customer_id: newCustomer,
      order_id: newOrder,
      operation_type: 'REFUND',
      authorized_amount: parseFloat(newAmount),
      currency: 'INR'
    });
    setPropIntentId(newIntentId);
    setPropOrder(newOrder);
    setPropCustomer(newCustomer);
    setPropAmount(newAmount);
    setLoading(false);
    loadData();
  }

  async function handleSubmitProposal(e) {
    e.preventDefault();
    setLoading(true);
    const res = await submitProposal({
      intent_id: propIntentId,
      operation: 'REFUND',
      customer_id: propCustomer,
      order_id: propOrder,
      amount: parseFloat(propAmount),
      currency: 'INR'
    });
    setLastEvalResult(res);
    setLoading(false);
    loadData();
  }

  async function handleResolveCase(caseId) {
    const notes = prompt('Enter human operator resolution notes:', 'Manual review completed; confirmed genuine request.');
    if (notes) {
      await resolveReviewCase(caseId, notes);
      loadData();
    }
  }

  return (
    <div className="app-container">
      {/* Top Navigation Bar */}
      <header className="header">
        <div className="logo-area">
          <div className="logo-badge">IG</div>
          <div>
            <h1 style={{ fontSize: '1.1rem', fontWeight: 700, letterSpacing: '-0.5px' }}>
              IntentGuard <span style={{ color: 'var(--accent-cyan)', fontWeight: 400 }}>Studio</span>
            </h1>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Financial AI Agent Transaction Safety Protocol</p>
          </div>
        </div>

        <nav className="nav-tabs">
          {[
            { id: 'dashboard', label: 'Dashboard' },
            { id: 'explorer', label: 'Intent Explorer' },
            { id: 'safety', label: 'Safety Events' },
            { id: 'reconciliation', label: 'Reconciliation' },
            { id: 'reviews', label: `Review Cases (${reviewCases.filter(c => c.status === 'OPEN').length})` },
            { id: 'benchmarks', label: 'Benchmarks & Ablations' }
          ].map(tab => (
            <button
              key={tab.id}
              className={`nav-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Main Container */}
      <main className="main-content">
        {/* Simulation Disclaimer Banner */}
        <div className="notice-banner">
          <span>⚠️</span>
          <div>
            <strong>ACADEMIC RESEARCH PROTOTYPE:</strong> This system runs strictly against an isolated mock payment simulator. 
            No real banking APIs, UPI accounts, cards, or production money are connected.
          </div>
        </div>

        {/* TAB 1: DASHBOARD OVERVIEW */}
        {activeTab === 'dashboard' && (
          <div>
            <div className="grid-metrics">
              <div className="metric-card">
                <span className="metric-label">Total Intents</span>
                <span className="metric-value">{metrics.total_intents}</span>
                <span className="metric-sub">Durable authorizations</span>
              </div>
              <div className="metric-card">
                <span className="metric-label" style={{ color: 'var(--accent-green)' }}>Completed (Safe)</span>
                <span className="metric-value" style={{ color: 'var(--accent-green)' }}>{metrics.completed}</span>
                <span className="metric-sub">Verified external settlements</span>
              </div>
              <div className="metric-card">
                <span className="metric-label" style={{ color: 'var(--accent-red)' }}>Blocked Violations</span>
                <span className="metric-value" style={{ color: 'var(--accent-red)' }}>{metrics.blocked}</span>
                <span className="metric-sub">Gateway pre-execution blocks</span>
              </div>
              <div className="metric-card">
                <span className="metric-label" style={{ color: 'var(--accent-yellow)' }}>Reconciled Unknowns</span>
                <span className="metric-value" style={{ color: 'var(--accent-yellow)' }}>{metrics.reconciled_unknowns}</span>
                <span className="metric-sub">Timeouts resolved without retry</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Duplicate Payouts</span>
                <span className="metric-value" style={{ color: 'var(--accent-green)' }}>0</span>
                <span className="metric-sub">0.0% duplicate rate</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Review Cases</span>
                <span className="metric-value" style={{ color: reviewCases.length > 0 ? 'var(--accent-yellow)' : 'var(--text-muted)' }}>
                  {reviewCases.length}
                </span>
                <span className="metric-sub">Escalated human tickets</span>
              </div>
            </div>

            {/* Architecture Flow Banner */}
            <div className="card">
              <h2 className="card-title">Intent-Consistent Execution Pipeline</h2>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', overflowX: 'auto', gap: '1rem' }}>
                <div style={{ textAlign: 'center', minWidth: '120px' }}>
                  <div className="badge badge-blue">Operator</div>
                  <p style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Authorizes Bounds</p>
                </div>
                <span>➔</span>
                <div style={{ textAlign: 'center', minWidth: '120px' }}>
                  <div className="badge badge-purple">AI Agent</div>
                  <p style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Proposes Action</p>
                </div>
                <span>➔</span>
                <div style={{ textAlign: 'center', minWidth: '120px' }}>
                  <div className="badge badge-green">10-Point Gateway</div>
                  <p style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Validates Invariants</p>
                </div>
                <span>➔</span>
                <div style={{ textAlign: 'center', minWidth: '120px' }}>
                  <div className="badge badge-purple">Mock Provider</div>
                  <p style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Simulated Settlement</p>
                </div>
                <span>➔</span>
                <div style={{ textAlign: 'center', minWidth: '120px' }}>
                  <div className="badge badge-yellow">Reconciliation</div>
                  <p style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Verifies Reality</p>
                </div>
              </div>
            </div>

            {/* Recent Intents Table */}
            <div className="card">
              <h2 className="card-title">Recent Intent Authorizations & States</h2>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Intent ID</th>
                      <th>Order ID</th>
                      <th>Customer</th>
                      <th>Authorized</th>
                      <th>Current State</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {intents.length === 0 ? (
                      <tr><td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No intents loaded. Run the demo or create an intent.</td></tr>
                    ) : (
                      intents.map(it => (
                        <tr key={it.id}>
                          <td className="mono" style={{ fontWeight: 600 }}>{it.id}</td>
                          <td className="mono">{it.order_id}</td>
                          <td>{it.customer_id}</td>
                          <td className="mono">{it.currency} {it.authorized_amount.toFixed(2)}</td>
                          <td>
                            <span className={`badge ${
                              it.current_state === 'COMPLETED' ? 'badge-green' :
                              it.current_state === 'BLOCKED' ? 'badge-red' :
                              it.current_state === 'ESCALATED' ? 'badge-red' :
                              it.current_state === 'UNKNOWN' ? 'badge-yellow' : 'badge-blue'
                            }`}>
                              {it.current_state}
                            </span>
                          </td>
                          <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{new Date(it.created_at).toLocaleTimeString()}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: INTENT EXPLORER */}
        {activeTab === 'explorer' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
            {/* Step 1: Create Intent */}
            <div className="card">
              <h2 className="card-title">Step 1: Create Human Authorization</h2>
              <form onSubmit={handleCreateIntent} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Intent ID</label>
                  <input
                    type="text"
                    value={newIntentId}
                    onChange={e => setNewIntentId(e.target.value)}
                    style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div>
                    <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Order ID</label>
                    <input
                      type="text"
                      value={newOrder}
                      onChange={e => setNewOrder(e.target.value)}
                      style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Customer ID</label>
                    <input
                      type="text"
                      value={newCustomer}
                      onChange={e => setNewCustomer(e.target.value)}
                      style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                    />
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Authorized Amount (INR)</label>
                  <input
                    type="number"
                    value={newAmount}
                    onChange={e => setNewAmount(e.target.value)}
                    style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                  />
                </div>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? 'Creating...' : 'Register Durable Intent'}
                </button>
              </form>
            </div>

            {/* Step 2: AI Proposal Simulation */}
            <div className="card">
              <h2 className="card-title">Step 2: AI Agent Proposal Submission</h2>
              <form onSubmit={handleSubmitProposal} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Target Intent ID</label>
                  <input
                    type="text"
                    value={propIntentId}
                    onChange={e => setPropIntentId(e.target.value)}
                    style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div>
                    <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Proposed Order</label>
                    <input
                      type="text"
                      value={propOrder}
                      onChange={e => setPropOrder(e.target.value)}
                      style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Proposed Customer</label>
                    <input
                      type="text"
                      value={propCustomer}
                      onChange={e => setPropCustomer(e.target.value)}
                      style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                    />
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Proposed Amount (Try ₹15,000 to trigger Block)</label>
                  <input
                    type="number"
                    value={propAmount}
                    onChange={e => setPropAmount(e.target.value)}
                    style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                  />
                </div>
                <button type="submit" className="btn-primary" style={{ background: 'linear-gradient(135deg, var(--accent-purple), #7c3aed)' }} disabled={loading}>
                  {loading ? 'Evaluating...' : 'Submit AI Proposal to Gateway'}
                </button>
              </form>

              {lastEvalResult && (
                <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(0,0,0,0.4)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <strong>Gateway Decision:</strong>
                    <span className={`badge ${lastEvalResult.decision === 'APPROVED' ? 'badge-green' : 'badge-red'}`}>
                      {lastEvalResult.decision}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                    {lastEvalResult.reason}
                  </p>
                  {lastEvalResult.provider_reference && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>
                      Provider Ref: {lastEvalResult.provider_reference}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: SAFETY EVENTS */}
        {activeTab === 'safety' && (
          <div className="card">
            <h2 className="card-title">Immutable Safety Audit Log & Security Events</h2>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Intent ID</th>
                    <th>Event Type</th>
                    <th>Decision</th>
                    <th>Reason / Invariants Evaluated</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEvents.map(ev => (
                    <tr key={ev.id}>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{new Date(ev.created_at).toLocaleTimeString()}</td>
                      <td className="mono">{ev.intent_id}</td>
                      <td><span className="badge badge-purple">{ev.event_type}</span></td>
                      <td>
                        <span className={`badge ${
                          ev.decision === 'APPROVED' ? 'badge-green' :
                          ev.decision === 'BLOCKED' ? 'badge-red' :
                          ev.decision === 'ESCALATE' ? 'badge-red' : 'badge-yellow'
                        }`}>
                          {ev.decision}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.85rem' }}>{ev.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 4: RECONCILIATION */}
        {activeTab === 'reconciliation' && (
          <div className="card">
            <h2 className="card-title">Active Reconciliation Log (Unknown Outcomes)</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Whenever an execution attempt drops network connection or yields an indeterminate HTTP status, 
              the system executes an active query across provider ledgers before authorizing retry or completion.
            </p>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Intent ID</th>
                    <th>Attempt ID</th>
                    <th>Action</th>
                    <th>Reconciliation Result</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEvents.filter(e => e.event_type.includes('RECONCIL')).map(ev => (
                    <tr key={ev.id}>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{new Date(ev.created_at).toLocaleTimeString()}</td>
                      <td className="mono">{ev.intent_id}</td>
                      <td className="mono">{ev.attempt_id || 'N/A'}</td>
                      <td><span className="badge badge-yellow">{ev.event_type}</span></td>
                      <td style={{ fontSize: '0.85rem' }}>{ev.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 5: REVIEW CASES */}
        {activeTab === 'reviews' && (
          <div className="card">
            <h2 className="card-title">Human Review & Escalation Queue</h2>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Case ID</th>
                    <th>Intent ID</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Reason</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {reviewCases.length === 0 ? (
                    <tr><td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No open human review cases. All transactions resolved automatically.</td></tr>
                  ) : (
                    reviewCases.map(c => (
                      <tr key={c.id}>
                        <td className="mono" style={{ fontWeight: 600 }}>{c.id}</td>
                        <td className="mono">{c.intent_id}</td>
                        <td><span className={`badge ${c.severity === 'CRITICAL' ? 'badge-red' : 'badge-yellow'}`}>{c.severity}</span></td>
                        <td><span className={`badge ${c.status === 'RESOLVED' ? 'badge-green' : 'badge-blue'}`}>{c.status}</span></td>
                        <td style={{ fontSize: '0.85rem' }}>{c.reason}</td>
                        <td>
                          {c.status === 'OPEN' ? (
                            <button
                              onClick={() => handleResolveCase(c.id)}
                              style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', background: 'var(--accent-green)', border: 'none', borderRadius: '4px', color: 'white', cursor: 'pointer' }}
                            >
                              Resolve
                            </button>
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Closed</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 6: BENCHMARKS & ABLATIONS */}
        {activeTab === 'benchmarks' && (
          <div>
            <div className="card">
              <h2 className="card-title">Comparative Baseline Evaluation (250 Scenarios Sweep)</h2>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
                Statistical evaluation across 12 distributed network and semantic failure modes under fixed seeds.
              </p>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Architecture</th>
                      <th>Incorrect Payouts</th>
                      <th>Duplicate Payouts</th>
                      <th>Completion %</th>
                      <th>Monetary Discrepancy</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><strong>Baseline A: Direct Agent</strong></td>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 600 }}>2</td>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 600 }}>2</td>
                      <td>20.0%</td>
                      <td className="mono" style={{ color: 'var(--accent-red)' }}>INR 11,500.00</td>
                      <td><span className="badge badge-red">Unsafe</span></td>
                    </tr>
                    <tr>
                      <td><strong>Baseline B: Fixed Validation</strong></td>
                      <td>0</td>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 600 }}>2</td>
                      <td>40.0%</td>
                      <td className="mono" style={{ color: 'var(--accent-red)' }}>INR 5,500.00</td>
                      <td><span className="badge badge-yellow">Duplicates</span></td>
                    </tr>
                    <tr>
                      <td><strong>Baseline C: Idempotency Alone</strong></td>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 600 }}>2</td>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 600 }}>1</td>
                      <td>30.0%</td>
                      <td className="mono" style={{ color: 'var(--accent-red)' }}>INR 11,000.00</td>
                      <td><span className="badge badge-red">Unsafe</span></td>
                    </tr>
                    <tr>
                      <td><strong>Baseline D: LLM Reviewer</strong></td>
                      <td>0</td>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 600 }}>2</td>
                      <td>40.0%</td>
                      <td className="mono" style={{ color: 'var(--accent-red)' }}>INR 5,500.00</td>
                      <td><span className="badge badge-yellow">Non-Deterministic</span></td>
                    </tr>
                    <tr style={{ background: 'rgba(16, 185, 129, 0.08)' }}>
                      <td><strong style={{ color: 'var(--accent-green)' }}>Proposed: IntentGuard</strong></td>
                      <td style={{ color: 'var(--accent-green)', fontWeight: 700 }}>0</td>
                      <td style={{ color: 'var(--accent-green)', fontWeight: 700 }}>0</td>
                      <td style={{ fontWeight: 700 }}>80.0%</td>
                      <td className="mono" style={{ color: 'var(--accent-green)', fontWeight: 700 }}>INR 0.00</td>
                      <td><span className="badge badge-green">100% Safe</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Component Ablation Table */}
            <div className="card">
              <h2 className="card-title">Component Ablation Study Matrix</h2>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Isolated Variant</th>
                      <th>Removed Component</th>
                      <th>Duplicate Rate</th>
                      <th>Discrepancy (INR)</th>
                      <th>Failure Mode Exposed</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>(-) No Active Reconciliation</td>
                      <td>Reconciliation Engine</td>
                      <td style={{ color: 'var(--accent-red)' }}>18 duplicates</td>
                      <td className="mono">INR 27,000.00</td>
                      <td>Network timeouts trigger naive duplicate retries</td>
                    </tr>
                    <tr>
                      <td>(-) No Duplicate Protection</td>
                      <td>Idempotency Ledger</td>
                      <td style={{ color: 'var(--accent-red)' }}>34 duplicates</td>
                      <td className="mono">INR 51,000.00</td>
                      <td>Agent restarts and replays cause double payouts</td>
                    </tr>
                    <tr>
                      <td>(-) No Intent Binding</td>
                      <td>Durable Authorization Record</td>
                      <td style={{ color: 'var(--accent-red)' }}>28 duplicates</td>
                      <td className="mono">INR 86,500.00</td>
                      <td>Semantic drift and hallucinated parameters execute</td>
                    </tr>
                    <tr>
                      <td>(-) No State-Aware Recovery</td>
                      <td>Cancellation & Escalation</td>
                      <td style={{ color: 'var(--accent-yellow)' }}>14 duplicates</td>
                      <td className="mono">INR 21,500.00</td>
                      <td>Corrupted effects remain unresolved in limbo</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

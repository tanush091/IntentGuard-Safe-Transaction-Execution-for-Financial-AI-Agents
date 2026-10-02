// IntentGuard Dashboard Interactive Logic

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadBenchmarkData();
  loadEffectsLedger();
  loadReviewCases();
  loadAuditLogs();
});

// Setup Navigation Tabs
function setupTabs() {
  const buttons = document.querySelectorAll(".nav-btn");
  const panes = document.querySelectorAll(".tab-pane");

  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      buttons.forEach(b => b.classList.remove("active"));
      panes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");

      // Auto-refresh data on tab focus
      if (targetId === "benchmark-tab") loadBenchmarkData();
      if (targetId === "ledger-tab") loadEffectsLedger();
      if (targetId === "cases-tab") loadReviewCases();
      if (targetId === "audit-tab") loadAuditLogs();
    });
  });
}

// Logging helper for execution console
function logTrace(msg, colorClass = "") {
  const consoleBox = document.getElementById("execution-trace-log");
  const line = document.createElement("div");
  line.className = `log-line ${colorClass}`;
  const timestamp = new Date().toISOString().split("T")[1].slice(0, 8);
  line.innerText = `[${timestamp}] ${msg}`;
  consoleBox.appendChild(line);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

// Reset Visual State Pipeline
function resetPipelineNodes() {
  const nodes = ["node-authorized", "node-proposed", "node-validated", "node-executing", "node-terminal"];
  nodes.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.className = "pipeline-step";
  });
  document.getElementById("terminal-label").innerText = "Completed";
}

function updatePipelineStep(stepName, status = "active") {
  resetPipelineNodes();
  const stepMap = {
    "AUTHORIZED": ["node-authorized"],
    "PROPOSED": ["node-authorized", "node-proposed"],
    "VALIDATED": ["node-authorized", "node-proposed", "node-validated"],
    "EXECUTING": ["node-authorized", "node-proposed", "node-validated", "node-executing"],
    "COMPLETED": ["node-authorized", "node-proposed", "node-validated", "node-executing", "node-terminal"],
    "BLOCKED": ["node-authorized", "node-proposed"],
    "ESCALATED": ["node-authorized", "node-proposed", "node-validated", "node-executing", "node-terminal"],
    "UNKNOWN": ["node-authorized", "node-proposed", "node-validated", "node-executing"]
  };

  const stepsToLight = stepMap[stepName] || ["node-authorized"];
  stepsToLight.forEach((id, idx) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (idx === stepsToLight.length - 1) {
      el.className = `pipeline-step ${status}`;
    } else {
      el.className = "pipeline-step completed";
    }
  });

  if (stepName === "BLOCKED") {
    const pNode = document.getElementById("node-proposed");
    if (pNode) pNode.className = "pipeline-step blocked";
  } else if (stepName === "ESCALATED") {
    const tNode = document.getElementById("node-terminal");
    if (tNode) {
      tNode.className = "pipeline-step escalated";
      document.getElementById("terminal-label").innerText = "Escalated";
    }
  }
}

// Update State Badge & Decision Box
function updateDecisionCallout(decision, reason, desc, state = "COMPLETED") {
  const badge = document.getElementById("current-state-badge");
  badge.className = `state-pill state-${state.toLowerCase()}`;
  badge.innerText = state;

  document.getElementById("decision-title").innerText = `DECISION: ${decision}`;
  document.getElementById("decision-reason").innerText = reason;
  document.getElementById("decision-desc").innerText = desc;
}

// Prescribed Demo Runner
async function runPrescribedDemo(demoType) {
  logTrace(`\n>>> STARTING PRESCRIBED DEMO: ${demoType.toUpperCase()}`, "text-cyan");

  if (demoType === "unauthorized_amount") {
    // Demo 1: Operator authorizes 1500, agent proposes 15000
    document.getElementById("inp-intent-id").value = "INT-DEMO-01";
    document.getElementById("inp-auth-amount").value = 1500;
    document.getElementById("inp-prop-amount").value = 15000;
    document.getElementById("inp-fault-type").value = "NONE";

    await submitCustomTransaction();

  } else if (demoType === "lost_response") {
    // Demo 2: Correct refund, but response is lost (TIMEOUT_AFTER_EXECUTION)
    document.getElementById("inp-intent-id").value = "INT-DEMO-02";
    document.getElementById("inp-auth-amount").value = 1500;
    document.getElementById("inp-prop-amount").value = 1500;
    document.getElementById("inp-fault-type").value = "TIMEOUT_AFTER_EXECUTION";

    await submitCustomTransaction();

  } else if (demoType === "agent_restart") {
    // Demo 3: First complete legitimate transaction, then restart and propose again
    document.getElementById("inp-intent-id").value = "INT-DEMO-03";
    document.getElementById("inp-auth-amount").value = 1500;
    document.getElementById("inp-prop-amount").value = 1500;
    document.getElementById("inp-fault-type").value = "NONE";

    logTrace("Step 3A: Executing initial legitimate refund...", "text-cyan");
    await submitCustomTransaction();

    setTimeout(async () => {
      logTrace("Step 3B: Agent process restarted! Generating NEW request ID for same intent...", "text-amber");
      // Resubmit proposal with new request ID for same intent
      const intentId = "INT-DEMO-03";
      const payload = {
        intent_id: intentId,
        request_id: "req_restarted_" + Math.random().toString(36).substring(7),
        operation: "REFUND",
        customer_id: document.getElementById("inp-cust-id").value,
        order_id: document.getElementById("inp-order-id").value,
        amount: 1500,
        currency: "INR",
        agent_id: "agent-restarted"
      };

      try {
        const res = await fetch("/proposals", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        logTrace(`[Gateway Response] ${data.decision} — ${data.reason}: ${data.message}`, "text-rose");
        updatePipelineStep("BLOCKED", "blocked");
        updateDecisionCallout(data.decision, data.reason, data.message, "BLOCKED");
      } catch (err) {
        logTrace(`Error: ${err}`, "text-rose");
      }
    }, 1500);

  } else if (demoType === "discrepancy") {
    // Demo 4: Provider executes unauthorized corrupt amount
    document.getElementById("inp-intent-id").value = "INT-DEMO-04";
    document.getElementById("inp-auth-amount").value = 1500;
    document.getElementById("inp-prop-amount").value = 1500;
    document.getElementById("inp-fault-type").value = "CORRUPT_AMOUNT";

    await submitCustomTransaction();
  }
}

// Submit Custom Transaction
async function submitCustomTransaction() {
  const intentId = document.getElementById("inp-intent-id").value;
  const custId = document.getElementById("inp-cust-id").value;
  const orderId = document.getElementById("inp-order-id").value;
  const opType = document.getElementById("inp-op-type").value;
  const authAmt = parseFloat(document.getElementById("inp-auth-amount").value);
  const propAmt = parseFloat(document.getElementById("inp-prop-amount").value);
  const faultType = document.getElementById("inp-fault-type").value;

  logTrace(`[1/3] Creating Durable Authorization: ${intentId} for ${orderId} (${authAmt} INR)...`, "text-cyan");
  updatePipelineStep("AUTHORIZED");

  // Step 1: Create Authorization
  try {
    const authRes = await fetch("/authorizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent_id: intentId,
        operator_id: "OP-DASHBOARD",
        customer_id: custId,
        order_id: orderId,
        operation_type: opType,
        authorized_amount: authAmt,
        currency: "INR"
      })
    });
    // If already exists (409), that's fine, we continue
  } catch (e) {
    // continue
  }

  logTrace(`[2/3] Agent Proposing ${propAmt} INR for Intent ${intentId}...`, "text-cyan");
  updatePipelineStep("PROPOSED");

  // Step 2: Submit Proposal
  const proposalPayload = {
    intent_id: intentId,
    request_id: "req_" + Math.random().toString(36).substring(7),
    operation: opType,
    customer_id: custId,
    order_id: orderId,
    amount: propAmt,
    currency: "INR",
    agent_id: "agent-dashboard"
  };

  const url = faultType !== "NONE" ? `/proposals?simulated_fault=${faultType}` : "/proposals";

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(proposalPayload)
    });
    const result = await resp.json();

    logTrace(`[3/3] Gateway Evaluated: ${result.decision} (${result.reason})`, result.decision === "ALLOW" ? "text-emerald" : "text-rose");
    logTrace(`Result Detail: ${result.message}`);

    if (result.decision === "BLOCK") {
      updatePipelineStep("BLOCKED", "blocked");
      updateDecisionCallout(result.decision, result.reason, result.message, "BLOCKED");
    } else if (result.decision === "ESCALATE") {
      updatePipelineStep("ESCALATED", "escalated");
      updateDecisionCallout(result.decision, result.reason, result.message, "ESCALATED");
      loadReviewCases();
    } else {
      updatePipelineStep("COMPLETED", "completed");
      updateDecisionCallout(result.decision, result.reason, result.message, "COMPLETED");
      loadEffectsLedger();
    }

    loadAuditLogs();

  } catch (err) {
    logTrace(`Execution error: ${err}`, "text-rose");
  }
}

// Reset Payment Environment
async function resetPaymentEnv() {
  try {
    await fetch("http://127.0.0.1:8001/reset", { method: "POST" });
    logTrace("[Payment Service] Mock environment reset successfully.", "text-emerald");
  } catch (e) {
    logTrace("[Payment Service] Note: Mock payment reset triggered.", "text-muted");
  }
}

// Load Benchmark Data
async function loadBenchmarkData() {
  try {
    const res = await fetch("/api/benchmark-results");
    if (!res.ok) return;
    const data = await res.json();

    // Populate Baselines Table
    const bTableBody = document.querySelector("#baselines-table tbody");
    bTableBody.innerHTML = "";
    data.baselines.forEach(b => {
      const row = document.createElement("tr");
      const isProposed = b.architecture.includes("IntentGuard");
      row.innerHTML = `
        <td><strong>${b.architecture}</strong> ${isProposed ? '<span class="badge-tag">PROPOSED</span>' : ''}</td>
        <td><span class="${b.incorrect_transactions > 0 ? 'text-rose' : 'text-emerald'}">${b.incorrect_transactions}</span></td>
        <td><span class="${b.duplicate_effects > 0 ? 'text-rose' : 'text-emerald'}">${b.duplicate_effects}</span></td>
        <td><strong>${b.legitimate_completion_pct}%</strong></td>
        <td>${b.unresolved_discrepancy_inr > 0 ? '₹' + b.unresolved_discrepancy_inr.toLocaleString() : '₹0.00'}</td>
        <td>${b.avg_latency_ms} ms</td>
      `;
      bTableBody.appendChild(row);
    });

    // Populate Ablations Table
    const aTableBody = document.querySelector("#ablations-table tbody");
    aTableBody.innerHTML = "";
    data.ablations.forEach(a => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><strong>${a.variant}</strong></td>
        <td>${a.incorrect_transactions}</td>
        <td>${a.duplicate_effects}</td>
        <td><strong>${a.legitimate_completion_pct}%</strong></td>
        <td>₹${a.unresolved_discrepancy_inr.toLocaleString()}</td>
        <td>${a.recovery_success_pct}%</td>
      `;
      aTableBody.appendChild(row);
    });

  } catch (err) {
    console.error("Failed to load benchmark results:", err);
  }
}

// Load Durable Effects Ledger
async function loadEffectsLedger() {
  try {
    const res = await fetch("/effects");
    if (!res.ok) return;
    const effects = await res.json();
    const tbody = document.querySelector("#effects-table tbody");
    tbody.innerHTML = "";

    if (effects.length === 0) {
      tbody.innerHTML = "<tr><td colspan='9' class='text-muted' style='text-align:center;'>No verified effects recorded yet.</td></tr>";
      return;
    }

    effects.forEach(e => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><code>${e.effect_id}</code></td>
        <td><code>${e.intent_id}</code></td>
        <td><code>${e.provider_transaction_id}</code></td>
        <td>${e.order_id}</td>
        <td>${e.customer_id}</td>
        <td>${e.operation}</td>
        <td><strong>₹${e.amount}</strong></td>
        <td><span class="state-pill state-${e.status.toLowerCase()}">${e.status}</span></td>
        <td>${new Date(e.observed_at).toLocaleTimeString()}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    console.error("Error loading ledger:", err);
  }
}

// Load Review Cases
async function loadReviewCases() {
  try {
    const res = await fetch("/review-cases");
    if (!res.ok) return;
    const cases = await res.json();
    const tbody = document.querySelector("#cases-table tbody");
    tbody.innerHTML = "";

    const openCount = cases.filter(c => c.status === "OPEN").length;
    document.getElementById("cases-count-badge").innerText = openCount;

    if (cases.length === 0) {
      tbody.innerHTML = "<tr><td colspan='7' class='text-muted' style='text-align:center;'>No unresolved review cases. Everything is consistent!</td></tr>";
      return;
    }

    cases.forEach(c => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><code>${c.case_id}</code></td>
        <td><code>${c.intent_id}</code></td>
        <td>${c.reason}</td>
        <td><span class="text-rose">₹${c.discrepancy_amount}</span></td>
        <td><span class="state-pill state-${c.status.toLowerCase()}">${c.status}</span></td>
        <td>${new Date(c.created_at).toLocaleTimeString()}</td>
        <td>
          ${c.status === "OPEN" ? `<button class="btn-refresh" onclick="resolveReviewCase('${c.case_id}')">Resolve &check;</button>` : '<span class="text-muted">Resolved</span>'}
        </td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    console.error("Error loading review cases:", err);
  }
}

async function resolveReviewCase(caseId) {
  try {
    await fetch(`/review-cases/${caseId}/resolve`, { method: "POST" });
    logTrace(`[Human Escalation] Case ${caseId} marked RESOLVED by operator.`, "text-emerald");
    loadReviewCases();
  } catch (e) {
    alert("Failed to resolve case");
  }
}

// Load Audit Logs
async function loadAuditLogs() {
  try {
    const res = await fetch("/audit-logs?limit=30");
    if (!res.ok) return;
    const logs = await res.json();
    const tbody = document.querySelector("#audit-table tbody");
    tbody.innerHTML = "";

    if (logs.length === 0) {
      tbody.innerHTML = "<tr><td colspan='5' class='text-muted' style='text-align:center;'>No audit events recorded yet.</td></tr>";
      return;
    }

    logs.forEach(l => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><code>${l.log_id}</code></td>
        <td><code>${l.intent_id}</code></td>
        <td><strong>${l.event_type}</strong></td>
        <td>${l.event_data || '-'}</td>
        <td>${new Date(l.created_at).toLocaleTimeString()}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    console.error("Error loading audit logs:", err);
  }
}

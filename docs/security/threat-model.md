# Threat model

IntentGuard is a research prototype against a simulated provider. This document states what the
protocol assumes, what it guarantees, and what it does not cover.

## The agent is an untrusted caller

The AI agent may be wrong, in ways that are honest or adversarial:

- hallucinated or mis-scaled amounts (×10, rupees read as paise), wrong currency;
- near-miss identifiers (`ORD-2041` / `ORD-2014` / `ORD-2401`), the wrong customer;
- repeats after timeouts; restarts that re-derive the operation with a new request ID;
- several agent instances working the same ticket at once;
- prompt injection in the ticket text that steers the extracted proposal.

The protocol does not try to make the agent correct. It makes the agent's output **irrelevant
unless it matches a durable operator authorization**, and it makes the gateway, not the agent,
the only party that submits, retries or reverses anything.

## Isolation

| Boundary | How it is enforced in this repository |
|---|---|
| Credentials | The agent holds no provider credentials. The gateway is the only component configured with the provider URL (`PAYMENT_SERVICE_URL`) |
| Network path | The agent's only interface is the gateway's proposal and agent endpoints. The agent endpoint runs extraction inside the gateway and submits through the same engine path |
| Code path | Only `IntentGuard._execute`, `recover` and `_maybe_retry` call the provider adapter, always with parameters from a recorded attempt or a re-read effect |
| LLM | An LLM is only an extractor: ticket text in, structured fields out. It has no tools and cannot call the provider |

In the Docker setup all services share one network, so isolation of an *external* agent process
from the provider would have to come from deployment (network policy, credentials held only by the
gateway). That is not demonstrated here.

## Invariants

| # | Invariant | Enforced by | Checked by |
|---|---|---|---|
| I1 | A proposal executes only if operation, customer, order, currency and amount equal the intent, and the operator is still active and permitted | `checks.binding_findings`, `authority_findings` | `test_protocol_spec.py`, `test_ablations.py` |
| I2 | At most one live intended effect per intent | Stable key `ig-<intent>-g<n>`; state gate; serialized decide+reserve; partial unique index | Concurrency tests (2/4/8 agents); property P1 |
| I3 | Live order total never exceeds the order value | `BALANCE_EXCEEDED` check across intents; provider's own balance check | Provider side: `test_balance_and_ownership_are_enforced_by_the_provider`. The gateway's `BALANCE_EXCEEDED` check has no dedicated test |
| I4 | An attempt is durable before the provider is called | `_reserve` commits `SUBMITTING` before `_execute` | Crash tests at both injection points |
| I5 | An unknown outcome is never treated as failure; absence counts only after the absence window and a successful search | `reconcile` | `test_timeout_marks_unknown_and_never_retries_blindly`, absence-window ablation test |
| I6 | `COMPLETED` is reported only when exactly the intended effect is observed at the provider | `_derive` uses effects only | Property P3 |
| I7 | A reversal is reported only after the provider confirms `CANCELLED` | `recover` read-back | `test_incorrect_completed_refund_is_escalated_not_reported_reversed`, recovery ablation test |
| I8 | Every live unintended effect is either reversed or escalated with its amount | `recover`, review cases | Property P2, P4 |
| I9 | History cannot be rewritten undetected | Append-only triggers, per-intent hash chain, `UNIQUE(chain_id, prev_hash)` | `test_audit_log_is_append_only_and_tamper_evident`; property P5 |

## Not covered

- **No authentication or authorization on either API.** Anyone who can reach the gateway can
  create operators, approve intents under any `operator_id`, resolve reviews and inject faults
  into the provider. Operator identity is a request field, not a verified principal.
- **Compromised gateway or database.** The gateway is trusted. The audit chain detects rewriting
  after the fact; it does not prevent a privileged attacker from appending false events.
- **Provider honesty.** The gateway trusts the provider's lookup and ledger as ground truth.
- **Secrets.** `.env` is gitignored and `.env.example` holds no secrets. Never put real payment
  credentials in either; the system only talks to the simulator.
- **Denial of service and rate limiting.** Not addressed.
- **Multi-gateway deployments.** Leases and row locks are designed for it, but running several
  gateways against one database is not tested.
- **PostgreSQL-specific enforcement** (row locks, the PL/pgSQL audit trigger) exists in code but is
  not exercised by the automated tests.

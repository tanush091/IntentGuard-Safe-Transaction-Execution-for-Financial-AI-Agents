# Demo walkthrough

The dashboard runs the four prescribed demonstrations as one-click cards on the Overview page
(`frontend/src/components/ScenarioCards.jsx`; target: [../DESIGN.md](../DESIGN.md) section 5.7).
After them, a reviewer resolves the escalated case. Every step below can also be driven over the
HTTP API with `curl` (last section).

The outcomes shown were checked on 2026-10-10 by making the same API calls against the gateway
and provider services (provider settle delay 3 s, offline agent rules). Provider transaction and
order IDs differ from run to run.

## Setup

Start the stack ([running.md](running.md)) with `SIMULATOR_MODE=true` for the gateway and the
provider. `.env.example` and `docker-compose.yml` set it. The cards depend on the simulator-only
endpoints `POST /api/dev/orders`, `POST /api/dev/faults` and `GET /api/dev/ledger`; when they are
off, the Overview page shows "SIMULATOR_MODE is off, so the demo scenarios are disabled".

Open http://localhost:3000 and sign in. With `DEMO_SEED=true` (the default) the gateway seeds,
on first start (`backend/gateway_api/seed.py`):

| Account | Role | May authorize | Limit |
|---|---|---|---|
| `asha@intentguard.test` | operator | refunds and holds | ₹50,000 |
| `ravi@intentguard.test` | operator | refunds | ₹5,000 |
| `meera@intentguard.test` | reviewer | refunds and holds | ₹50,000 |
| `admin@intentguard.test` | admin | refunds and holds | ₹100,000 |
| `agent-support` | agent (service principal) | cannot log in; an admin issues it short-lived tokens scoped to intents or customers | |

The password of every human account is `DEMO_PASSWORD`, default `intentguard-demo`.

| Seeded order | Customer | Value |
|---|---|---|
| `ORD-204` | C-17 | ₹5,000 |
| `ORD-240` | C-17 | ₹12,000 (near-miss of ORD-204) |
| `ORD-2041` | C-71 | ₹20,000 (near-miss, other customer) |
| `ORD-311` | C-17 | ₹8,000 |

What each role sees: operators, reviewers and admins get Overview, Intents, Exceptions, Review
queue, Reconciliation, Audit and Experiments; admins also get Admin (users, agent tokens, policies,
provider connection). Only reviewers and admins see the buttons that resolve a review case, verify
the audit chain, run a matching pass or mark a mismatch handled. The server enforces the same rules
(`backend/gateway_api/security.py`); the dashboard only hides what would be refused.

**Sign in as Asha to run the cards.** Separation of duties is on by default: whoever authorizes an
intent cannot resolve its review case. The cards authorize as the signed-in user, so a card run by
Meera produces a case that only the admin can resolve.

## The four demo cards

Each card creates a fresh demo order (`POST /api/dev/orders`, an `ORD-9xxxxxxx` id registered with
both the gateway and the provider), so the cards can be run again. It then calls the public API
exactly as an operator and an agent would, writes each step to the Live console, and opens the
intent's detail page.

### 1. Unauthorized amount (safety barrier)

The card creates a ₹5,000 order for C-17, authorizes a ₹1,500 refund on it, and submits a ₹15,000
proposal as the agent.

Result: decision **`REJECT`**, reasons `AMOUNT_EXCEEDS_AUTHORIZATION` and `EXCEEDS_REMAINING_BALANCE`
(₹15,000 is also more than the order). The intent stays `AUTHORIZED`, no attempt is recorded, and
the provider ledger for the order is empty. On the detail page the pipeline marks Validated as
blocked, with the reason codes and the callout "No provider call was made for this proposal"; the
proposal is listed as Blocked (status `REJECTED`).

To try other errors, use the "Act as the agent" form on the same page: a near-miss order
(`ORD-240`) gives `ORDER_MISMATCH`, a different customer `CUSTOMER_MISMATCH`, a smaller amount
`AMOUNT_BELOW_AUTHORIZATION`. Submitting the authorized values afterwards is allowed.

### 2. Lost response (active reconciliation)

The card creates a ₹8,000 order, injects `TIMEOUT_AFTER_EXECUTION` for it, authorizes a ₹2,000
refund with the ticket "Please refund ₹2,000 on ORD-… for customer C-17", and runs the agent on the
ticket (`POST /api/intents/{id}/agent`; offline rules unless `LLM_PROVIDER` is set).

Result: decision **`ALLOW`**. The provider executed the refund but answered 504, so the attempt's
outcome is unknown. The gateway reconciled at once: it searched the order for a transaction carrying
the intent's id, found the refund and recorded it. It did not send a second refund.

```
AUTHORIZED -> IN_FLIGHT -> UNKNOWN -> EXECUTING -> COMPLETED
```

`EXECUTING` lasts until the provider settles the refund (3 s); the worker then sees it `COMPLETED`.
The ledger holds exactly one ₹2,000 refund. While an intent is `UNKNOWN` or `RECONCILING` the
dashboard labels it "Verifying", never "failed".

### 3. Agent restart (duplicate suppression)

The card creates a ₹12,000 order, authorizes a ₹1,200 refund, and submits the correct proposal
twice: first with request id `agent-run-1`, then unchanged with `agent-run-2-after-restart`, as a
restarted agent would.

Result: the first proposal is **`ALLOW`** (`EXECUTING`, provider transaction `rf_…`). The second is
**`DUPLICATE`** with reason `ALREADY_COMPLETED` and the same `provider_transaction_id`. The ledger
holds one refund, and the intent becomes `COMPLETED` when it settles. The provider idempotency key
is derived from the intent (`ig-<intent>-g0`), never from the agent's request id. No gateway
response includes it: intent, history, timeline and audit responses, and the simulator-only ledger
(`/api/dev/ledger`), all redact it.

### 4. Incorrect completed effect (human escalation)

The card creates a ₹20,000 order for C-71, injects `CORRUPT_AMOUNT` (factor 10) and
`FAILED_CANCELLATION` for it, authorizes a ₹1,000 refund, and runs the agent.

Result: decision **`ALLOW`**, intent **`ESCALATED`**:

```
AUTHORIZED -> IN_FLIGHT -> DISCREPANCY -> ESCALATED
```

The provider created a ₹10,000 refund. The gateway read it back, classified it `MISMATCH`, and tried
to cancel it while it was still pending; the provider refused (`cancellation_failed`). The gateway
opened review case **`CANCEL_REJECTED`** with **₹9,000.00** at stake (₹10,000 paid instead of
₹1,000). The wrong refund stays live and completes at the provider a few seconds later; nothing
reports it as reversed. The detail page shows "Unintended effect at provider ₹10,000.00", the effect
with class `MISMATCH`, and a chip linking to the open case.

## Resolving the escalated case

Sign out and sign in as Meera (reviewer). **Review queue** lists the open case: reason
`CANCEL_REJECTED`, ₹9,000.00 at stake. **Resolve ✓** opens a dialog with the resolution and a note
(appended to the audit log), then **Resolve case**.

- `ACCEPTED_AS_IS` is refused with `409 NO_VERIFIED_EFFECT`: no verified intended effect exists,
  only the wrong ₹10,000 refund. The dashboard shows `NO_VERIFIED_EFFECT` in a notification; the
  dialog and the case stay open.
- `WRITTEN_OFF` resolves the case (and any other open case of the intent) and closes the intent:
  state `CLOSED`, terminal. The ₹10,000 refund stays in the provider's ledger.
- `REFUND_RECOVERED_OUT_OF_BAND` is the alternative when the excess was recovered outside the
  system: the wrong refund is marked remediated (it no longer counts toward the intent), the key
  generation moves to 1, and the gateway retries. A second attempt pays the correct ₹1,000; the
  intent goes `EXECUTING`, then `COMPLETED`.

An operator gets `403 FORBIDDEN` (operators cannot resolve cases), and a reviewer or admin who
authorized the intent gets `403 SEPARATION_OF_DUTIES`. All five resolutions are
described in [../product/overview.md](../product/overview.md#what-a-reviewer-can-decide).

## The intent detail page

Open an intent from Recent intents on the Overview, from Intents, or from a card. From top to bottom:

- **Header**: id, state, "provider-verified" when the state is `COMPLETED`, `EXECUTING` or
  `CANCELLED`, and the open review case.
- **Summary**: operation, customer, order, authorized amount, amount counted toward the
  authorization, any unintended live effect at the provider, the authorizing operator, attempts and
  key generation, and the ticket.
- **Pipeline**: Authorized, Proposed, Validated, Executing, Outcome. A blocked proposal shows its
  reason codes with plain-language text; `UNKNOWN` and `RECONCILING` show a dashed "Verifying" node.
- **Act as the agent**: "Run agent on the ticket" (when the authorization has a ticket) and a
  structured proposal form.
- **AI investigator** (only for exceptions: `UNKNOWN`, `RECONCILING`, `DISCREPANCY`,
  `CANCEL_REQUESTED`, `ESCALATED`), marked "AI-generated · advisory". **Investigate** shows the
  classification, a summary, evidence references, the recommended action and the verdict of the
  deterministic policy gate (`backend/investigator/policy.py`). **Apply** is enabled only when the
  gate permits the action, and the gateway re-checks the gate on fresh evidence before acting. For
  card 4 the offline rules classify `AMOUNT_MISMATCH`. While the wrong refund is still pending they
  recommend `CANCEL_PENDING`, which the gate does not permit for an `ESCALATED` intent
  (`no_discrepancy_or_cancel_request`); once it has completed, a few seconds later, they recommend
  `ESCALATE`, which is not permitted either (`already_escalated`). Either way **Apply** stays
  disabled and the case stays with the reviewer.
- **Cancel**: an `AUTHORIZED` or `RECONCILING` intent (no live effect) is cancelled at once; a
  pending refund or a hold is cancelled at the provider and the cancellation verified first. A
  completed refund cannot be cancelled (`409 NOT_CANCELLABLE`), nor can an intent whose outcome is
  still unknown (`409 ATTEMPT_IN_PROGRESS`); `DISCREPANCY`, `CANCEL_REQUESTED` and `ESCALATED`
  answer `409 STATE_CONFLICT`.
- **Timeline**: the intent's audit chain as readable events (authorization, decisions, attempts,
  provider observations, state changes, reversals, review cases, investigations).
- **Attempts** (with a **Reconcile** button for an attempt that is `UNKNOWN` or `SUBMITTING`),
  **Effects at the provider** and **Proposals and decisions**.

**Exceptions** lists every intent in one of those exception states, each with the investigator
panel.

## Reconciliation

**Reconciliation** lists open mismatches and recent runs. Worker runs are recorded by the
background worker; **Run matching** (reviewer and admin) starts a matching run, which compares the
gateway's ledger with the provider order by order and records mismatches of kind `MISSING`,
`DUPLICATE`, `AMOUNT`, `ORDER` or `CUSTOMER`. A matching run never moves money, changes an intent or
resolves a mismatch; a reviewer marks each one **Handled**. Webhook events for transactions the
gateway cannot attribute also appear here. For example, if card 4's case was written off, the
₹10,000 refund is still live, and a matching run reports it as an `AMOUNT` mismatch.

## Audit

**Audit** searches the hash-chained log by intent, actor or kind; a row opens its full payload,
with provider idempotency keys and other secrets shown as `[redacted]`. **Verify chain** (reviewer
and admin, `GET /api/audit/verify`) recomputes every chain and shows "Chain verified ✓ (N
entries)" or "Chain broken at #seq". Reviewers and admins also see the same badge in the top bar,
re-checked every 30 seconds. Operators can read the log but not verify it.

## Experiments

**Experiments** shows `RESULTS_DIR/latest/summary.json` (`GET /api/experiments/latest`): run
metadata, every arm grouped into baselines, the proposed protocol and ablations with mean and 95%
confidence-interval half-width per metric (best value highlighted), a bar chart per metric, and
per-category results for one arm. The numbers come from the measured run; see
[../research/results.md](../research/results.md). Without a results file the page shows the command
that creates one.

## Driving the same scenarios with curl

Every call needs a bearer token from `POST /api/auth/login`. Access tokens last 15 minutes; an API
client also receives a `refresh_token` in the login body for `POST /api/auth/refresh`. Decisions
(`ALLOW`, `REJECT`, `DUPLICATE`, `HOLD_FOR_REVIEW`) are HTTP 200 bodies; errors use the envelope
`{"error": {"code", "message", "details", "request_id"}}`. Run in bash (Git Bash on Windows);
`python` extracts fields from the JSON responses.

```bash
G=http://127.0.0.1:8000/api
JSON='Content-Type: application/json'
field() { python -c "import json, sys; print(json.load(sys.stdin)['$1'])"; }
login() {
  curl -s -X POST $G/auth/login -H "$JSON" \
       -d "{\"email\": \"$1\", \"password\": \"intentguard-demo\"}" | field access_token
}
A="Authorization: Bearer $(login asha@intentguard.test)"
M="Authorization: Bearer $(login meera@intentguard.test)"
```

**1. Unauthorized amount**

```bash
ORDER=$(curl -s -X POST $G/dev/orders -H "$A" -H "$JSON" -d '{"customer_id": "C-17", "amount": "5000"}' | field order_id)
INTENT=$(curl -s -X POST $G/authorizations -H "$A" -H "$JSON" -d @- <<EOF | field intent_id
{"customer_id": "C-17", "order_id": "$ORDER", "operation": "REFUND", "authorized_amount": "1500.00", "currency": "INR"}
EOF
)
curl -s -X POST $G/intents/$INTENT/proposals -H "$A" -H "$JSON" -d @- <<EOF
{"operation": "REFUND", "customer_id": "C-17", "order_id": "$ORDER", "amount": "15000.00", "currency": "INR"}
EOF
# "decision": "REJECT", "reasons": ["AMOUNT_EXCEEDS_AUTHORIZATION", "EXCEEDS_REMAINING_BALANCE"],
# "state": "AUTHORIZED", "attempt_id": null
curl -s "$G/dev/ledger?order_id=$ORDER" -H "$A"        # []
```

**2. Lost response**

```bash
ORDER=$(curl -s -X POST $G/dev/orders -H "$A" -H "$JSON" -d '{"customer_id": "C-17", "amount": "8000"}' | field order_id)
curl -s -X POST $G/dev/faults -H "$A" -H "$JSON" -d "{\"kind\": \"TIMEOUT_AFTER_EXECUTION\", \"order_id\": \"$ORDER\"}"
INTENT=$(curl -s -X POST $G/authorizations -H "$A" -H "$JSON" -d @- <<EOF | field intent_id
{"customer_id": "C-17", "order_id": "$ORDER", "authorized_amount": "2000.00",
 "ticket_text": "Please refund INR 2000 on $ORDER for customer C-17"}
EOF
)
curl -s -X POST $G/intents/$INTENT/agent -H "$A" -H "$JSON" -d '{}'
# "decision": "ALLOW", "state": "EXECUTING", "extraction": {"source": "rules", "model": "offline-rules", ...}
curl -s $G/intents/$INTENT/timeline -H "$A"             # a few seconds later: ... UNKNOWN -> EXECUTING, EXECUTING -> COMPLETED
curl -s "$G/dev/ledger?order_id=$ORDER" -H "$A"        # one refund
```

**3. Agent restart**

```bash
ORDER=$(curl -s -X POST $G/dev/orders -H "$A" -H "$JSON" -d '{"customer_id": "C-17", "amount": "12000"}' | field order_id)
INTENT=$(curl -s -X POST $G/authorizations -H "$A" -H "$JSON" -d @- <<EOF | field intent_id
{"customer_id": "C-17", "order_id": "$ORDER", "authorized_amount": "1200.00"}
EOF
)
for RID in agent-run-1 agent-run-2-after-restart; do
  curl -s -X POST $G/intents/$INTENT/proposals -H "$A" -H "$JSON" -d @- <<EOF
{"request_id": "$RID", "operation": "REFUND", "customer_id": "C-17", "order_id": "$ORDER", "amount": "1200.00"}
EOF
  echo
done
# first: "ALLOW"; second: "DUPLICATE", "reason": "ALREADY_COMPLETED", same "provider_transaction_id"
```

**4. Incorrect completed effect, then the review**

```bash
ORDER=$(curl -s -X POST $G/dev/orders -H "$A" -H "$JSON" -d '{"customer_id": "C-71", "amount": "20000"}' | field order_id)
curl -s -X POST $G/dev/faults -H "$A" -H "$JSON" -d "{\"kind\": \"CORRUPT_AMOUNT\", \"order_id\": \"$ORDER\", \"params\": {\"factor\": 10}}"
curl -s -X POST $G/dev/faults -H "$A" -H "$JSON" -d "{\"kind\": \"FAILED_CANCELLATION\", \"order_id\": \"$ORDER\"}"
INTENT=$(curl -s -X POST $G/authorizations -H "$A" -H "$JSON" -d @- <<EOF | field intent_id
{"customer_id": "C-71", "order_id": "$ORDER", "authorized_amount": "1000.00",
 "ticket_text": "Refund INR 1000 for $ORDER to C-71"}
EOF
)
curl -s -X POST $G/intents/$INTENT/agent -H "$A" -H "$JSON" -d '{}'      # "decision": "ALLOW", "state": "ESCALATED"
CASE=$(curl -s $G/intents/$INTENT -H "$A" | field open_review_case_id)
curl -s $G/review-cases -H "$M"                       # "reason": "CANCEL_REJECTED", "discrepancy_amount": "9000.00"
curl -s -X POST $G/review-cases/$CASE/resolve -H "$M" -H "$JSON" -d '{"resolution": "ACCEPTED_AS_IS"}'
# 409 {"error": {"code": "NO_VERIFIED_EFFECT", ...}}
curl -s -X POST $G/review-cases/$CASE/resolve -H "$M" -H "$JSON" \
     -d '{"resolution": "WRITTEN_OFF", "note": "customer keeps the excess"}'
# {"case_id": "RC-…", "status": "RESOLVED", "resolution": "WRITTEN_OFF", "intent_state": "CLOSED"}
curl -s $G/audit/verify -H "$M"                       # {"valid": true, "entries_checked": …, "first_break": null}
```

Fault injection through `/api/dev/faults` is recorded in the audit log (`dev.fault_injected`). The
provider also accepts faults directly at `POST http://127.0.0.1:8001/v1/faults` (no
authentication, `SIMULATOR_MODE` only). Fault kinds: `OUTAGE`, `TIMEOUT_BEFORE_EXECUTION`,
`TIMEOUT_AFTER_EXECUTION`, `DELAYED_STATUS` (`settle_delay_s`), `DELAYED_VISIBILITY` (`lag_s`),
`CORRUPT_AMOUNT` (`factor`), `FAILED_CANCELLATION`, `LOOKUP_OUTAGE`, `WEBHOOK_DUPLICATE`,
`WEBHOOK_DELAY` (`delay_s`). A fault applies to its `order_id` (or to every order when omitted),
fires `times` times (default 1; `-1` until cleared with `DELETE /api/dev/faults`), and is then
consumed. The endpoints are listed in [../architecture/api.md](../architecture/api.md); the target
contract is [../API.md](../API.md).

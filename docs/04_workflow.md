# 04. Workflow

## Complete Transaction Execution Lifecycle

The IntentGuard protocol progresses through eight distinct stages from operator authorization to verified settlement.

---

### Step 1: Authorization Creation
1. An authorized human operator or upstream trusted billing engine generates an authorization request.
2. The authorization defines:
   - `intent_id`: Unique identifier (e.g., `INT-001`)
   - `operator_id`: Identity of the authorizing human (e.g., `OP-10`)
   - `customer_id`: Authorized recipient (e.g., `C-17`)
   - `order_id`: Associated business order (e.g., `ORD-204`)
   - `operation_type`: Specific allowed operation (`REFUND` or `PAYMENT_AUTHORIZE`)
   - `authorized_amount`: Maximum permitted amount (e.g., `1500.00`)
   - `currency`: Expected ISO-4217 currency code (e.g., `INR`)
3. The intent is persisted in the database in the `AUTHORIZED` state.

---

### Step 2: AI Proposal Generation
1. The AI Agent receives the customer ticket or prompt: *"Customer C-17 requests a refund for damaged goods on order ORD-204."*
2. The agent produces a structured JSON proposal matching the `AgentProposal` schema:
   ```json
   {
     "intent_id": "INT-001",
     "operation": "REFUND",
     "customer_id": "C-17",
     "order_id": "ORD-204",
     "amount": 1500,
     "currency": "INR"
   }
   ```
3. The proposal is submitted via API to `POST /api/proposals`.
4. Intent state advances to `PROPOSED`.

---

### Step 3: Safety Gateway Evaluation
The safety gateway executes 10 deterministic checks:
1. Customer ID match
2. Order ID match
3. Operation type match
4. Amount conformity (exact match or within limit)
5. Currency code match
6. Operator authorization validity
7. Duplicate completed effect check (has this intent already settled?)
8. Concurrent active attempt check (is another thread currently executing?)
9. Existing provider effect check (does provider already record this?)
10. Transaction state machine validity (is transition `PROPOSED → APPROVED` legal?)

- **Failure**: Gateway marks the intent `BLOCKED`, logs an immutable audit event with failure reason, and returns HTTP 403.
- **Success**: Gateway approves the proposal; state advances to `APPROVED`.

---

### Step 4: Execution Dispatch & Attempt Recording
1. An `Attempt` record is created in the database with status `SUBMITTED`, linking `intent_id` and an incremented `attempt_number`.
2. A deterministic idempotency key is generated (`idempotency_key = f"{intent_id}-att-{attempt_number}"`).
3. The gateway dispatches the HTTP request to the Mock Payment Service (`POST /refunds`).

---

### Step 5: External-State Observation & Branching
The gateway observes the HTTP response from the mock payment service:
- **Case A: Explicit Success (HTTP 200/201)**:
  - Provider returns `provider_reference` and status `COMPLETED`.
  - Effect record is recorded in the ledger.
  - Intent state transitions `SUBMITTED → COMPLETED`.
- **Case B: Explicit Failure (HTTP 400/404/422)**:
  - Provider indicates rejected parameters.
  - Attempt marked `FAILED`.
  - Intent state transitions `SUBMITTED → FAILED`.
- **Case C: Indeterminate Outcome (Timeout / Network Drop / HTTP 5xx)**:
  - Connection times out after `DEFAULT_TIMEOUT_SECONDS`.
  - Gateway does **NOT** retry immediately.
  - Attempt marked `UNKNOWN`.
  - Intent state transitions `SUBMITTED → UNKNOWN → RECONCILING`.

---

### Step 6: Active Reconciliation (When UNKNOWN)
1. The reconciliation engine queries the mock payment service:
   - `GET /refunds/{provider_reference}` (if reference exists)
   - `GET /refunds?order_id=ORD-204` (to inspect provider ledger for this order)
2. **Analysis of Observed External State**:
   - **Observed Provider Effect Matches Authorization**:
     The refund actually executed before the network dropped. Gateway captures the effect, marks the attempt `COMPLETED`, and resolves the intent as `COMPLETED`. (Avoided double-refund!).
   - **Observed Provider Has No Record of Transaction**:
     The request was dropped before processing. Controlled retry is permitted (`RECONCILING → RETRY_ALLOWED`).
   - **Observed Provider Has Unexpected / Corrupted Effect**:
     Effect has wrong amount or corrupted fields. Marked as `INCORRECT`.

---

### Step 7: State-Aware Recovery
- If an incorrect effect is detected:
  - The gateway initiates cancellation (`POST /refunds/{refund_id}/cancel`).
  - If cancellation succeeds: status moves to `CANCELLED`.
  - If cancellation is unsupported or rejected by provider: an immutable `ReviewCase` is created, and status transitions to `ESCALATED`.

---

### Step 8: Final Resolution & Audit Trail
Every step, check, outcome, and state transition appends an immutable entry to `audit_events`.

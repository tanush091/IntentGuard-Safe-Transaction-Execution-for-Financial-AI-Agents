> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# Test Plan (TEST_PLAN.md) — IntentGuard

## Definition of "Working"
The IntentGuard system is working if and only if:
1. Valid proposals matching authorizations execute and reach `COMPLETED` at the provider.
2. Unauthorized amounts (exceeding limit) or mutated order IDs are blocked pre-execution with zero provider effect.
3. Lost responses (timeout after execution) are actively reconciled against the provider and marked `COMPLETED` without duplicate charges.
4. Process restarts with altered request IDs are detected as duplicate attempts for the same `intent_id` and blocked.
5. Injected provider discrepancies are detected post-execution and escalated to open human review cases.
6. Pending transactions eligible for cancellation are cancelled and verified against provider state.
7. Automated test suite runs with 100% pass rate.

## Testing Checklist

### 1. Unit & State Machine Tests (`tests/unit/test_state_machine.py`)
- [x] Legal state transitions (`AUTHORIZED` -> `PROPOSED` -> `VALIDATED` -> `EXECUTING` -> `COMPLETED`)
- [x] Illegal state transitions raise `InvalidStateTransitionError`
- [x] Terminal states (`COMPLETED`, `CANCELLED`) cannot be transitioned out of

### 2. Mock Payment Service Tests (`tests/unit/test_mock_payment.py`)
- [x] Successful refund execution
- [x] Idempotent replay of identical requests
- [x] Fault: `TIMEOUT_BEFORE_EXECUTION` (provider has 0 records)
- [x] Fault: `TIMEOUT_AFTER_EXECUTION` (provider records completed effect, drops network response)

### 3. Gateway Validation Tests (`tests/unit/test_gateway_validation.py`)
- [x] Exceeding amount is rejected (`AMOUNT_EXCEEDS_AUTHORIZATION`)
- [x] Mutated order number is rejected (`ORDER_MISMATCH`)
- [x] Duplicate execution attempt for completed intent is suppressed (`ALREADY_COMPLETED`)

### 4. Reconciliation Engine Tests (`tests/integration/test_reconciliation.py`)
- [x] Discovering lost-response effect and resolving `UNKNOWN` to `COMPLETED`
- [x] Updating durable effects ledger

### 5. Transferability Tests (`tests/integration/test_payment_auth_transferability.py`)
- [x] Payment authorization hold creation
- [x] State-aware void/cancellation and provider state verification

### 6. Comprehensive Scenario Tests (`tests/e2e/test_scenarios_comprehensive.py`)
- [x] End-to-end execution of all primary failure modes

### 7. Full Benchmark Suite (`run_benchmark.py`)
- [x] 250 seeded synthetic scenarios evaluated across 5 baselines and 6 ablations

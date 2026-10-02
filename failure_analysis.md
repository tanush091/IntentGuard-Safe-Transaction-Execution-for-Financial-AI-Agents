# IntentGuard: Component Ablation Failure Analysis

This document details the specific failure modes exposed when individual components of the IntentGuard architecture are ablated. It lists the scenario categories where the ablated variant fails (by violating safety, causing duplicates, or leaving discrepancies) but the Full Protocol succeeds.

## 1. (-) No Active Reconciliation
**Description:** The system relies entirely on synchronous HTTP responses from the payment provider and does not poll or reconcile unknown states.
**Failing Scenarios:**
- `TIMEOUT_POST_EXECUTION`: The provider executes the transaction, but the HTTP response is lost. Without reconciliation, the agent or operator assumes failure and initiates a retry, resulting in **duplicate transactions** and monetary discrepancies.
- `DELAYED_PROVIDER_STATUS`: The provider initially returns `PENDING`. Without reconciliation polling, the system never discovers the terminal state.

## 2. (-) No Duplicate Protection
**Description:** The system does not check historical completed effects before executing a proposal.
**Failing Scenarios:**
- `AGENT_RESTART`: An agent crashes after execution and restarts, generating a new `request_id` for the same intent. Without duplicate protection, the system executes it again, causing **duplicates**.
- `CONCURRENT_AGENTS`: Multiple agents or retry loops dispatch identical proposals simultaneously.

## 3. (-) No Intent Binding
**Description:** The gateway accepts proposals based solely on agent authentication, without a prior durable authorization record to match against.
**Failing Scenarios:**
- `WRONG_AMOUNT`: Agent hallucinates a larger refund amount. Executes successfully, causing massive **discrepancies**.
- `WRONG_ORDER`: Agent transposes an order ID. Refunds the wrong customer.
- `WRONG_CUSTOMER`: Agent targets the wrong customer profile.

## 4. (-) No Durable Effects Ledger
**Description:** The system does not record verified provider effects durably in the local database.
**Failing Scenarios:**
- `AGENT_RESTART` and `CONCURRENT_AGENTS`: Even if intent binding is active, without a durable ledger of past executions for an intent, the gateway believes the intent is still `PROPOSED` and allows multiple executions.

## 5. (-) No State-Aware Recovery
**Description:** The system blindly cancels or retries without verifying provider state.
**Failing Scenarios:**
- `PROVIDER_DISCREPANCY`: Provider executes a corrupted amount. Without state-aware handling, the system assumes the returned `COMPLETED` status is fully valid, or blindly attempts to cancel it. The protocol fails to escalate the discrepancy to human review.

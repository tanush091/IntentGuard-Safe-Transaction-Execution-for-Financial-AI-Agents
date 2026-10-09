> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 07. API Documentation

## IntentGuard Gateway & Mock Payment Service Endpoints

---

## 1. IntentGuard Safety Gateway API (Port 8000)

### 1.1 Authorization & Intents
- `POST /api/intents`: Register a new durable authorization record.
  - **Request Body**:
    ```json
    {
      "intent_id": "INT-001",
      "operator_id": "OP-10",
      "customer_id": "C-17",
      "order_id": "ORD-204",
      "operation_type": "REFUND",
      "authorized_amount": 1500.0,
      "currency": "INR"
    }
    ```
  - **Response (201 Created)**:
    ```json
    {
      "intent_id": "INT-001",
      "current_state": "AUTHORIZED",
      "approval_status": "PENDING_PROPOSAL",
      "created_at": "2026-10-03T10:00:00Z"
    }
    ```
- `GET /api/intents/{intent_id}`: Retrieve detailed intent record including attempts, effects, and audit trail.
- `GET /api/intents`: List recent intents with optional filtering by status and order ID.

### 1.2 AI Proposals & Execution
- `POST /api/proposals`: Submit a structured AI agent proposal for gateway evaluation and execution.
  - **Request Body**:
    ```json
    {
      "intent_id": "INT-001",
      "operation": "REFUND",
      "customer_id": "C-17",
      "order_id": "ORD-204",
      "amount": 1500.0,
      "currency": "INR"
    }
    ```
  - **Response (200 OK - Approved & Executed)**:
    ```json
    {
      "decision": "APPROVED",
      "current_state": "COMPLETED",
      "attempt_number": 1,
      "provider_reference": "ref_sim_98231",
      "reason": "Proposal perfectly matched durable authorization bounds."
    }
    ```
  - **Response (403 Forbidden - Blocked)**:
    ```json
    {
      "decision": "BLOCKED",
      "current_state": "BLOCKED",
      "reason": "Amount mismatch: proposed 15000.00 exceeds authorized 1500.00."
    }
    ```

### 1.3 Human Review & Escalation Cases
- `GET /api/reviews`: List open review cases.
- `POST /api/reviews/{case_id}/resolve`: Resolve an escalated review case with human operator notes.

---

## 2. Mock Payment Service API (Port 8001)

### 2.1 Refund Operations
- `POST /refunds`: Submit a refund request.
  - **Headers**: `Idempotency-Key: <key>`
  - **Request Body**:
    ```json
    {
      "order_id": "ORD-204",
      "customer_id": "C-17",
      "amount": 1500.0,
      "currency": "INR",
      "reason": "Customer return"
    }
    ```
- `GET /refunds/{refund_id}`: Query refund status by provider reference.
- `GET /refunds?order_id=ORD-204`: Query all refunds associated with an order ID.
- `POST /refunds/{refund_id}/cancel`: Cancel an existing refund (if supported).

### 2.2 Payment Authorizations (Secondary Workflow)
- `POST /authorizations`: Hold or authorize a payment amount.
- `GET /authorizations/{auth_id}`: Inspect authorization status.
- `POST /authorizations/{auth_id}/void`: Void/cancel an existing active authorization.

### 2.3 Fault Injection & Simulation Control
- `POST /faults/configure`: Configure deterministic network faults, delays, or crash modes.
  - Supported faults: `TIMEOUT_BEFORE_EXECUTION`, `LOST_RESPONSE_AFTER_EXECUTION`, `DELAYED_VISIBILITY`, `OUTAGE_503`, `CORRUPT_AMOUNT`.
- `POST /faults/reset`: Reset all active faults to standard healthy operation.

> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 05 — API Design

## Safety Gateway

### Create Authorization
`POST /authorizations`

### Submit Agent Proposal
`POST /proposals`

### Inspect Intent
`GET /intents/{intent_id}`

### Inspect Transaction History
`GET /intents/{intent_id}/history`

### Reconcile Unknown Attempt
`POST /attempts/{attempt_id}/reconcile`

### Review Case
`GET /review-cases`

## Mock Payment Service

### Refund
`POST /refunds`

Example:
```json
{
  "customer_id": "C-17",
  "order_id": "ORD-204",
  "amount": 1500,
  "currency": "INR"
}
```

### Refund Status
`GET /refunds/{refund_id}`

### Discover Refunds
`GET /refunds?order_id=ORD-204`

### Cancel Refund
`POST /refunds/{refund_id}/cancel`

## Gateway Response Example

```json
{
  "intent_id": "INT-1001",
  "decision": "BLOCK",
  "reason": "AMOUNT_EXCEEDS_AUTHORIZATION"
}
```

## Important API Rule
The agent should never receive credentials or a direct route to the payment service.

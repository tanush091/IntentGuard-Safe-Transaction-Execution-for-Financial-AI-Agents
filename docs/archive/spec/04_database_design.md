> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 04 — Database Design

## authorizations
- intent_id
- operator_id
- customer_id
- order_id
- operation_type
- authorized_amount
- currency
- approval_status
- created_at

## agent_proposals
- proposal_id
- intent_id
- request_id
- operation
- customer_id
- order_id
- amount
- currency
- created_at

## gateway_decisions
- decision_id
- proposal_id
- decision
- reason
- created_at

## transaction_attempts
- attempt_id
- intent_id
- provider_request_id
- status
- started_at
- completed_at

## effects
- effect_id
- intent_id
- attempt_id
- provider_transaction_id
- customer_id
- order_id
- amount
- currency
- status
- observed_at

## review_cases
- case_id
- intent_id
- reason
- discrepancy_amount
- status
- created_at
- resolved_at

## Database Principle
Never silently overwrite the transaction history. Preserve previous decisions and observed effects for auditability.

> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 11. Fault Injection

## Simulating Real-World Payment Network Failures

To evaluate the resilience of the IntentGuard protocol under adverse operating conditions, the standalone `mock-payment-service` includes a configurable, deterministic fault injection engine.

---

## 1. Supported Failure Modes

| Fault Mode | Description | Real-World Analog |
| :--- | :--- | :--- |
| `TIMEOUT_BEFORE_EXECUTION` | Network drops before the provider receives or processes the request. | Client-side connection reset, cellular drop, upstream firewall blockage. |
| `LOST_RESPONSE_AFTER_EXECUTION` | Provider successfully executes the refund and settles the balance, but connection drops before the 200 OK reaches the client. | Downstream reverse-proxy timeout, client disconnect right as server finishes. |
| `DELAYED_VISIBILITY` | Provider executes the transaction, but status queries (`GET /refunds`) return `PENDING` or `404` for N seconds. | Eventual consistency in distributed databases, replica lag. |
| `OUTAGE_503` | Provider returns HTTP 503 Service Unavailable for all endpoints. | Maintenance window, upstream payment processor crash. |
| `CORRUPT_AMOUNT` | Provider simulates bit-flip or corrupted settlement with an incorrect amount. | Buggy upstream provider settlement engine. |
| `CANCELLATION_REFUSED` | Provider rejects void or cancellation requests with HTTP 409 Conflict. | Provider policy window expired, settled batch cannot be reversed. |

---

## 2. Configuration API

Faults can be configured dynamically via HTTP API:
```bash
# Configure lost response scenario for order ORD-204
curl -X POST http://127.0.0.1:8001/faults/configure \
  -H "Content-Type: application/json" \
  -d '{
    "fault_type": "LOST_RESPONSE_AFTER_EXECUTION",
    "target_order_id": "ORD-204",
    "duration_seconds": 10
  }'

# Reset all simulated faults
curl -X POST http://127.0.0.1:8001/faults/reset
```

---

## 3. Determinism & Random Seeds
All stochastic faults (e.g., probabilistic drops in large benchmark sweeps) are derived from pseudo-random number generators seeded explicitly (`--seed 42`). This ensures that benchmarks are 100% reproducible across machines and peer evaluations.

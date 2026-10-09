# ADR-001: Keep intent, proposal, attempt and effect separate

**Status:** Accepted

## Context
Simple agent integrations treat "the request" as one thing: the agent's call is the authorization,
the attempt and the outcome. That makes a wrong proposal indistinguishable from an approved one, a
timeout indistinguishable from a failure, and a restarted agent's request indistinguishable from
a new payment.

## Decision
Model four identities with separate records: the operator's **intent** (`intents`), the agent's
**proposal** (`proposals`, every one recorded with its decision), the gateway's **attempt** (one
provider call, `attempts`) and the **effect** observed at the provider (`effects`). Intent state
is never asserted by a caller; it is derived from attempts and effects (`engine._derive`) and
checked against `TRANSITIONS` (`domain.py`).

## Consequences
- A proposal can be rejected before any money moves; a new agent request can never create a new authorization.
- `COMPLETED` means an effect matching the intent was observed, not that an API call returned 200.
- More tables and more state to reason about; mitigated by the explicit transition table and property test P5.

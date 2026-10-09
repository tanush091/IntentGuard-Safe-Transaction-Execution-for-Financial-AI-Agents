# ADR-011: Ablations are configuration switches on the real engine

**Status:** Accepted

## Context
An ablation that re-implements the protocol without a component measures the re-implementation,
not the component.

## Decision
Each safeguard is a boolean or parameter in `ProtocolConfig` (`intent_binding`, `effect_dedup`,
`reconciliation`, `absence_window_s`, `stable_idempotency_key`, `state_aware_recovery`,
`serialize_intent`, plus `readback_verification`, which is not ablated). Ablation arms run the
same engine with one switch, or two overlapping switches, turned off.
`backend/tests/test_ablations.py` shows each switch changes behaviour in the scenario it exists for.

## Consequences
- Overlapping safeguards show up as "no change alone, regression together", reported as defence in depth.
- The engine carries ablation-only code paths (blind cancel, permissive transitions), marked as such in the code.

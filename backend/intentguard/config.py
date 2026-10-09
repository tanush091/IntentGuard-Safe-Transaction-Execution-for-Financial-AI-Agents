"""Protocol configuration. Each boolean switch corresponds to one ablation in the benchmark."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ProtocolConfig:
    # Components (turn one off to ablate it)
    intent_binding: bool = True  # proposal must match the durable authorization
    effect_dedup: bool = True  # gate on intent state + effects ledger
    reconciliation: bool = True  # unknown outcomes are reconciled, not assumed failed
    stable_idempotency_key: bool = True  # one provider key per intent, not per attempt
    state_aware_recovery: bool = True  # cancel only when allowed, verify, else escalate
    serialize_intent: bool = True  # decide + reserve atomically under a lock
    readback_verification: bool = True  # re-read the provider after a successful response

    # Parameters
    absence_window_s: float = 30.0  # "not found" is evidence of no effect only after this long
    max_attempts: int = 3
    auto_retry: bool = True  # gateway retries itself once absence is confirmed
    submit_lease_s: float = 15.0  # a SUBMITTING attempt older than this is presumed orphaned
    unknown_review_after_s: float = 300.0  # unresolved unknown outcomes escalate after this
    poll_interval_s: float = 5.0
    max_poll_interval_s: float = 60.0
    max_cancel_tries: int = 3

    def without(self, **flags: bool) -> "ProtocolConfig":
        return replace(self, **flags)

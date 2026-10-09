"""
The deterministic policy gate. Given the recommended action and the facts computed by code
(never by the LLM), decide whether the action is permitted in the intent's current state.
Confidence scores are not an input (ADR-013).
"""

from __future__ import annotations

from dataclasses import dataclass

from intentguard.domain import IntentState
from investigator.evidence import Facts

_TERMINAL = (IntentState.CANCELLED, IntentState.CLOSED)


@dataclass(frozen=True)
class Verdict:
    permitted: bool
    rule: str


def gate(action: str, f: Facts) -> Verdict:
    if f.state in _TERMINAL:
        return Verdict(False, "intent_is_terminal")

    if action == "MARK_COMPLETED":
        if f.open_review:
            return Verdict(False, "requires_review_resolution")
        if not f.provider_reachable:
            return Verdict(False, "provider_unreachable")
        if f.unintended_live_refs:
            return Verdict(False, "unintended_effect_live")
        if not f.matching_live_refs:
            return Verdict(False, "no_matching_effect_at_provider")
        return Verdict(True, "effect_matches_authorization")

    if action == "WAIT_AND_RECHECK":
        if f.state in (IntentState.UNKNOWN, IntentState.DISCREPANCY, IntentState.CANCEL_REQUESTED):
            return Verdict(True, "outcome_still_pending")
        return Verdict(False, "nothing_pending")

    if action == "CONTROLLED_RETRY":
        if f.state == IntentState.UNKNOWN:
            return Verdict(False, "absence_not_verified")
        if f.attempt_budget_remaining <= 0:
            return Verdict(False, "attempt_budget_exhausted")
        if not f.retry_allowed:
            return Verdict(False, "retry_not_supported_by_evidence")
        return Verdict(True, "absence_verified_and_budget_remaining")

    if action == "CANCEL_PENDING":
        if f.state not in (IntentState.DISCREPANCY, IntentState.CANCEL_REQUESTED):
            return Verdict(False, "no_discrepancy_or_cancel_request")
        if not f.cancellable_unintended:
            return Verdict(False, "effect_not_cancellable")
        return Verdict(True, "cancellable_unintended_effect")

    if action == "ESCALATE":
        if f.state == IntentState.ESCALATED:
            return Verdict(False, "already_escalated")
        return Verdict(True, "escalation_always_permitted")

    return Verdict(False, "unknown_action")

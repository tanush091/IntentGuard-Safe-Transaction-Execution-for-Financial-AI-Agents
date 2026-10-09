"""
Evidence bundle for one intent: what the ledger recorded, plus a fresh read-only lookup at the
provider. Every item has a reference (ATT-001, EFF-1, WH-3, RC-2, PROVIDER:rf_...) that the
classifier must cite. Facts used by the policy gate are computed here by code, never by the LLM.

Redaction: provider idempotency keys, secrets and internal hashes are never included; the ticket
is truncated and marked as untrusted data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from intentguard.domain import (
    LIVE_PROVIDER_STATUSES,
    IntentState,
    Operation,
    ProviderStatus,
    cancellation_policy,
)
from intentguard.engine import IntentGuard, NotFound
from intentguard.models import Attempt, Effect, Intent, ReviewCase, WebhookEvent
from intentguard.money import to_major
from intentguard.providers.base import ProviderError, ProviderRecord

# Intents an investigation may be opened for (exception-only LLM use, ADR-014).
EXCEPTION_STATES = frozenset({
    IntentState.UNKNOWN,
    IntentState.RECONCILING,
    IntentState.DISCREPANCY,
    IntentState.CANCEL_REQUESTED,
    IntentState.ESCALATED,
})

TICKET_LIMIT = 500


@dataclass
class Facts:
    """Deterministic facts the policy gate relies on."""

    state: IntentState
    provider_reachable: bool
    matching_live_refs: list[str] = field(default_factory=list)  # live, attributed, exactly as authorized
    unintended_live_refs: list[str] = field(default_factory=list)  # live, attributed, not as authorized (or extra)
    cancellable_unintended: bool = False
    retry_allowed: bool = False
    open_review: bool = False
    attempt_budget_remaining: int = 0


@dataclass
class Bundle:
    intent_id: str
    data: dict[str, Any]
    refs: set[str]
    facts: Facts


def _amount(minor: int, currency: str) -> str:
    return str(to_major(minor, currency))


def _matches(intent: Intent, rec: ProviderRecord) -> bool:
    return (rec.operation.value == intent.operation and rec.order_id == intent.order_id
            and rec.customer_id == intent.customer_id and rec.amount_minor == intent.amount_minor
            and rec.currency == intent.currency)


def build_bundle(guard: IntentGuard, intent_id: str) -> Bundle:
    with guard.session() as s:
        intent = s.get(Intent, intent_id)
        if intent is None:
            raise NotFound(f"intent {intent_id} not found")
        attempts = list(s.scalars(select(Attempt).where(Attempt.intent_id == intent_id).order_by(Attempt.attempt_no)))
        effects = list(s.scalars(select(Effect).where(Effect.intent_id == intent_id).order_by(Effect.id)))
        reviews = list(s.scalars(select(ReviewCase).where(ReviewCase.intent_id == intent_id).order_by(ReviewCase.id)))
        events = list(s.scalars(select(WebhookEvent).where(WebhookEvent.intent_id == intent_id)
                                .order_by(WebhookEvent.id)))
        s.expunge_all()
    op = Operation(intent.operation)
    state = IntentState(intent.state)

    # Fresh, read-only provider lookups: every known reference, then the order's transactions that
    # carry this intent's id or one of its attempt ids.
    lookups: dict[str, ProviderRecord] = {}
    reachable = True
    known = sorted({a.provider_ref for a in attempts if a.provider_ref} | {e.provider_ref for e in effects})
    attempt_ids = {a.id for a in attempts}
    try:
        for ref in known:
            lookups[ref] = guard.provider.get(op, ref)
        for rec in guard.provider.list_by_order(op, intent.order_id):
            if rec.metadata.get("intent_id") == intent_id or rec.metadata.get("attempt_id") in attempt_ids:
                lookups[rec.provider_ref] = rec
    except ProviderError:
        reachable = False

    live = {ref: rec for ref, rec in lookups.items() if rec.status in LIVE_PROVIDER_STATUSES}
    remediated = {e.provider_ref for e in effects if e.remediated}
    cancelling = intent.cancel_requested_at is not None
    matching = [ref for ref, rec in live.items() if _matches(intent, rec) and ref not in remediated]
    # A second exactly-matching live transaction is a duplicate, not an intended effect.
    intended_extra = matching[1:]
    matching = matching[:1]
    unintended = [ref for ref, rec in live.items()
                  if ref not in remediated and (not _matches(intent, rec) or ref in intended_extra)]
    if cancelling:
        unintended = sorted(set(unintended) | set(matching))
        matching = []
    cancellable = any(cancellation_policy(op, ProviderStatus(live[ref].status.value)) for ref in unintended)

    facts = Facts(
        state=state,
        provider_reachable=reachable,
        matching_live_refs=[f"PROVIDER:{r}" for r in matching],
        unintended_live_refs=[f"PROVIDER:{r}" for r in unintended],
        cancellable_unintended=cancellable,
        retry_allowed=guard.controlled_retry_allowed(intent_id),
        open_review=any(r.status == "OPEN" for r in reviews),
        attempt_budget_remaining=max(0, guard.cfg.max_attempts - intent.attempt_count),
    )

    data: dict[str, Any] = {
        "intent": {
            "ref": intent.id, "state": state.value, "operation": intent.operation,
            "customer_id": intent.customer_id, "order_id": intent.order_id,
            "authorized_amount": _amount(intent.amount_minor, intent.currency), "currency": intent.currency,
            "attempt_count": intent.attempt_count, "generation": intent.key_generation,
            "cancel_requested": cancelling,
        },
        "attempts": [
            {"ref": a.id, "status": a.status, "error": (a.error or "")[:200], "order_id": a.order_id,
             "amount": _amount(a.amount_minor, a.currency), "provider_ref": a.provider_ref}
            for a in attempts
        ],
        "effects": [
            {"ref": f"EFF-{e.id}", "provider_ref": e.provider_ref, "status": e.provider_status,
             "classification": e.classification, "order_id": e.order_id, "customer_id": e.customer_id,
             "amount": _amount(e.amount_minor, e.currency), "currency": e.currency, "remediated": e.remediated}
            for e in effects
        ],
        "provider_lookups": [
            {"ref": f"PROVIDER:{ref}", "status": rec.status.value, "order_id": rec.order_id,
             "customer_id": rec.customer_id, "amount": _amount(rec.amount_minor, rec.currency),
             "currency": rec.currency, "matches_authorization": _matches(intent, rec)}
            for ref, rec in sorted(lookups.items())
        ],
        "provider_reachable": reachable,
        "webhook_events": [
            {"ref": f"WH-{ev.id}", "type": ev.type, "object_id": ev.object_id, "deliveries": ev.deliveries}
            for ev in events
        ],
        "review_cases": [
            {"ref": f"RC-{r.id}", "reason": r.reason, "status": r.status,
             "discrepancy": _amount(r.discrepancy_minor, intent.currency)}
            for r in reviews
        ],
        "absence_window_s": guard.cfg.absence_window_s,
        "attempt_budget_remaining": facts.attempt_budget_remaining,
        "ticket_untrusted": (intent.ticket or "")[:TICKET_LIMIT],
    }
    refs = ({intent.id} | {a["ref"] for a in data["attempts"]} | {e["ref"] for e in data["effects"]}
            | {lk["ref"] for lk in data["provider_lookups"]} | {w["ref"] for w in data["webhook_events"]}
            | {r["ref"] for r in data["review_cases"]})
    return Bundle(intent_id=intent_id, data=data, refs=refs, facts=facts)


def unintended_kind(bundle: Bundle) -> str:
    """AMOUNT_MISMATCH when a live unintended effect is on the authorized order, else WRONG_ORDER."""
    order = bundle.data["intent"]["order_id"]
    for lk in bundle.data["provider_lookups"]:
        if lk["ref"] in bundle.facts.unintended_live_refs and lk["order_id"] != order:
            return "WRONG_ORDER"
    return "AMOUNT_MISMATCH"


__all__ = ["EXCEPTION_STATES", "Bundle", "Facts", "build_bundle", "unintended_kind"]

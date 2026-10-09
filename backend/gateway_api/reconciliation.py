"""
Reconciliation runs (docs/API.md section 5).

WORKER runs record what each background-worker pass did (examined, resolved, escalated).
MATCHING runs compare the gateway ledger with the provider, order by order, and record mismatches:

  MISSING    a live provider transaction for our orders that no intent accounts for, or a ledger
             effect that the provider does not know (lookup by id is strongly consistent)
  DUPLICATE  more than one live transaction exactly matching one intent
  AMOUNT / ORDER / CUSTOMER
             a live effect attributed to an intent that differs from it in that field

A matching run never changes money or intent state and never resolves a mismatch: a reviewer does
(zero automatic resolutions). To avoid false alarms from eventual consistency it skips intents whose
outcome is still being determined (IN_FLIGHT, UNKNOWN).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from gateway_api.security import now
from intentguard.domain import LIVE_PROVIDER_STATUSES, IntentState, Operation
from intentguard.engine import IntentGuard
from intentguard.models import Effect, Intent, Mismatch, Order, ReconciliationRun
from intentguard.providers.base import ProviderError, ProviderNotFound, ProviderRecord

_LIVE = {s.value for s in LIVE_PROVIDER_STATUSES}
_SETTLING = {IntentState.IN_FLIGHT.value, IntentState.UNKNOWN.value}


def record_worker_run(guard: IntentGuard, started: float,
                      results: list[tuple[str, IntentState, IntentState]]) -> None:
    done = (IntentState.COMPLETED, IntentState.CANCELLED)
    resolved = sum(1 for _, b, a in results if a in done and b not in done)
    escalated = sum(1 for _, b, a in results if a == IntentState.ESCALATED and b != IntentState.ESCALATED)
    with guard.session() as s, s.begin():
        s.add(ReconciliationRun(kind="WORKER", triggered_by="worker", started_at=started, finished_at=now(),
                                examined=len(results), resolved=resolved, escalated=escalated))


def _field_kinds(intent: Intent, e: Any) -> list[str]:
    kinds = []
    if e.order_id != intent.order_id:
        kinds.append("ORDER")
    if e.customer_id != intent.customer_id:
        kinds.append("CUSTOMER")
    if e.amount_minor != intent.amount_minor or e.currency != intent.currency:
        kinds.append("AMOUNT")
    return kinds


def start_matching_run(guard: IntentGuard, triggered_by: str) -> int:
    """Record a matching run as started (so callers get its id at once); matching_run() does the work."""
    with guard.session() as s, s.begin():
        run = ReconciliationRun(kind="MATCHING", triggered_by=triggered_by, started_at=now())
        s.add(run)
        s.flush()
        return run.id


def matching_run(guard: IntentGuard, triggered_by: str, run_id: int | None = None) -> dict[str, Any]:
    if run_id is None:
        run_id = start_matching_run(guard, triggered_by)
    with guard.session() as s:
        orders = [o.id for o in s.scalars(select(Order))]
        intents = {i.id: i for i in s.scalars(select(Intent))}
        effects = list(s.scalars(select(Effect)))
        s.expunge_all()
    by_ref = {e.provider_ref: e for e in effects}
    found: list[dict[str, Any]] = []
    examined = errors = 0

    # Provider -> ledger
    seen: dict[str, ProviderRecord] = {}
    for order_id in orders:
        for op in Operation:
            try:
                recs = guard.provider.list_by_order(op, order_id)
            except ProviderError:
                errors += 1
                continue
            for rec in recs:
                examined += 1
                seen[rec.provider_ref] = rec
                if rec.status.value not in _LIVE or rec.provider_ref in by_ref:
                    continue
                intent = intents.get(rec.metadata.get("intent_id", ""))
                if intent is not None and intent.state in _SETTLING:
                    continue  # the engine is still establishing this attempt's outcome
                found.append({"kind": "MISSING", "fingerprint": f"MISSING:{rec.provider_ref}",
                              "intent_id": intent.id if intent else None, "provider_ref": rec.provider_ref,
                              "order_id": rec.order_id,
                              "details": {"reason": "live provider transaction not recorded in the gateway ledger",
                                          "status": rec.status.value, "amount_minor": rec.amount_minor}})

    # Ledger -> provider, and per-intent comparisons
    matching_live: dict[str, list[str]] = {}
    for e in effects:
        examined += 1
        intent = intents.get(e.intent_id)
        if e.provider_status not in _LIVE or e.remediated or intent is None:
            continue
        if e.provider_ref not in seen:
            try:
                guard.provider.get(Operation(e.operation), e.provider_ref)
            except ProviderNotFound:
                found.append({"kind": "MISSING", "fingerprint": f"GONE:{e.provider_ref}", "intent_id": intent.id,
                              "provider_ref": e.provider_ref, "order_id": e.order_id,
                              "details": {"reason": "ledger effect is not known to the provider"}})
                continue
            except ProviderError:
                errors += 1
                continue
        kinds = _field_kinds(intent, e) if e.operation == intent.operation else ["ORDER"]
        for kind in kinds:
            found.append({"kind": kind, "fingerprint": f"{kind}:{e.provider_ref}", "intent_id": intent.id,
                          "provider_ref": e.provider_ref, "order_id": e.order_id,
                          "details": {"reason": f"live effect differs from the authorization ({kind.lower()})",
                                      "effect_amount_minor": e.amount_minor, "authorized_minor": intent.amount_minor,
                                      "effect_order": e.order_id, "authorized_order": intent.order_id,
                                      "effect_customer": e.customer_id, "authorized_customer": intent.customer_id}})
        if not kinds:
            matching_live.setdefault(intent.id, []).append(e.provider_ref)
    for iid, refs in matching_live.items():
        if len(refs) > 1:
            found.append({"kind": "DUPLICATE", "fingerprint": f"DUPLICATE:{iid}:{','.join(sorted(refs))}",
                          "intent_id": iid, "provider_ref": sorted(refs)[1], "order_id": intents[iid].order_id,
                          "details": {"reason": "more than one live transaction matches this intent",
                                      "provider_refs": sorted(refs)}})

    new = 0
    with guard.session() as s, s.begin():
        open_fps = set(s.scalars(select(Mismatch.fingerprint).where(Mismatch.status == "OPEN")))
        for m in found:
            if m["fingerprint"] in open_fps:
                continue
            open_fps.add(m["fingerprint"])
            s.add(Mismatch(run_id=run_id, status="OPEN", detected_at=now(), **m))
            new += 1
        run = s.get(ReconciliationRun, run_id)
        assert run is not None
        run.finished_at, run.examined, run.errors, run.mismatches_found = now(), examined, errors, new
    guard.record_audit("reconciliation.run", triggered_by, run_id=run_id, examined=examined, mismatches=new,
                       errors=errors)
    return {"run_id": run_id, "examined": examined, "mismatches_found": new, "errors": errors}

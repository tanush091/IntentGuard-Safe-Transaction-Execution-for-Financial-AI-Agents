"""
Reconciliation, exceptions and the AI investigator (docs/API.md sections 5 and 6).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select

from gateway_api import idempotency
from gateway_api import serializers as ser
from gateway_api.errors import ApiError
from gateway_api.pagination import paginate
from gateway_api.reconciliation import matching_run, start_matching_run
from gateway_api.routers.deps import guard_of, load_intent
from gateway_api.schemas import MismatchResolveIn
from gateway_api.security import Principal, now, require
from intentguard.agents import LLMClient, LLMSettings
from intentguard.domain import AttemptStatus, IntentState
from intentguard.models import Attempt, Effect, Intent, Investigation, Mismatch, ReconciliationRun
from investigator import EXCEPTION_STATES, LLMClassifier, OfflineClassifier
from investigator.service import InvestigatorOutputRejected, apply_investigation, investigate

router = APIRouter(tags=["recovery"])


# ---------------------------------------------------------- reconciliation


@router.post("/attempts/{attempt_id}/reconcile", summary="Force a reconciliation pass for an attempt")
def reconcile_attempt(attempt_id: str, request: Request, p: Principal = Depends(require("reconcile"))) -> dict[str, Any]:
    guard = guard_of(request)
    with guard.session() as s:
        a = s.get(Attempt, attempt_id)
        if a is None:
            raise ApiError(404, "NOT_FOUND", f"attempt {attempt_id} not found")
        intent_id = a.intent_id
    state, info = guard.reconcile_with_details(intent_id)
    with guard.session() as s:
        a = s.get(Attempt, attempt_id)
        assert a is not None
        intent = load_intent(s, intent_id)
        effects = list(s.scalars(select(Effect).where(Effect.intent_id == intent_id)))
        if not info["ran"]:
            outcome = "NOT_RECONCILABLE"
        elif not info["lookup_ok"]:
            outcome = "PROVIDER_UNREACHABLE"
        elif state == IntentState.DISCREPANCY:
            outcome = "DISCREPANCY"
        elif a.status == AttemptStatus.SUCCEEDED.value:
            outcome = "EFFECT_FOUND"
        elif a.status == AttemptStatus.RECONCILED.value:
            outcome = "ABSENT_CONFIRMED"
        elif a.status == AttemptStatus.FAILED.value:
            outcome = "REJECTED_BY_PROVIDER"
        else:
            outcome = "ABSENT_PENDING_WINDOW"
        evidence = [{"kind": "provider_lookup", "ref": e.provider_ref, "status": e.provider_status,
                     "observed_at": ser.iso(e.updated_at)} for e in effects if e.provider_ref in info["found"]]
        if info["searched"]:
            evidence.append({"kind": "provider_search", "ref": intent.order_id, "observed_at": ser.iso(now()),
                             "ok": info["lookup_ok"]})
    if state == IntentState.RECONCILING and guard.controlled_retry_allowed(intent_id):
        next_action = "CONTROLLED_RETRY"
    elif state == IntentState.ESCALATED:
        next_action = "HOLD_FOR_REVIEW"
    else:
        next_action = "NONE"
    return {"attempt_id": attempt_id, "intent_id": intent_id, "outcome": outcome, "intent_state": state.value,
            "attempt_status": a.status, "evidence": evidence, "next_action": next_action}


@router.get("/reconciliation/runs", summary="Recent reconciliation runs")
def list_runs(request: Request, p: Principal = Depends(require("reconciliation:read")),
              kind: str | None = None, limit: int | None = Query(None), cursor: str | None = None) -> dict[str, Any]:
    stmt = select(ReconciliationRun)
    if kind:
        stmt = stmt.where(ReconciliationRun.kind == kind.upper())
    with guard_of(request).session() as s:
        rows, nxt = paginate(s, stmt, ReconciliationRun.started_at, ReconciliationRun.id, limit, cursor,
                             lambda r: (r.started_at, r.id))
        return {"items": [{"run_id": ser.ref("run", r.id), "kind": r.kind, "triggered_by": r.triggered_by,
                           "started_at": ser.iso(r.started_at), "finished_at": ser.iso(r.finished_at),
                           "examined": r.examined, "resolved": r.resolved, "escalated": r.escalated,
                           "errors": r.errors, "mismatches_found": r.mismatches_found} for r in rows],
                "next_cursor": nxt}


@router.post("/reconciliation/runs", status_code=202, summary="Run a matching pass over orders and the provider")
def trigger_run(request: Request, background: BackgroundTasks,
                p: Principal = Depends(require("reconciliation:run"))) -> dict[str, Any]:
    guard = guard_of(request)
    if request.query_params.get("wait") == "true":
        result = matching_run(guard, p.sub)
        return {"run_id": ser.ref("run", result["run_id"]), "status": "finished", **{
            k: v for k, v in result.items() if k != "run_id"}}
    run_id = start_matching_run(guard, p.sub)
    background.add_task(matching_run, guard, p.sub, run_id)
    return {"run_id": ser.ref("run", run_id), "status": "started"}


@router.get("/reconciliation/mismatches", summary="Mismatches found by matching runs and webhooks")
def list_mismatches(request: Request, p: Principal = Depends(require("reconciliation:read")),
                    kind: str | None = None, status: str | None = "OPEN", limit: int | None = Query(None),
                    cursor: str | None = None) -> dict[str, Any]:
    stmt = select(Mismatch)
    if kind:
        stmt = stmt.where(Mismatch.kind == kind.upper())
    if status:
        stmt = stmt.where(Mismatch.status == status.upper())
    with guard_of(request).session() as s:
        rows, nxt = paginate(s, stmt, Mismatch.detected_at, Mismatch.id, limit, cursor,
                             lambda m: (m.detected_at, m.id))
        return {"items": [{"mismatch_id": ser.ref("mismatch", m.id), "kind": m.kind, "status": m.status,
                           "intent_id": m.intent_id, "provider_transaction_id": m.provider_ref,
                           "order_id": m.order_id, "details": m.details, "run_id": ser.ref("run", m.run_id),
                           "detected_at": ser.iso(m.detected_at), "resolved_at": ser.iso(m.resolved_at)}
                          for m in rows], "next_cursor": nxt}


@router.post("/reconciliation/mismatches/{mismatch_id}/resolve", summary="Mark a mismatch as handled")
def resolve_mismatch(mismatch_id: str, body: MismatchResolveIn, request: Request,
                     p: Principal = Depends(require("mismatches:resolve"))) -> dict[str, Any]:
    guard = guard_of(request)
    mid = ser.parse_ref("mismatch", mismatch_id)
    with guard.session() as s, s.begin():
        m = s.get(Mismatch, mid)
        if m is None:
            raise ApiError(404, "NOT_FOUND", f"mismatch {mismatch_id} not found")
        if m.status != "OPEN":
            raise ApiError(409, "ALREADY_RESOLVED", "mismatch is already resolved")
        m.status, m.resolved_at = "RESOLVED", now()
        m.details = {**m.details, "resolved_by": p.sub, "note": body.note}
        intent_id = m.intent_id
    guard.record_audit("mismatch.resolved", p.sub, intent_id, mismatch_id=mid, note=body.note)
    return {"mismatch_id": ser.ref("mismatch", mid), "status": "RESOLVED"}


# ---------------------------------------------------------------- exceptions


@router.get("/exceptions", summary="Unresolved uncertain cases (unknown, held, discrepancy, ...)")
def list_exceptions(request: Request, p: Principal = Depends(require("exceptions:read")),
                    limit: int | None = Query(None), cursor: str | None = None) -> dict[str, Any]:
    stmt = select(Intent).where(Intent.state.in_([s.value for s in EXCEPTION_STATES]))
    with guard_of(request).session() as s:
        rows, nxt = paginate(s, stmt, Intent.updated_at, Intent.id, limit, cursor, lambda i: (i.updated_at, i.id))
        items = []
        for i in rows:
            last = s.scalar(select(Investigation).where(Investigation.intent_id == i.id)
                            .order_by(Investigation.id.desc()).limit(1))
            items.append({**ser.intent_summary(i), "attempt_count": i.attempt_count,
                          "latest_investigation": ser.investigation(last) if last else None})
        return {"items": items, "next_cursor": nxt}


def _classifier(request: Request) -> Any:
    factory = getattr(request.app.state, "classifier_factory", None)
    if factory is not None:
        return factory()
    llm = LLMSettings.from_env()
    return LLMClassifier(LLMClient(llm)) if llm else OfflineClassifier()


@router.post("/exceptions/{intent_id}/investigate", summary="AI investigation (advisory; policy-gated)")
def investigate_exception(intent_id: str, request: Request,
                          p: Principal = Depends(require("exceptions:investigate"))) -> Any:
    guard = guard_of(request)

    def handler() -> dict[str, Any]:
        try:
            inv_id = investigate(guard, intent_id, p.sub, _classifier(request))
        except InvestigatorOutputRejected as exc:
            raise ApiError(422, "INVALID_INVESTIGATOR_OUTPUT", f"investigator output was rejected: {exc.reason}",
                           {"investigation_id": ser.ref("investigation", exc.investigation_id)}) from exc
        with guard.session() as s:
            return ser.investigation(s.get(Investigation, inv_id))

    return idempotency.run(request, p, {"intent_id": intent_id}, 200, handler)


@router.get("/investigations/{investigation_id}", summary="One investigation")
def get_investigation(investigation_id: str, request: Request,
                      p: Principal = Depends(require("exceptions:read"))) -> dict[str, Any]:
    with guard_of(request).session() as s:
        inv = s.get(Investigation, ser.parse_ref("investigation", investigation_id))
        if inv is None:
            raise ApiError(404, "NOT_FOUND", f"investigation {investigation_id} not found")
        out = ser.investigation(inv)
        out["prompt"], out["raw_output"] = inv.prompt, inv.raw_output
        return out


@router.post("/investigations/{investigation_id}/apply",
             summary="Apply a permitted recommendation (the policy gate is re-checked first)")
def apply(investigation_id: str, request: Request, p: Principal = Depends(require("investigations:apply"))) -> Any:
    guard = guard_of(request)
    inv_id = ser.parse_ref("investigation", investigation_id)

    def handler() -> dict[str, Any]:
        result = apply_investigation(guard, inv_id, p.sub)
        return {**result, "investigation_id": ser.ref("investigation", inv_id)}

    return idempotency.run(request, p, {"investigation_id": inv_id}, 200, handler)

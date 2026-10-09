"""Audit, metrics and experiments (docs/API.md sections 9 and 10)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from gateway_api import serializers as ser
from gateway_api.errors import ApiError
from gateway_api.pagination import paginate
from gateway_api.routers.deps import guard_of
from gateway_api.routers.intents import _ts
from gateway_api.security import Principal, now, require
from intentguard import audit
from intentguard.domain import IntentState
from intentguard.models import AuditEvent, Effect, GatewayDecision, Intent, ReviewCase

router = APIRouter(tags=["observability"])

_WINDOWS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400, "all": None}


# --------------------------------------------------------------------- audit


@router.get("/audit", summary="Audit log (newest first)")
def list_audit(request: Request, p: Principal = Depends(require("audit:read")), intent_id: str | None = None,
               actor: str | None = None, kind: str | None = None, from_: str | None = Query(None, alias="from"),
               to: str | None = None, limit: int | None = Query(None), cursor: str | None = None) -> dict[str, Any]:
    stmt = select(AuditEvent)
    if intent_id:
        stmt = stmt.where(AuditEvent.chain_id == intent_id)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    if kind:
        stmt = stmt.where(AuditEvent.kind == kind)
    if (t := _ts(from_, "from")) is not None:
        stmt = stmt.where(AuditEvent.created_at >= t)
    if (t := _ts(to, "to")) is not None:
        stmt = stmt.where(AuditEvent.created_at <= t)
    with guard_of(request).session() as s:
        rows, nxt = paginate(s, stmt, AuditEvent.seq, AuditEvent.seq, limit, cursor, lambda e: (e.seq, e.seq))
        return {"items": [ser.audit_entry(e) for e in rows], "next_cursor": nxt}


@router.get("/audit/verify", summary="Recompute every hash chain")
def verify_audit(request: Request, p: Principal = Depends(require("audit:verify"))) -> dict[str, Any]:
    with guard_of(request).session() as s:
        r = audit.verify(s)
    return {"valid": r["ok"], "entries_checked": r["checked"], "chains": r.get("chains"),
            "first_break": None if r["ok"] else {"seq": r["broken_at_seq"], "chain_id": r["chain_id"]}}


# ------------------------------------------------------------------- metrics


@router.get("/metrics/summary", summary="Operational metrics over a time window")
def metrics_summary(request: Request, p: Principal = Depends(require("metrics:read")),
                    window: str = "24h") -> dict[str, Any]:
    if window not in _WINDOWS:
        raise ApiError(422, "VALIDATION_ERROR", f"window must be one of {sorted(_WINDOWS)}")
    span = _WINDOWS[window]
    since = 0.0 if span is None else now() - span
    with guard_of(request).session() as s:
        intents = list(s.scalars(select(Intent).where(Intent.created_at >= since)))
        ids = [i.id for i in intents]
        by_state: dict[str, int] = {}
        for i in intents:
            by_state[i.state] = by_state.get(i.state, 0) + 1
        decisions = dict(s.execute(select(GatewayDecision.decision, func.count()).where(
            GatewayDecision.decided_at >= since).group_by(GatewayDecision.decision)).all())
        reviewed = set(s.scalars(select(ReviewCase.intent_id).where(ReviewCase.intent_id.in_(ids)))) if ids else set()
        refused = set(s.scalars(select(GatewayDecision.intent_id).where(
            GatewayDecision.intent_id.in_(ids), GatewayDecision.decision.in_(["REJECT", "HOLD_FOR_REVIEW"]))))             if ids else set()
        state_events = list(s.execute(select(AuditEvent.chain_id, AuditEvent.kind, AuditEvent.payload,
                                             AuditEvent.created_at).where(
            AuditEvent.chain_id.in_(ids), AuditEvent.kind.in_(["intent.state", "attempt.reserved"]))
            .order_by(AuditEvent.seq))) if ids else []
        live_bad = s.execute(select(func.count(), func.coalesce(func.sum(Effect.amount_minor), 0)).where(
            Effect.provider_status.in_(["PENDING", "COMPLETED"]), Effect.classification != "INTENDED",
            Effect.remediated.is_(False))).one()
        open_reviews = s.execute(select(func.count(), func.coalesce(func.sum(ReviewCase.discrepancy_minor), 0))
                                 .where(ReviewCase.status == "OPEN")).one()

    first_attempt: dict[str, float] = {}
    completed_at: dict[str, float] = {}
    exceptional: set[str] = set()
    for chain, kind, payload, ts in state_events:
        if kind == "attempt.reserved":
            first_attempt.setdefault(chain, ts)
        elif payload.get("to") in (IntentState.UNKNOWN.value, IntentState.DISCREPANCY.value):
            exceptional.add(chain)
        elif payload.get("to") == IntentState.COMPLETED.value:
            completed_at.setdefault(chain, ts)
    settled = {IntentState.COMPLETED.value, IntentState.CANCELLED.value}
    auto = [iid for iid in exceptional if by_state and iid not in reviewed
            and next((i.state for i in intents if i.id == iid), None) in settled]
    to_verified = [completed_at[k] - first_attempt[k] for k in completed_at if k in first_attempt]
    blocked = sum(1 for i in intents if i.state == IntentState.AUTHORIZED.value and i.attempt_count == 0
                  and i.id in refused)
    return {
        "window": window,
        "intents": {"total": len(intents), "completed": by_state.get("COMPLETED", 0),
                    "blocked": blocked, "unknown": by_state.get("UNKNOWN", 0),
                    "escalated": by_state.get("ESCALATED", 0), "by_state": by_state},
        "decisions": decisions,
        "duplicates_suppressed": decisions.get("DUPLICATE", 0),
        "auto_resolved_rate": round(len(auto) / len(exceptional), 4) if exceptional else None,
        "human_intervention_rate": round(len(reviewed) / len(intents), 4) if intents else None,
        "median_time_to_verified_s": round(statistics.median(to_verified), 3) if to_verified else None,
        "live_unintended_effects": {"count": live_bad[0], "amount_minor": int(live_bad[1])},
        "open_reviews": {"count": open_reviews[0], "discrepancy_minor": int(open_reviews[1])},
        "definitions": {
            "blocked": "authorized intents with no attempt whose proposals were rejected or held",
            "auto_resolved_rate": "intents that entered UNKNOWN or DISCREPANCY and settled with no review case",
            "human_intervention_rate": "intents with at least one review case",
            "median_time_to_verified_s": "first attempt reserved -> first COMPLETED",
        },
    }


@router.get("/experiments/latest", summary="Latest benchmark summary (summary.json)")
def latest_experiment(request: Request, p: Principal = Depends(require("metrics:read"))) -> dict[str, Any]:
    path = Path(request.app.state.settings.RESULTS_DIR) / "latest" / "summary.json"
    if not path.exists():
        raise ApiError(404, "NOT_FOUND", "no benchmark results yet; run `python -m bench run` in experiments/")
    return json.loads(path.read_text(encoding="utf-8"))

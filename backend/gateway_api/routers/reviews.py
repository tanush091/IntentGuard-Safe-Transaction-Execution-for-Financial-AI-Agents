"""Review queue (docs/API.md section 7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from gateway_api import idempotency
from gateway_api import serializers as ser
from gateway_api.errors import ApiError
from gateway_api.pagination import paginate
from gateway_api.routers.deps import guard_of
from gateway_api.schemas import ResolveIn
from gateway_api.security import Principal, require
from intentguard.models import AuditEvent, Effect, Intent, Investigation, ReviewCase

router = APIRouter(prefix="/review-cases", tags=["reviews"])


@router.get("", summary="Review cases (default: open), newest first")
def list_cases(request: Request, p: Principal = Depends(require("reviews:read")), status: str | None = "OPEN",
               limit: int | None = Query(None), cursor: str | None = None) -> dict[str, Any]:
    stmt = select(ReviewCase)
    if status:
        stmt = stmt.where(ReviewCase.status == status.upper())
    with guard_of(request).session() as s:
        rows, nxt = paginate(s, stmt, ReviewCase.created_at, ReviewCase.id, limit, cursor,
                             lambda rc: (rc.created_at, rc.id))
        currencies = dict(s.execute(select(Intent.id, Intent.currency).where(
            Intent.id.in_([rc.intent_id for rc in rows]))).all()) if rows else {}
        return {"items": [ser.review_case(rc, currencies.get(rc.intent_id, "INR")) for rc in rows],
                "next_cursor": nxt}


@router.get("/{case_id}", summary="One review case with linked effects, timeline and investigations")
def get_case(case_id: str, request: Request, p: Principal = Depends(require("reviews:read"))) -> dict[str, Any]:
    with guard_of(request).session() as s:
        rc = s.get(ReviewCase, ser.parse_ref("review", case_id))
        if rc is None:
            raise ApiError(404, "NOT_FOUND", f"review case {case_id} not found")
        intent = s.get(Intent, rc.intent_id)
        assert intent is not None
        out = ser.review_case(rc, intent.currency)
        out["intent"] = ser.intent_summary(intent)
        out["effects"] = [ser.effect(e) for e in s.scalars(select(Effect).where(Effect.intent_id == rc.intent_id)
                                                          .order_by(Effect.id))]
        out["investigations"] = [ser.investigation(inv) for inv in s.scalars(
            select(Investigation).where(Investigation.intent_id == rc.intent_id).order_by(Investigation.id))]
        out["timeline"] = [ser.audit_entry(ev) for ev in s.scalars(
            select(AuditEvent).where(AuditEvent.chain_id == rc.intent_id).order_by(AuditEvent.seq))]
        return out


@router.post("/{case_id}/resolve", summary="Resolve a review case (appended to the audit log)")
def resolve(case_id: str, body: ResolveIn, request: Request, p: Principal = Depends(require("reviews:resolve"))) -> Any:
    guard = guard_of(request)
    cid = ser.parse_ref("review", case_id)

    def handler() -> dict[str, Any]:
        state = guard.resolve_review(cid, p.sub, body.resolution, body.note)
        return {"case_id": ser.ref("review", cid), "status": "RESOLVED", "resolution": body.resolution.value,
                "intent_state": state.value}

    return idempotency.run(request, p, body, 200, handler)

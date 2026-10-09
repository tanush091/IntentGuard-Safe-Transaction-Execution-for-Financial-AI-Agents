"""
Authorizations, intents and the agent boundary (docs/API.md sections 3 and 4).

Decisions (ALLOW, REJECT, DUPLICATE, HOLD_FOR_REVIEW) are HTTP 200 payloads, not errors.
Agents may only submit proposals for, and read, the intents their token is scoped to.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from gateway_api import idempotency
from gateway_api import serializers as ser
from gateway_api.errors import ApiError
from gateway_api.pagination import paginate
from gateway_api.routers.deps import guard_of, load_intent
from gateway_api.schemas import AgentRunIn, AuthorizationIn, CancelIn, ProposalIn
from gateway_api.security import Principal, current_principal, require, require_intent_access
from intentguard.agents import ExtractionError, LLMError, LLMExtractor, LLMSettings, extract
from intentguard.checks import Proposal
from intentguard.domain import IntentState
from intentguard.engine import SubmitResult
from intentguard.models import (
    AgentProposal,
    Attempt,
    AuditEvent,
    Effect,
    GatewayDecision,
    Intent,
    Investigation,
    ReviewCase,
    WebhookEvent,
)
from intentguard.money import to_minor

router = APIRouter(tags=["intents"])

VERIFIED_STATES = {IntentState.COMPLETED.value, IntentState.EXECUTING.value, IntentState.CANCELLED.value}


def _ts(value: str | None, name: str) -> float | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", f"{name} must be an ISO-8601 timestamp") from exc


def _effect_amounts(s: Any, intent_ids: list[str]) -> dict[str, int]:
    if not intent_ids:
        return {}
    rows = s.execute(select(Effect.intent_id, func.sum(Effect.amount_minor)).where(
        Effect.intent_id.in_(intent_ids), Effect.counts_toward_intent.is_(True)).group_by(Effect.intent_id))
    return {k: int(v) for k, v in rows}


# ------------------------------------------------------------ authorizations


@router.post("/authorizations", status_code=201, summary="Operator authorization: creates the intent")
def create_authorization(body: AuthorizationIn, request: Request,
                         p: Principal = Depends(require("authorizations:create"))) -> Any:
    guard = guard_of(request)

    def handler() -> dict[str, Any]:
        iid = guard.authorize(operator_id=p.sub, customer_id=body.customer_id, order_id=body.order_id,
                              operation=body.operation, amount_minor=to_minor(body.authorized_amount, body.currency),
                              currency=body.currency, ticket=body.ticket_text, metadata=body.metadata)
        with guard.session() as s:
            i = load_intent(s, iid)
            return {"intent_id": i.id, "state": i.state, "approval_status": i.approval_status,
                    "created_at": ser.iso(i.created_at)}

    return idempotency.run(request, p, body, 201, handler)


# ------------------------------------------------------------------ intents


@router.get("/intents", summary="List intents (newest first, cursor-paginated)")
def list_intents(request: Request, p: Principal = Depends(current_principal),
                 state: str | None = None, customer_id: str | None = None, order_id: str | None = None,
                 operation: str | None = None, created_from: str | None = None, created_to: str | None = None,
                 limit: int | None = Query(None), cursor: str | None = None) -> dict[str, Any]:
    guard = guard_of(request)
    stmt = select(Intent)
    if p.role == "agent":
        ids = [sc.split(":", 2)[2] for sc in p.scopes if sc.startswith("intents:read:") and ":customer:" not in sc]
        customers = [sc.split(":", 3)[3] for sc in p.scopes if sc.startswith("intents:read:customer:")]
        stmt = stmt.where((Intent.id.in_(ids)) | (Intent.customer_id.in_(customers)))
    elif not p.can("intents:read"):
        raise ApiError(403, "FORBIDDEN", "not allowed to list intents")
    if state:
        stmt = stmt.where(Intent.state == state.upper())
    if customer_id:
        stmt = stmt.where(Intent.customer_id == customer_id)
    if order_id:
        stmt = stmt.where(Intent.order_id == order_id)
    if operation:
        stmt = stmt.where(Intent.operation == operation.upper())
    if (t := _ts(created_from, "created_from")) is not None:
        stmt = stmt.where(Intent.created_at >= t)
    if (t := _ts(created_to, "created_to")) is not None:
        stmt = stmt.where(Intent.created_at <= t)
    with guard.session() as s:
        rows, nxt = paginate(s, stmt, Intent.created_at, Intent.id, limit, cursor, lambda i: (i.created_at, i.id))
        amounts = _effect_amounts(s, [i.id for i in rows])
        return {"items": [ser.intent_summary(i, amounts.get(i.id)) for i in rows], "next_cursor": nxt}


def _readable_intent(request: Request, p: Principal, intent_id: str) -> Any:
    guard = guard_of(request)
    with guard.session() as s:
        intent = load_intent(s, intent_id)
        require_intent_access(p, intent, "intents:read", "intents:read")
        s.expunge(intent)
        return intent


@router.get("/intents/{intent_id}", summary="Intent with attempts, effects and the open review case")
def get_intent(intent_id: str, request: Request, p: Principal = Depends(current_principal)) -> dict[str, Any]:
    _readable_intent(request, p, intent_id)
    guard = guard_of(request)
    with guard.session() as s:
        i = load_intent(s, intent_id)
        attempts = list(s.scalars(select(Attempt).where(Attempt.intent_id == intent_id).order_by(Attempt.attempt_no)))
        effects = list(s.scalars(select(Effect).where(Effect.intent_id == intent_id).order_by(Effect.id)))
        open_case = s.scalar(select(ReviewCase.id).where(ReviewCase.intent_id == intent_id, ReviewCase.status == "OPEN")
                             .order_by(ReviewCase.id))
        proposals = list(s.scalars(select(AgentProposal).where(AgentProposal.intent_id == intent_id)
                                   .order_by(AgentProposal.id)))
        decisions = {d.proposal_id: d for d in s.scalars(select(GatewayDecision).where(
            GatewayDecision.intent_id == intent_id))}
        intended = sum(e.amount_minor for e in effects if e.counts_toward_intent) if effects else None
        out = ser.intent_summary(i, intended)
        out.update({
            "approval_status": i.approval_status, "generation": i.key_generation, "attempt_count": i.attempt_count,
            "ticket_text": i.ticket, "metadata": i.metadata_ or {},
            "cancel_requested": i.cancel_requested_at is not None, "verified": i.state in VERIFIED_STATES,
            "attempts": [ser.attempt(a) for a in attempts],
            "effects": [ser.effect(e) for e in effects],
            "proposals": [ser.proposal(pr, decisions.get(pr.id)) for pr in proposals],
            "open_review_case_id": ser.ref("review", open_case),
        })
        return out


_TIMELINE = {
    "intent.authorized": ("AUTHORIZED", lambda pl: f"authorized {pl.get('operation')} of "
                                                   f"{ser.amount(pl.get('amount_minor'), pl.get('currency') or 'INR')} "
                                                   f"{pl.get('currency')} on {pl.get('order_id')}"),
    "proposal.decided": ("DECISION", lambda pl: f"{pl.get('decision')}"
                         + (f" ({', '.join(f['check'] for f in pl.get('findings', []))})" if pl.get("findings") else "")),
    "attempt.reserved": ("ATTEMPT_RESERVED", lambda pl: f"attempt {pl.get('attempt_id')} reserved"),
    "attempt.result": ("ATTEMPT_RESULT", lambda pl: {"record": "provider returned a transaction",
                                                     "rejected": "provider rejected the request",
                                                     "unknown": "no usable response; outcome unknown"}
                       .get(pl.get("outcome"), str(pl.get("outcome")))),
    "effect.observed": ("PROVIDER_OBSERVATION", lambda pl: f"{pl.get('classification')} effect {pl.get('provider_ref')} "
                                                           f"is {pl.get('status')}"),
    "attempt.absence_confirmed": ("RECONCILED", lambda pl: "verified absent at the provider after the absence window"),
    "attempt.lease_expired": ("ATTEMPT_UNKNOWN", lambda pl: "submission lease expired; outcome unknown"),
    "attempt.orphaned": ("ATTEMPT_UNKNOWN", lambda pl: "gateway restarted mid-submission; outcome unknown"),
    "attempt.controlled_retry": ("CONTROLLED_RETRY", lambda pl: "controlled retry after verified absence"),
    "reconcile.lookup_failed": ("PROVIDER_UNREACHABLE", lambda pl: "provider could not be queried"),
    "effect.reversal_verified": ("REVERSAL_VERIFIED", lambda pl: f"{pl.get('provider_ref')} verified CANCELLED"),
    "effect.reversal_assumed": ("REVERSAL_ASSUMED", lambda pl: "reversal assumed without verification (ablation)"),
    "review.opened": ("ESCALATED", lambda pl: f"review case opened: {pl.get('reason')}"),
    "review.resolved": ("REVIEW_RESOLVED", lambda pl: f"review case resolved: {pl.get('resolution')}"),
    "intent.state": ("STATE", lambda pl: f"{pl.get('from')} -> {pl.get('to')}"),
    "intent.cancel_requested": ("CANCEL_REQUESTED", lambda pl: "cancellation requested"),
    "intent.cancelled": ("CANCELLED", lambda pl: "cancelled with no live effect"),
    "investigation.created": ("INVESTIGATION", lambda pl: f"investigator: {pl.get('classification')} -> "
                                                          f"{pl.get('recommended_action')} "
                                                          f"({'permitted' if pl.get('permitted') else 'not permitted'})"),
    "investigation.applied": ("INVESTIGATION_APPLIED", lambda pl: f"applied {pl.get('action')}"),
}


@router.get("/intents/{intent_id}/timeline", summary="Ordered, human-readable events")
def timeline(intent_id: str, request: Request, p: Principal = Depends(current_principal)) -> dict[str, Any]:
    _readable_intent(request, p, intent_id)
    with guard_of(request).session() as s:
        events = []
        for ev in s.scalars(select(AuditEvent).where(AuditEvent.chain_id == intent_id).order_by(AuditEvent.seq)):
            kind, summary = _TIMELINE.get(ev.kind, (ev.kind.upper().replace(".", "_"), lambda pl: ""))
            events.append({"ts": ser.iso(ev.created_at), "seq": ev.seq, "kind": kind, "actor": ev.actor,
                           "summary": summary(ev.payload), "ref": ev.payload.get("attempt_id")
                           or ev.payload.get("provider_ref") or (ser.ref("review", ev.payload.get("case_id"))
                                                                 if ev.payload.get("case_id") else None)})
        return {"intent_id": intent_id, "events": events}


@router.get("/intents/{intent_id}/history", summary="Raw rows: proposals, decisions, attempts, effects, ...")
def history(intent_id: str, request: Request, p: Principal = Depends(current_principal)) -> dict[str, Any]:
    _readable_intent(request, p, intent_id)
    with guard_of(request).session() as s:
        i = load_intent(s, intent_id)
        proposals = list(s.scalars(select(AgentProposal).where(AgentProposal.intent_id == intent_id)
                                   .order_by(AgentProposal.id)))
        decisions = {d.proposal_id: d for d in s.scalars(select(GatewayDecision).where(
            GatewayDecision.intent_id == intent_id))}
        return {
            "intent_id": intent_id,
            "proposals": [ser.proposal(pr, decisions.get(pr.id)) for pr in proposals],
            "attempts": [ser.attempt(a) for a in s.scalars(select(Attempt).where(Attempt.intent_id == intent_id)
                                                         .order_by(Attempt.attempt_no))],
            "effects": [ser.effect(e) for e in s.scalars(select(Effect).where(Effect.intent_id == intent_id)
                                                       .order_by(Effect.id))],
            "review_cases": [ser.review_case(rc, i.currency) for rc in s.scalars(
                select(ReviewCase).where(ReviewCase.intent_id == intent_id).order_by(ReviewCase.id))],
            "investigations": [ser.investigation(inv) for inv in s.scalars(
                select(Investigation).where(Investigation.intent_id == intent_id).order_by(Investigation.id))],
            "webhook_events": [ser.webhook_event(ev) for ev in s.scalars(
                select(WebhookEvent).where(WebhookEvent.intent_id == intent_id).order_by(WebhookEvent.id))],
        }


@router.post("/intents/{intent_id}/cancel", status_code=202, summary="Cancel (pending effects are verified)")
def cancel(intent_id: str, request: Request, body: CancelIn | None = None,
           p: Principal = Depends(require("cancel"))) -> Any:
    guard = guard_of(request)

    def handler() -> dict[str, Any]:
        state = guard.cancel(intent_id, p.sub)
        return {"intent_id": intent_id, "state": state.value}

    return idempotency.run(request, p, body or CancelIn(), 202, handler)


# ------------------------------------------------------------ agent boundary


def _submit_response(guard: Any, r: SubmitResult) -> dict[str, Any]:
    with guard.session() as s:
        state = s.scalar(select(Intent.state).where(Intent.id == r.intent_id))
    return {
        "intent_id": r.intent_id, "proposal_id": ser.ref("proposal", r.proposal_id), "decision": r.decision.value,
        "reason": r.findings[0]["check"] if r.findings else None,
        "reasons": [f["check"] for f in r.findings], "findings": r.findings,
        "state": state, "attempt_id": r.attempt_id, "provider_transaction_id": r.provider_ref,
        "verified": state in VERIFIED_STATES,
    }


@router.post("/intents/{intent_id}/proposals", summary="Submit a structured proposal (agent boundary)")
def submit_proposal(intent_id: str, body: ProposalIn, request: Request,
                    p: Principal = Depends(current_principal)) -> Any:
    guard = guard_of(request)
    with guard.session() as s:
        require_intent_access(p, load_intent(s, intent_id), "proposals:create", "proposals:create")

    def handler() -> dict[str, Any]:
        agent_id = p.sub if p.role == "agent" else (body.agent_id or p.sub)
        prop = Proposal(intent_id=intent_id, request_id=body.request_id or f"req_{uuid.uuid4().hex[:12]}",
                        agent_id=agent_id, operation=body.operation, customer_id=body.customer_id,
                        order_id=body.order_id, amount_minor=to_minor(body.amount, body.currency),
                        currency=body.currency.upper(), rationale=body.rationale)
        return _submit_response(guard, guard.submit(prop))

    return idempotency.run(request, p, body, 200, handler)


@router.post("/intents/{intent_id}/agent", summary="Extract a proposal from the ticket and submit it")
def run_agent(intent_id: str, request: Request, body: AgentRunIn | None = None,
              p: Principal = Depends(require("agent:run"))) -> Any:
    guard = guard_of(request)
    body = body or AgentRunIn()
    with guard.session() as s:
        ticket = body.ticket_text or load_intent(s, intent_id).ticket
    if not ticket:
        raise ApiError(422, "NO_TICKET", "no ticket text: pass ticket_text or store it on the authorization")

    def handler() -> dict[str, Any]:
        llm = LLMSettings.from_env()
        source = "llm" if llm else "rules"
        try:
            ex = LLMExtractor(llm).extract(ticket) if llm else extract(ticket)
        except LLMError as exc:
            raise ApiError(422, "INVALID_AGENT_OUTPUT", f"agent output was rejected: {exc}") from exc
        except ExtractionError as exc:
            raise ApiError(422, "EXTRACTION_FAILED", str(exc)) from exc
        prop = Proposal(intent_id=intent_id, request_id=f"req_{uuid.uuid4().hex[:12]}", agent_id="support-agent",
                        operation=ex.operation, customer_id=ex.customer_id, order_id=ex.order_id,
                        amount_minor=ex.amount_minor, currency=ex.currency, rationale=f"extracted by {source}")
        out = _submit_response(guard, guard.submit(prop))
        out["extraction"] = {"source": source, "model": f"{llm.provider}/{llm.model}" if llm else "offline-rules",
                             "proposal": {"operation": ex.operation.value, "customer_id": ex.customer_id,
                                          "order_id": ex.order_id, "amount": ser.amount(ex.amount_minor, ex.currency),
                                          "currency": ex.currency}}
        return out

    return idempotency.run(request, p, body, 200, handler)

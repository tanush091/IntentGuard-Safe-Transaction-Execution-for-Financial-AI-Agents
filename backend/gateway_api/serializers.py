"""
Database rows -> API shapes (docs/API.md). Amounts are decimal strings in major units with the
currency; timestamps are ISO-8601 UTC; identifiers carry a prefix. Provider idempotency keys are
never returned (contract rule 4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from gateway_api.errors import ApiError
from intentguard.money import fmt, to_major

PREFIX = {"proposal": "PRP", "decision": "DEC", "effect": "EFF", "review": "RC", "investigation": "INV",
          "webhook": "WH", "run": "RUN", "mismatch": "MM"}
REDACTED = "[redacted]"
_SECRET_KEYS = {"idempotency_key", "password", "password_hash", "token", "refresh_token", "webhook_secret"}


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def amount(minor: int | None, currency: str) -> str | None:
    return None if minor is None else str(to_major(minor, currency))


def ref(kind: str, n: int | None) -> str | None:
    return None if n is None else f"{PREFIX[kind]}-{n}"


def parse_ref(kind: str, value: str) -> int:
    prefix = PREFIX[kind] + "-"
    raw = value[len(prefix):] if value.upper().startswith(prefix) else value
    if not raw.isdigit():
        raise ApiError(404, "NOT_FOUND", f"{value!r} is not a valid {kind} id")
    return int(raw)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if k in _SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


# ------------------------------------------------------------------- shapes


def intent_summary(i: Any, effect_minor: int | None = None) -> dict[str, Any]:
    return {
        "intent_id": i.id, "state": i.state, "operation": i.operation, "customer_id": i.customer_id,
        "order_id": i.order_id, "authorized_amount": amount(i.amount_minor, i.currency), "currency": i.currency,
        "effect_amount": amount(effect_minor, i.currency), "operator_id": i.operator_id,
        "created_at": iso(i.created_at), "updated_at": iso(i.updated_at),
    }


def attempt(a: Any) -> dict[str, Any]:
    return {
        "attempt_id": a.id, "attempt_no": a.attempt_no, "status": a.status, "operation": a.operation,
        "order_id": a.order_id, "customer_id": a.customer_id, "amount": amount(a.amount_minor, a.currency),
        "currency": a.currency, "provider_transaction_id": a.provider_ref, "error": a.error,
        "started_at": iso(a.created_at), "completed_at": iso(a.completed_at),
    }


def effect(e: Any) -> dict[str, Any]:
    return {
        "effect_id": ref("effect", e.id), "provider_transaction_id": e.provider_ref, "attempt_id": e.attempt_id,
        "operation": e.operation, "order_id": e.order_id, "customer_id": e.customer_id,
        "amount": amount(e.amount_minor, e.currency), "currency": e.currency, "status": e.provider_status,
        "classification": e.classification, "counts_toward_intent": e.counts_toward_intent,
        "remediated": e.remediated, "note": e.note, "observed_at": iso(e.observed_at),
        "updated_at": iso(e.updated_at),
    }


def proposal(p: Any, d: Any | None) -> dict[str, Any]:
    return {
        "proposal_id": ref("proposal", p.id), "request_id": p.request_id, "agent_id": p.agent_id,
        "operation": p.operation, "customer_id": p.customer_id, "order_id": p.order_id,
        "amount": amount(p.amount_minor, p.currency), "currency": p.currency, "rationale": p.rationale,
        "status": p.status, "created_at": iso(p.created_at),
        "decision": None if d is None else {
            "decision_id": ref("decision", d.id), "decision": d.decision,
            "reasons": [f["check"] for f in d.reasons], "findings": d.reasons, "decided_at": iso(d.decided_at)},
    }


def review_case(rc: Any, currency: str) -> dict[str, Any]:
    return {
        "case_id": ref("review", rc.id), "intent_id": rc.intent_id, "reason": rc.reason,
        "discrepancy_amount": amount(rc.discrepancy_minor, currency), "currency": currency,
        "status": rc.status, "resolution": rc.resolution, "resolved_by": rc.resolved_by, "note": rc.notes,
        "details": redact(rc.details), "created_at": iso(rc.created_at), "resolved_at": iso(rc.resolved_at),
    }


def audit_entry(ev: Any) -> dict[str, Any]:
    return {
        "seq": ev.seq, "ts": iso(ev.created_at), "chain_id": ev.chain_id, "intent_id": ev.intent_id,
        "actor": ev.actor, "kind": ev.kind, "payload": redact(ev.payload), "prev_hash": ev.prev_hash,
        "hash": ev.hash,
    }


def investigation(inv: Any) -> dict[str, Any]:
    return {
        "investigation_id": ref("investigation", inv.id), "intent_id": inv.intent_id,
        "intent_state": inv.intent_state, "valid_output": inv.valid_output,
        "classification": inv.classification, "summary": inv.summary, "evidence_refs": inv.evidence_refs,
        "recommended_action": inv.recommended_action,
        "policy_verdict": {"permitted": inv.policy_permitted, "rule": inv.policy_rule},
        "model": inv.model, "tokens": {"in": inv.tokens_in, "out": inv.tokens_out},
        "created_by": inv.created_by, "created_at": iso(inv.created_at),
        "applied": None if inv.applied_at is None else {
            "at": iso(inv.applied_at), "by": inv.applied_by, "outcome": inv.apply_outcome},
    }


def webhook_event(ev: Any) -> dict[str, Any]:
    return {
        "webhook_event_id": ref("webhook", ev.id), "provider": ev.provider, "event_id": ev.event_id,
        "type": ev.type, "object_id": ev.object_id, "intent_id": ev.intent_id, "sequence": ev.sequence,
        "deliveries": ev.deliveries, "provider_created_at": iso(ev.provider_created_at),
        "received_at": iso(ev.received_at), "processed_at": iso(ev.processed_at), "outcome": ev.outcome,
    }


def user(u: Any) -> dict[str, Any]:
    return {
        "id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active,
        "permitted_operations": u.permitted_operations, "limit": amount(u.limit_minor, "INR"),
        "currency": "INR", "locked": bool(u.locked_until), "created_at": iso(u.created_at),
    }


def money_display(minor: int, currency: str) -> str:
    return fmt(minor, currency)

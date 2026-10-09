"""
Provider webhooks (docs/API.md section 8, docs/SECURITY.md section 7, ADR-021).

1. Verify the signature on the raw body (HMAC-SHA256, constant-time compare) and the timestamp
   tolerance, before parsing anything.
2. Store the event once per provider event id; a repeat delivery only increments `deliveries`.
3. Treat the event as a hint: re-fetch the transaction from the provider and let the engine absorb
   what the provider says now. Delivery order therefore does not matter.

Signature header (paysim): `Paysim-Signature: t=<unix seconds>,v1=<hex HMAC of "<t>." + body>`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gateway_api.errors import ApiError
from gateway_api.security import now
from gateway_api.settings import settings
from intentguard.domain import LIVE_PROVIDER_STATUSES, Operation, ProviderStatus
from intentguard.engine import IntentGuard
from intentguard.models import Intent, Mismatch, ProviderConfig, WebhookEvent

log = logging.getLogger("intentguard.gateway")

SIGNATURE_HEADER = "paysim-signature"
_KIND_TO_OPERATION = {"REFUND": Operation.REFUND, "AUTHORIZATION": Operation.PAYMENT_AUTHORIZATION}


def secret_for(guard: IntentGuard, provider: str) -> str:
    with guard.session() as s:
        cfg = s.get(ProviderConfig, provider)
        return (cfg.webhook_secret if cfg and cfg.webhook_secret else settings.WEBHOOK_SECRET) or ""


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify(secret: str, header: str | None, body: bytes, at: float) -> None:
    if not secret:
        raise ApiError(400, "INVALID_SIGNATURE", "webhook secret is not configured; events are rejected")
    if not header:
        raise ApiError(400, "INVALID_SIGNATURE", "missing signature header")
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        ts, given = int(parts["t"]), parts["v1"]
    except (ValueError, KeyError) as exc:
        raise ApiError(400, "INVALID_SIGNATURE", "malformed signature header") from exc
    expected = sign(secret, ts, body).split("v1=", 1)[1]
    if not hmac.compare_digest(expected, given):
        raise ApiError(400, "INVALID_SIGNATURE", "signature does not match")
    if abs(at - ts) > settings.WEBHOOK_TOLERANCE_S:
        raise ApiError(400, "STALE_EVENT", "signature timestamp is outside the tolerance window")


def receive(guard: IntentGuard, provider: str, header: str | None, body: bytes) -> tuple[dict[str, Any], int | None]:
    """Verify and store. Returns (response body, id of a new event to process, or None)."""
    verify(secret_for(guard, provider), header, body, now())
    try:
        event = json.loads(body)
        obj = event["data"]["object"]
        event_id, etype, object_id = str(event["id"]), str(event["type"]), str(obj["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiError(400, "MALFORMED_EVENT", "event body is not a valid provider event") from exc
    intent_id = (obj.get("metadata") or {}).get("intent_id")
    try:
        with guard.session() as s, s.begin():
            ev = WebhookEvent(provider=provider, event_id=event_id, type=etype, object_id=object_id,
                              provider_created_at=float(event.get("created", 0)),
                              sequence=int(event.get("sequence", 0)), payload=event, intent_id=intent_id,
                              received_at=now())
            s.add(ev)
            s.flush()
            new_id = ev.id
    except IntegrityError:
        with guard.session() as s, s.begin():
            ev = s.scalar(select(WebhookEvent).where(WebhookEvent.provider == provider,
                                                     WebhookEvent.event_id == event_id))
            if ev is not None:
                ev.deliveries += 1
        return {"status": "duplicate", "event_id": event_id}, None
    return {"status": "accepted", "event_id": event_id}, new_id


def _flag(guard: IntentGuard, kind: str, fingerprint: str, **fields: Any) -> None:
    with guard.session() as s, s.begin():
        exists = s.scalar(select(Mismatch.id).where(Mismatch.fingerprint == fingerprint, Mismatch.status == "OPEN"))
        if exists is None:
            s.add(Mismatch(run_id=None, kind=kind, status="OPEN", fingerprint=fingerprint, detected_at=now(),
                           **fields))


def process(guard: IntentGuard, event_row_id: int) -> str:
    """Re-fetch the event's transaction from the provider and absorb it. Returns the outcome."""
    with guard.session() as s:
        ev = s.get(WebhookEvent, event_row_id)
        assert ev is not None
        obj = ev.payload["data"]["object"]
        intent = s.get(Intent, ev.intent_id) if ev.intent_id else None
        intent_id = intent.id if intent else None
    op = _KIND_TO_OPERATION.get(str(obj.get("kind", "")).upper())
    live = str(obj.get("status", "")).upper() in {st.value for st in LIVE_PROVIDER_STATUSES}
    if op is None:
        outcome = "unsupported_object"
    elif intent_id is None:
        outcome = "unknown_intent"
        if live:
            _flag(guard, "MISSING", f"MISSING:{obj['id']}", provider_ref=obj["id"], order_id=obj.get("order_id"),
                  details={"source": "webhook", "reason": "live provider transaction for no known intent",
                           "event_type": ev.type})
    else:
        state, outcome = guard.observe(intent_id, op, obj["id"])
        if outcome == "terminal_intent_live_effect":
            _flag(guard, "MISSING", f"LATE:{obj['id']}", intent_id=intent_id, provider_ref=obj["id"],
                  order_id=obj.get("order_id"),
                  details={"source": "webhook", "reason": f"live provider transaction for a {state.value} intent"})
    with guard.session() as s, s.begin():
        row = s.get(WebhookEvent, event_row_id)
        assert row is not None
        row.processed_at, row.outcome = now(), outcome
    log.info("webhook %s processed: %s", event_row_id, outcome)
    return outcome


__all__ = ["SIGNATURE_HEADER", "process", "receive", "sign", "verify", "ProviderStatus"]

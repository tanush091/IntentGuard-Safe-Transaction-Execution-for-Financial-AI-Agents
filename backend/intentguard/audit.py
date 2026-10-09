"""Tamper-evident audit log: each event's hash covers its content and the previous event's hash."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from intentguard.models import AuditEvent

GENESIS = "0" * 64
SYSTEM_CHAIN = "system"


def _digest(prev_hash: str, chain_id: str, kind: str, actor: str, payload: dict[str, Any], at: float) -> str:
    body = json.dumps(
        {"chain": chain_id, "kind": kind, "actor": actor, "payload": payload, "at": repr(at)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def append(
    s: Session, *, chain_id: str, kind: str, actor: str, at: float, payload: dict[str, Any] | None = None
) -> AuditEvent:
    payload = json.loads(json.dumps(payload or {}, default=str))  # store exactly what was hashed
    prev = s.scalar(
        select(AuditEvent.hash).where(AuditEvent.chain_id == chain_id).order_by(AuditEvent.seq.desc()).limit(1)
    )
    prev = prev or GENESIS
    ev = AuditEvent(
        chain_id=chain_id,
        intent_id=None if chain_id == SYSTEM_CHAIN else chain_id,
        kind=kind,
        actor=actor,
        payload=payload,
        created_at=at,
        prev_hash=prev,
        hash=_digest(prev, chain_id, kind, actor, payload, at),
    )
    s.add(ev)
    s.flush()
    return ev


def verify(s: Session, chain_id: str | None = None) -> dict[str, Any]:
    """Recompute every chain. Returns the first broken link, if any."""
    stmt = select(AuditEvent).order_by(AuditEvent.seq)
    if chain_id:
        stmt = stmt.where(AuditEvent.chain_id == chain_id)
    last: dict[str, str] = {}
    checked = 0
    for ev in s.scalars(stmt):
        expected_prev = last.get(ev.chain_id, GENESIS)
        recomputed = _digest(ev.prev_hash, ev.chain_id, ev.kind, ev.actor, ev.payload, ev.created_at)
        if ev.prev_hash != expected_prev or recomputed != ev.hash:
            return {"ok": False, "checked": checked, "broken_at_seq": ev.seq, "chain_id": ev.chain_id}
        last[ev.chain_id] = ev.hash
        checked += 1
    return {"ok": True, "checked": checked, "chains": len(last)}

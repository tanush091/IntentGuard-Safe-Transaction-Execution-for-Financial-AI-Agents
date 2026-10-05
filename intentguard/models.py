"""
Durable records. Timestamps are float epoch seconds taken from the injected clock.

Database-level guarantees (not just application convention):
* at most one live INTENDED effect per intent (partial unique index),
* one effect row per provider transaction (unique provider_ref),
* attempt numbers are unique per intent,
* audit events are append-only (triggers reject UPDATE/DELETE) and hash-chained
  per intent; a chain cannot fork (unique chain_id + prev_hash).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DDL,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    permitted_operations: Mapped[list[Any]] = mapped_column(JSON)
    limit_minor: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[float] = mapped_column(Float)


class Order(Base):
    """The merchant's own order record (system of record for what was paid)."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[float] = mapped_column(Float)


class Intent(Base):
    __tablename__ = "intents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[str] = mapped_column(ForeignKey("operators.id"))
    customer_id: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    operation: Mapped[str] = mapped_column(String(32))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    state: Mapped[str] = mapped_column(String(32), index=True)
    ticket: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # Bumped only after an effect is verifiably reversed, so a retry gets a fresh provider key
    # instead of replaying the reversed transaction.
    key_generation: Mapped[int] = mapped_column(Integer, default=0)
    next_check_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    unknown_since: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_intents_due", "next_check_at"),)


class ProposalRecord(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id"), nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operation: Mapped[str] = mapped_column(String(32))
    order_id: Mapped[str] = mapped_column(String(64))
    customer_id: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16))
    provider_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    incarnation: Mapped[str] = mapped_column(String(64))
    lease_expires_at: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)

    __table_args__ = (UniqueConstraint("intent_id", "attempt_no", name="uq_attempt_no"),)


class Effect(Base):
    """A transaction observed at the provider and attributed to an intent."""

    __tablename__ = "effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey("attempts.id"), nullable=True)
    provider_ref: Mapped[str] = mapped_column(String(64), unique=True)
    operation: Mapped[str] = mapped_column(String(32))
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    provider_status: Mapped[str] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(String(16))
    counts_toward_intent: Mapped[bool] = mapped_column(Boolean, default=False)
    remediated: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_tries: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index(
            "uq_one_live_intended_effect",
            "intent_id",
            unique=True,
            sqlite_where=text("counts_toward_intent = 1"),
            postgresql_where=text("counts_toward_intent"),
        ),
    )


class ReviewCase(Base):
    __tablename__ = "review_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    reason: Mapped[str] = mapped_column(String(48))
    discrepancy_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    resolution: Mapped[str | None] = mapped_column(String(48), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("chain_id", "prev_hash", name="uq_audit_chain_link"),)


# Append-only enforcement at the database level.
_SQLITE_TRIGGERS = [
    "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
]
_PG_TRIGGER = [
    "CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS audit_no_modify ON audit_events",
    "CREATE TRIGGER audit_no_modify BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()",
]
for _stmt in _SQLITE_TRIGGERS:
    event.listen(AuditEvent.__table__, "after_create", DDL(_stmt).execute_if(dialect="sqlite"))
for _stmt in _PG_TRIGGER:
    event.listen(AuditEvent.__table__, "after_create", DDL(_stmt).execute_if(dialect="postgresql"))

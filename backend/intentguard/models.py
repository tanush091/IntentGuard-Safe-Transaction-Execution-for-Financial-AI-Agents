"""
Durable records. Timestamps are float epoch seconds taken from the injected clock.
Table names follow docs/ARCHITECTURE.md section 6.

Database-level guarantees (not just application convention):
* at most one live INTENDED effect per intent (partial unique index),
* one effect row per provider transaction (unique provider_ref),
* attempt numbers are unique per intent, one decision per proposal,
* webhook events are stored once per provider event id,
* audit entries are append-only (triggers reject UPDATE/DELETE) and hash-chained
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
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = "2"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


def row_dict(obj: Any) -> dict[str, Any]:
    """Column values keyed by attribute name (e.g. Intent.metadata_, AuditEvent.created_at)."""
    return {attr.key: getattr(obj, attr.key) for attr in sa_inspect(obj).mapper.column_attrs}


# ------------------------------------------------------------------ principals


class User(Base):
    """Operators, reviewers, admins and agent service principals (role column)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="operator")
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # What this user may authorize (operators, reviewers, admins).
    permitted_operations: Mapped[list[Any]] = mapped_column(JSON)
    limit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)


class RefreshToken(Base):
    """Opaque rotating refresh tokens, stored hashed. Reuse of a rotated token revokes its family."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    absolute_expires_at: Mapped[float] = mapped_column(Float)
    used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)


class ServiceToken(Base):
    """Issued agent tokens (short-lived JWTs). Kept so they can be listed and revoked by jti."""

    __tablename__ = "service_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scopes: Mapped[list[Any]] = mapped_column(JSON)
    issued_by: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)


# ---------------------------------------------------------------- merchant data


class Order(Base):
    """The merchant's own order record (system of record for what was paid)."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[float] = mapped_column(Float)


# ----------------------------------------------------------------- the protocol


class Intent(Base):
    """An operator authorization and the intent it creates (docs: authorizations / intents)."""

    __tablename__ = "intents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    customer_id: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    operation: Mapped[str] = mapped_column(String(32))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    approval_status: Mapped[str] = mapped_column(String(16), default="APPROVED")
    state: Mapped[str] = mapped_column(String(32), index=True)
    ticket: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # Bumped only after an effect is verifiably reversed, so a retry gets a fresh provider key
    # instead of replaying the reversed transaction.
    key_generation: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    cancel_requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_check_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    unknown_since: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_intents_due", "next_check_at"),)


class AgentProposal(Base):
    """Every proposal an agent (or operator) submitted, including rejected ones."""

    __tablename__ = "agent_proposals"

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
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[float] = mapped_column(Float)


class GatewayDecision(Base):
    """The gateway's decision on one proposal, with the reason codes (findings)."""

    __tablename__ = "gateway_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("agent_proposals.id"), unique=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[Any]] = mapped_column(JSON)
    decided_at: Mapped[float] = mapped_column(Float)


class Attempt(Base):
    """One provider call. Written as SUBMITTING before the call is made."""

    __tablename__ = "transaction_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("agent_proposals.id"), nullable=True)
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
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (UniqueConstraint("intent_id", "attempt_no", name="uq_attempt_no"),)


class Effect(Base):
    """A transaction observed at the provider and attributed to an intent."""

    __tablename__ = "effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_attempts.id"), nullable=True)
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


# ------------------------------------------------------------- recovery inputs


class WebhookEvent(Base):
    """A signature-verified provider event. Events are hints; state is re-fetched from the provider."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    provider_created_at: Mapped[float] = mapped_column(Float)
    sequence: Mapped[int] = mapped_column(BigInteger, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    intent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    received_at: Mapped[float] = mapped_column(Float)
    deliveries: Mapped[int] = mapped_column(Integer, default=1)
    processed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_event"),)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))  # WORKER | MATCHING
    triggered_by: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    examined: Mapped[int] = mapped_column(Integer, default=0)
    resolved: Mapped[int] = mapped_column(Integer, default=0)
    escalated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    mismatches_found: Mapped[int] = mapped_column(Integer, default=0)


class Mismatch(Base):
    """A disagreement between the gateway's ledger and the provider found by a matching run."""

    __tablename__ = "mismatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # MISSING | DUPLICATE | AMOUNT | ORDER | CUSTOMER
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    fingerprint: Mapped[str] = mapped_column(String(128))
    intent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    detected_at: Mapped[float] = mapped_column(Float)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Investigation(Base):
    """An AI investigator run: advisory classification + recommendation, and the policy gate's verdict."""

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intent_id: Mapped[str] = mapped_column(ForeignKey("intents.id"), index=True)
    intent_state: Mapped[str] = mapped_column(String(32))
    valid_output: Mapped[bool] = mapped_column(Boolean)
    classification: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSON)
    recommended_action: Mapped[str] = mapped_column(String(32))
    policy_permitted: Mapped[bool] = mapped_column(Boolean)
    policy_rule: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    raw_output: Mapped[str] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    applied_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    applied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    apply_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---------------------------------------------------------------- operations


class Policy(Base):
    """Admin-editable policy values (kill switch, limits, protocol parameters)."""

    __tablename__ = "policies"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[float] = mapped_column(Float)


class ProviderConfig(Base):
    """Provider connection settings. Secrets are write-only through the API."""

    __tablename__ = "provider_configs"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(256))
    timeout_s: Mapped[float] = mapped_column(Float)
    webhook_secret: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[float] = mapped_column(Float)


class ApiIdempotency(Base):
    """Stored responses for client Idempotency-Key replay (API calls only, not provider calls)."""

    __tablename__ = "api_idempotency"

    principal: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(256))
    body_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)


class Counter(Base):
    """Sequences for human-readable identifiers (INT-1001, ATT-001)."""

    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger)


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))


# --------------------------------------------------------------------- audit


class AuditEvent(Base):
    __tablename__ = "audit_logs"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_id: Mapped[str] = mapped_column(String(64), index=True)
    intent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column("ts", Float)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("chain_id", "prev_hash", name="uq_audit_chain_link"),)


# Append-only enforcement at the database level.
_SQLITE_TRIGGERS = [
    "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_logs "
    "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_logs "
    "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END",
]
_PG_TRIGGER = [
    "CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS audit_no_modify ON audit_logs",
    "CREATE TRIGGER audit_no_modify BEFORE UPDATE OR DELETE ON audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()",
]
for _stmt in _SQLITE_TRIGGERS:
    event.listen(AuditEvent.__table__, "after_create", DDL(_stmt).execute_if(dialect="sqlite"))
for _stmt in _PG_TRIGGER:
    event.listen(AuditEvent.__table__, "after_create", DDL(_stmt).execute_if(dialect="postgresql"))

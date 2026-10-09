"""
Gateway checks. Pure functions over a snapshot of durable state, so each check
can be unit-tested and individually ablated.

Spec mapping:
  customer/order match          -> CUSTOMER_MISMATCH, ORDER_MISMATCH
  operation type authorized     -> OPERATION_MISMATCH
  amount and currency           -> AMOUNT_MISMATCH, CURRENCY_MISMATCH, BALANCE_EXCEEDED
  operator allowed to authorize -> OPERATOR_NOT_PERMITTED, INTENT_NOT_ACTIVE
  intent already produced effect-> ALREADY_FULFILLED
  another attempt in progress   -> ATTEMPT_IN_PROGRESS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from intentguard.domain import Decision, IntentState, Operation


class Check(StrEnum):
    INTENT_NOT_ACTIVE = "INTENT_NOT_ACTIVE"
    OPERATOR_NOT_PERMITTED = "OPERATOR_NOT_PERMITTED"
    OPERATION_MISMATCH = "OPERATION_MISMATCH"
    CUSTOMER_MISMATCH = "CUSTOMER_MISMATCH"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    BALANCE_EXCEEDED = "BALANCE_EXCEEDED"
    ALREADY_FULFILLED = "ALREADY_FULFILLED"
    ATTEMPT_IN_PROGRESS = "ATTEMPT_IN_PROGRESS"
    HELD_FOR_REVIEW = "HELD_FOR_REVIEW"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class Proposal:
    """What an agent asks the gateway to do. Never trusted on its own."""

    intent_id: str
    request_id: str
    agent_id: str
    operation: Operation
    customer_id: str
    order_id: str
    amount_minor: int
    currency: str
    rationale: str = ""


@dataclass(frozen=True)
class IntentSnapshot:
    id: str
    state: IntentState
    operator_id: str
    operation: Operation
    customer_id: str
    order_id: str
    amount_minor: int
    currency: str
    attempt_count: int


@dataclass(frozen=True)
class OperatorSnapshot:
    id: str
    active: bool
    permitted_operations: frozenset[str]
    limit_minor: int


@dataclass(frozen=True)
class Context:
    intent: IntentSnapshot
    operator: OperatorSnapshot | None
    order_amount_minor: int  # merchant's record of the order value
    other_live_minor: int  # live effects of the same operation on the order, from other intents
    has_live_intended_effect: bool
    max_attempts: int


@dataclass(frozen=True)
class Finding:
    check: Check
    detail: str
    decision: Decision

    def as_dict(self) -> dict[str, str]:
        return {"check": self.check.value, "detail": self.detail, "decision": self.decision.value}


@dataclass
class Evaluation:
    decision: Decision
    findings: list[Finding] = field(default_factory=list)


_PRECEDENCE = [Decision.REJECTED, Decision.HELD, Decision.IN_PROGRESS, Decision.DUPLICATE]


def authority_findings(ctx: Context) -> list[Finding]:
    out: list[Finding] = []
    i, op = ctx.intent, ctx.operator
    if op is None or not op.active:
        out.append(Finding(Check.OPERATOR_NOT_PERMITTED, "authorizing operator is inactive or unknown", Decision.REJECTED))
    elif i.operation.value not in op.permitted_operations or i.amount_minor > op.limit_minor:
        out.append(Finding(Check.OPERATOR_NOT_PERMITTED, "operator may not authorize this operation/amount", Decision.REJECTED))
    return out


def binding_findings(ctx: Context, p: Proposal) -> list[Finding]:
    i = ctx.intent
    out: list[Finding] = []

    def mismatch(check: Check, field_name: str, want: object, got: object) -> None:
        out.append(Finding(check, f"{field_name}: authorized {want!r}, proposed {got!r}", Decision.REJECTED))

    if p.operation != i.operation:
        mismatch(Check.OPERATION_MISMATCH, "operation", i.operation.value, p.operation.value)
    if p.customer_id != i.customer_id:
        mismatch(Check.CUSTOMER_MISMATCH, "customer", i.customer_id, p.customer_id)
    if p.order_id != i.order_id:
        mismatch(Check.ORDER_MISMATCH, "order", i.order_id, p.order_id)
    if p.currency.upper() != i.currency:
        mismatch(Check.CURRENCY_MISMATCH, "currency", i.currency, p.currency)
    if p.amount_minor != i.amount_minor:
        mismatch(Check.AMOUNT_MISMATCH, "amount_minor", i.amount_minor, p.amount_minor)
    if p.amount_minor + ctx.other_live_minor > ctx.order_amount_minor:
        out.append(
            Finding(
                Check.BALANCE_EXCEEDED,
                f"order value {ctx.order_amount_minor}, already used {ctx.other_live_minor}, proposed {p.amount_minor}",
                Decision.REJECTED,
            )
        )
    return out


def state_findings(ctx: Context) -> list[Finding]:
    s = ctx.intent.state
    if s in (IntentState.REVOKED, IntentState.CLOSED):
        return [Finding(Check.INTENT_NOT_ACTIVE, f"intent is {s.value}", Decision.REJECTED)]
    if s == IntentState.NEEDS_REVIEW:
        return [Finding(Check.HELD_FOR_REVIEW, "intent is held for human review", Decision.HELD)]
    if ctx.has_live_intended_effect or s in (IntentState.COMPLETED, IntentState.PENDING_SETTLEMENT):
        return [Finding(Check.ALREADY_FULFILLED, "the authorized effect already exists", Decision.DUPLICATE)]
    if s in (IntentState.IN_FLIGHT, IntentState.OUTCOME_UNKNOWN, IntentState.DISCREPANCY):
        return [Finding(Check.ATTEMPT_IN_PROGRESS, f"intent is {s.value}; the gateway owns it", Decision.IN_PROGRESS)]
    if ctx.intent.attempt_count >= ctx.max_attempts:
        return [Finding(Check.ATTEMPT_BUDGET_EXHAUSTED, "attempt budget exhausted", Decision.HELD)]
    return []


def evaluate(ctx: Context, p: Proposal, *, intent_binding: bool = True, effect_dedup: bool = True) -> Evaluation:
    findings = authority_findings(ctx)
    if intent_binding:
        findings += binding_findings(ctx, p)
    if effect_dedup:
        findings += state_findings(ctx)
    elif ctx.intent.state in (IntentState.REVOKED, IntentState.CLOSED):
        findings += [Finding(Check.INTENT_NOT_ACTIVE, f"intent is {ctx.intent.state.value}", Decision.REJECTED)]
    for d in _PRECEDENCE:
        if any(f.decision == d for f in findings):
            return Evaluation(d, findings)
    return Evaluation(Decision.APPROVED, findings)

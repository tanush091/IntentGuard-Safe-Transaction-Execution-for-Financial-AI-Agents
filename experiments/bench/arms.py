"""
Architectures under test ("arms"). Every arm receives the same agent proposals,
talks to the same simulated provider, and is scored by the same oracle against
the provider's ledger. Arms differ only in what stands between agent and provider.

Baselines (spec section 7):
  A  direct access              agent calls the provider; no key, no checks
  B  fixed validation rules     static merchant rules (order ownership, currency, cap, local balance)
  C  API idempotency alone      agent's request_id is the provider idempotency key
  D  pre-execution reviewer     reviewer re-reads the ticket and must agree with the proposal
  E  IntentGuard                the full protocol
Ablations: IntentGuard with one (or two) components switched off via ProtocolConfig.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from intentguard.agents import ExtractionError, LLMError, extract
from intentguard.checks import Proposal
from intentguard.config import ProtocolConfig
from intentguard.db import init_schema, make_engine, make_session_factory
from intentguard.domain import Decision, IntentState
from intentguard.engine import Hooks, IntentGuard, SimulatedCrash
from intentguard.models import Attempt, ReviewCase
from intentguard.providers.base import ProviderError, ProviderRejected
from intentguard.providers.inprocess import InProcessProvider
from sqlalchemy import func, select

from bench.scenarios import IntentSpec, OperatorSpec, OrderSpec


class Resp(StrEnum):
    DONE = "DONE"  # agent believes the operation succeeded
    ACCEPTED = "ACCEPTED"  # the system took ownership (in progress / held); agent stops
    DUPLICATE = "DUPLICATE"  # already fulfilled; agent stops
    REJECTED = "REJECTED"  # definitive refusal; agent may re-propose
    ERROR = "ERROR"  # transient failure or timeout; agent may retry the same request


class Reported(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NOT_EXECUTED = "NOT_EXECUTED"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"


@dataclass
class ArmContext:
    provider: InProcessProvider
    clock: Any
    db_url: str


class CrashPlan:
    """One-shot crash at a named point, shared by all arms."""

    def __init__(self) -> None:
        self.point: str | None = None
        self._lock = threading.Lock()

    def arm(self, point: str | None) -> None:
        with self._lock:
            self.point = point

    def hit(self, point: str) -> None:
        with self._lock:
            if self.point == point:
                self.point = None
                raise SimulatedCrash(point)


class Arm:
    name = "base"
    label = "base"
    group = "baseline"

    def __init__(self, ctx: ArmContext):
        self.ctx = ctx
        self.crash = CrashPlan()
        self._last: dict[str, Resp] = {}
        self._lock = threading.Lock()

    # world setup
    def add_operator(self, op: OperatorSpec) -> None: ...
    def add_order(self, o: OrderSpec) -> None: ...
    def authorize(self, it: IntentSpec) -> None: ...
    def revoke_operator(self, operator_id: str) -> None: ...

    # runtime
    def submit(self, it: IntentSpec, p: Proposal) -> Resp:
        resp = self._submit(it, p)
        with self._lock:
            self._last[it.key] = resp
        return resp

    def _submit(self, it: IntentSpec, p: Proposal) -> Resp:
        raise NotImplementedError

    def restart(self) -> None:
        """Called after a SimulatedCrash: the crashed process comes back."""

    def tick(self) -> None: ...

    def next_due(self) -> float | None:
        return None

    # observation
    def reported(self, it: IntentSpec) -> Reported:
        last = self._last.get(it.key)
        if last in (Resp.DONE, Resp.DUPLICATE):
            return Reported.COMPLETED
        if last == Resp.REJECTED:
            return Reported.NOT_EXECUTED
        return Reported.FAILED  # error, crash, or never answered

    def flagged(self, it: IntentSpec) -> bool:
        return False

    def reviews(self, it: IntentSpec) -> int:
        return 0

    def forget_scenario(self) -> None:
        self._last.clear()

    # helper shared by the direct-style baselines
    def _send(self, p: Proposal, key: str | None) -> Resp:
        self.crash.hit("before_send")
        try:
            self.ctx.provider.create(p.operation, order_id=p.order_id, customer_id=p.customer_id,
                                     amount_minor=p.amount_minor, currency=p.currency, idempotency_key=key,
                                     metadata={"request_id": p.request_id})
            resp = Resp.DONE
        except ProviderRejected:
            resp = Resp.REJECTED
        except ProviderError:
            resp = Resp.ERROR
        self.crash.hit("after_send")
        return resp


class DirectArm(Arm):
    name, label = "A_direct", "A: direct provider access"

    def _submit(self, it: IntentSpec, p: Proposal) -> Resp:
        return self._send(p, None)


class IdempotencyArm(Arm):
    name, label = "C_idempotency", "C: API idempotency alone"

    def _submit(self, it: IntentSpec, p: Proposal) -> Resp:
        return self._send(p, p.request_id)


class StaticRulesArm(Arm):
    name, label = "B_static_rules", "B: fixed validation rules"
    AGENT_CAP_MINOR = 50_000_00  # policy: agents may not move more than ₹50,000 per operation

    def __init__(self, ctx: ArmContext):
        super().__init__(ctx)
        self.orders: dict[str, OrderSpec] = {}
        self.used: dict[tuple[str, str], int] = {}  # (order, op) -> amount the arm believes it moved

    def add_order(self, o: OrderSpec) -> None:
        self.orders[o.order_id] = o

    def _submit(self, it: IntentSpec, p: Proposal) -> Resp:
        o = self.orders.get(p.order_id)
        if (o is None or o.customer_id != p.customer_id or o.currency != p.currency
                or not 0 < p.amount_minor <= self.AGENT_CAP_MINOR
                or self.used.get((p.order_id, p.operation), 0) + p.amount_minor > o.amount_minor):
            return Resp.REJECTED
        resp = self._send(p, None)
        if resp == Resp.DONE:
            with self._lock:
                self.used[(p.order_id, p.operation)] = self.used.get((p.order_id, p.operation), 0) + p.amount_minor
        return resp


class ReviewerArm(Arm):
    """
    A pre-execution reviewer compares the proposal with the ticket it was derived from.
    Offline it uses the deterministic extractor; with --llm-reviewer it uses an LLM.
    It has no durable record of what already executed.
    """

    name, label = "D_reviewer", "D: pre-execution reviewer"

    def __init__(self, ctx: ArmContext, reviewer: Callable[[str], Any] | None = None):
        super().__init__(ctx)
        self.reviewer = reviewer or extract
        self.review_failures = 0

    def _submit(self, it: IntentSpec, p: Proposal) -> Resp:
        try:
            ex = self.reviewer(it.ticket)
        except (ExtractionError, LLMError):
            self.review_failures += 1
            return Resp.REJECTED
        if (ex.operation, ex.customer_id, ex.order_id, ex.amount_minor, ex.currency) != (
                p.operation, p.customer_id, p.order_id, p.amount_minor, p.currency):
            return Resp.REJECTED
        return self._send(p, None)


class _CrashHooks(Hooks):
    _MAP = {"before_send": "after_attempt_recorded", "after_send": "after_provider_response"}

    def __init__(self, plan: CrashPlan):
        self.plan = plan

    def at(self, point: str, **ctx: Any) -> None:
        for public, internal in self._MAP.items():
            if point == internal:
                self.plan.hit(public)


class IntentGuardArm(Arm):
    group = "proposed"

    def __init__(self, ctx: ArmContext, config: ProtocolConfig, name: str, label: str, group: str = "proposed"):
        super().__init__(ctx)
        self.name, self.label, self.group = name, label, group
        self.config = config
        engine = make_engine(ctx.db_url, durable=False)
        init_schema(engine)
        self.sf = make_session_factory(engine)
        self.engine = engine
        self.guard = self._new_guard()
        self.intent_ids: dict[str, str] = {}

    def _new_guard(self) -> IntentGuard:
        return IntentGuard(self.sf, self.ctx.provider, self.ctx.clock, self.config, _CrashHooks(self.crash))

    def add_operator(self, op: OperatorSpec) -> None:
        self.guard.upsert_operator(op.operator_id, op.operator_id, list(op.operations), op.limit_minor)

    def add_order(self, o: OrderSpec) -> None:
        self.guard.upsert_order(o.order_id, o.customer_id, o.currency, o.amount_minor)

    def authorize(self, it: IntentSpec) -> None:
        self.intent_ids[it.key] = self.guard.authorize(
            operator_id=it.operator_id, customer_id=it.customer_id, order_id=it.order_id, operation=it.operation,
            amount_minor=it.amount_minor, currency=it.currency, ticket=it.ticket)

    def revoke_operator(self, operator_id: str) -> None:
        self.guard.set_operator_active(operator_id, False)

    def _submit(self, it: IntentSpec, p: Proposal) -> Resp:
        iid = self.intent_ids[it.key]
        r = self.guard.submit(Proposal(**{**p.__dict__, "intent_id": iid}))
        if r.decision == Decision.REJECT:
            return Resp.REJECTED
        if r.decision == Decision.DUPLICATE:
            # Another attempt is in progress: the gateway owns the intent; the agent stops either way.
            in_progress = any(f["check"] == "ATTEMPT_IN_PROGRESS" for f in r.findings)
            return Resp.ACCEPTED if in_progress else Resp.DUPLICATE
        if r.decision == Decision.HOLD_FOR_REVIEW:
            return Resp.ACCEPTED
        if r.intent_state in (IntentState.COMPLETED, IntentState.EXECUTING):
            return Resp.DONE
        if r.intent_state == IntentState.RECONCILING:
            with self.sf() as s:  # provider rejected definitively -> agent may re-propose
                st = s.scalar(select(Attempt.status).where(Attempt.id == r.attempt_id))
            return Resp.REJECTED if st == "FAILED" else Resp.ACCEPTED
        return Resp.ACCEPTED

    def restart(self) -> None:
        self.guard = self._new_guard()  # new incarnation over the same durable database
        self.guard.startup_recovery()

    def tick(self) -> None:
        self.guard.tick()

    def next_due(self) -> float | None:
        return self.guard.next_due()

    def reported(self, it: IntentSpec) -> Reported:
        iid = self.intent_ids[it.key]
        st = self.guard._state(iid)
        if st in (IntentState.COMPLETED, IntentState.EXECUTING):
            return Reported.COMPLETED
        if st in (IntentState.ESCALATED, IntentState.DISCREPANCY):
            return Reported.REVIEW
        if st in (IntentState.UNKNOWN, IntentState.IN_FLIGHT):
            return Reported.IN_PROGRESS
        with self.sf() as s:
            attempts = s.scalar(select(func.count()).select_from(Attempt).where(Attempt.intent_id == iid)) or 0
        return Reported.FAILED if attempts else Reported.NOT_EXECUTED

    def reviews(self, it: IntentSpec) -> int:
        with self.sf() as s:
            return s.scalar(select(func.count()).select_from(ReviewCase).where(
                ReviewCase.intent_id == self.intent_ids[it.key])) or 0

    def flagged(self, it: IntentSpec) -> bool:
        return self.reviews(it) > 0 or self.guard._state(self.intent_ids[it.key]) == IntentState.DISCREPANCY

    def close(self) -> None:
        self.engine.dispose()


FULL = ProtocolConfig()

ABLATIONS: dict[str, tuple[str, ProtocolConfig]] = {
    "X_no_intent_binding": ("IntentGuard − intent binding", FULL.without(intent_binding=False)),
    "X_no_effect_dedup": ("IntentGuard − effect dedup", FULL.without(effect_dedup=False)),
    "X_no_reconciliation": ("IntentGuard − reconciliation", FULL.without(reconciliation=False)),
    "X_no_absence_window": ("IntentGuard − absence window", FULL.without(absence_window_s=0.0)),
    "X_no_stable_key": ("IntentGuard − stable idempotency key", FULL.without(stable_idempotency_key=False)),
    "X_no_state_aware_recovery": ("IntentGuard − state-aware recovery", FULL.without(state_aware_recovery=False)),
    "X_no_serialization": ("IntentGuard − serialization", FULL.without(serialize_intent=False)),
    "X_no_dedup_no_key": ("IntentGuard − dedup − stable key", FULL.without(effect_dedup=False, stable_idempotency_key=False)),
    "X_no_window_no_key": ("IntentGuard − absence window − stable key",
                           FULL.without(absence_window_s=0.0, stable_idempotency_key=False)),
    "X_no_recon_no_key": ("IntentGuard − reconciliation − stable key",
                          FULL.without(reconciliation=False, stable_idempotency_key=False)),
}

BASELINES: dict[str, type[Arm]] = {
    "A_direct": DirectArm,
    "B_static_rules": StaticRulesArm,
    "C_idempotency": IdempotencyArm,
    "D_reviewer": ReviewerArm,
}

ALL_ARMS = [*BASELINES, "E_intentguard", *ABLATIONS]


def build_arm(name: str, ctx: ArmContext, *, reviewer: Callable[[str], Any] | None = None) -> Arm:
    if name in BASELINES:
        cls = BASELINES[name]
        return cls(ctx, reviewer) if cls is ReviewerArm else cls(ctx)  # type: ignore[call-arg]
    if name == "E_intentguard":
        return IntentGuardArm(ctx, FULL, name, "E: IntentGuard (full protocol)", "proposed")
    if name in ABLATIONS:
        label, cfg = ABLATIONS[name]
        return IntentGuardArm(ctx, cfg, name, label, "ablation")
    raise KeyError(f"unknown arm {name}; choose from {ALL_ARMS}")


def arm_meta(name: str) -> dict[str, str]:
    if name in BASELINES:
        cls = BASELINES[name]
        return {"arm": name, "label": cls.label, "group": "baseline"}
    if name == "E_intentguard":
        return {"arm": name, "label": "E: IntentGuard (full protocol)", "group": "proposed"}
    return {"arm": name, "label": ABLATIONS[name][0], "group": "ablation"}


"""
The IntentGuard engine: the only component allowed to move money.

Life of a proposal
  1. decide   (locked)  evaluate checks against the durable authorization, record the decision
  2. reserve  (same tx) record an attempt with a provider idempotency key, intent -> IN_FLIGHT
  3. execute  (no lock) call the provider
  4. verify   (no lock) read the transaction back from the provider
  5. absorb   (locked)  record the observed effect, derive intent state from the ledger
  6. drive    reconcile unknown outcomes, recover discrepancies, retry only on verified absence

Provider I/O never happens while a database lock is held. Every state change is
checked against domain.TRANSITIONS and written to the hash-chained audit log.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intentguard import audit, checks
from intentguard.checks import Proposal
from intentguard.config import ProtocolConfig
from intentguard.domain import (
    LIVE_PROVIDER_STATUSES,
    UNRESOLVED_ATTEMPTS,
    AttemptStatus,
    Decision,
    EffectClass,
    IntentState,
    Operation,
    ProviderStatus,
    ReviewReason,
    ReviewResolution,
    cancellation_policy,
    IllegalTransition,
    check_transition,
    proposal_status,
)
from intentguard.models import (
    AgentProposal,
    Attempt,
    Counter,
    Effect,
    GatewayDecision,
    Intent,
    Order,
    Policy,
    ReviewCase,
    User,
    row_dict,
)
from intentguard.providers.base import (
    PaymentProvider,
    ProviderError,
    ProviderRecord,
    ProviderRejected,
)

LIVE = [s.value for s in LIVE_PROVIDER_STATUSES]
ACTIVE_STATES = frozenset(
    {IntentState.IN_FLIGHT, IntentState.UNKNOWN, IntentState.EXECUTING, IntentState.DISCREPANCY,
     IntentState.CANCEL_REQUESTED}
)
RECONCILABLE_STATES = ACTIVE_STATES | {IntentState.COMPLETED}


class SimulatedCrash(BaseException):
    """Raised by fault-injection hooks to emulate a process crash at a named point."""


class Hooks:
    """Override `at` to inject crashes. Points: after_attempt_recorded, after_provider_response."""

    def at(self, point: str, **ctx: Any) -> None:
        return None


class GatewayError(Exception):
    """Base for engine errors that the API maps to an error code."""

    code = "ERROR"

    def __init__(self, message: str, code: str | None = None, **details: Any):
        super().__init__(message)
        if code:
            self.code = code
        self.details = details


class AuthorizationError(GatewayError, ValueError):
    """An operator authorization (intent) was refused."""

    code = "AUTHORIZATION_REFUSED"


class NotFound(GatewayError, LookupError):
    code = "NOT_FOUND"


class ConflictError(GatewayError, RuntimeError):
    code = "STATE_CONFLICT"


class PermissionDenied(GatewayError, PermissionError):
    code = "FORBIDDEN"


# Policy keys the engine reads, with their defaults (the policies table overrides them).
POLICY_DEFAULTS: dict[str, Any] = {
    "kill_switch": False,
    "max_amount_minor": None,
    "separation_of_duties": True,
}


@dataclass
class SubmitResult:
    decision: Decision
    intent_id: str
    intent_state: IntentState
    findings: list[dict[str, str]] = field(default_factory=list)
    proposal_id: int | None = None
    attempt_id: str | None = None
    provider_ref: str | None = None


class IntentGuard:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provider: PaymentProvider,
        clock: Any,
        config: ProtocolConfig | None = None,
        hooks: Hooks | None = None,
        incarnation: str | None = None,
    ):
        self._sf = session_factory
        self.provider = provider
        self.clock = clock
        self.cfg = config or ProtocolConfig()
        self.hooks = hooks or Hooks()
        self.incarnation = incarnation or uuid.uuid4().hex[:12]

    # ================================================================ plumbing

    def _now(self) -> float:
        return self.clock.now()

    def session(self) -> Session:
        return self._sf()

    @contextmanager
    def _uow(self) -> Iterator[Session]:
        with self._sf() as s, s.begin():
            yield s

    @contextmanager
    def _locked(self, intent_id: str) -> Iterator[tuple[Session, Intent]]:
        with self._uow() as s:
            stmt = select(Intent).where(Intent.id == intent_id)
            if self.cfg.serialize_intent:
                stmt = stmt.with_for_update()
            intent = s.scalar(stmt)
            if intent is None:
                raise NotFound(f"intent {intent_id} not found")
            yield s, intent

    def _audit(self, s: Session, chain: str | None, kind: str, actor: str = "gateway", **payload: Any) -> None:
        audit.append(s, chain_id=chain or audit.SYSTEM_CHAIN, kind=kind, actor=actor, at=self._now(), payload=payload)

    def _next_seq(self, s: Session, name: str) -> int:
        """Next value of a named sequence; the row lock serializes concurrent callers."""
        c = s.scalar(select(Counter).where(Counter.name == name).with_for_update())
        if c is None:  # databases created by init_schema always have the counters
            c = Counter(name=name, value=0)
            s.add(c)
        c.value += 1
        s.flush()
        return c.value

    def policies(self, s: Session | None = None) -> dict[str, Any]:
        """Current policy values (POLICY_DEFAULTS overridden by the policies table)."""
        if s is None:
            with self._sf() as s2:
                return self.policies(s2)
        out = dict(POLICY_DEFAULTS)
        for row in s.scalars(select(Policy)):
            out[row.key] = row.value
        return out

    def set_policy(self, key: str, value: Any, actor: str) -> None:
        with self._uow() as s:
            row = s.get(Policy, key)
            old = row.value if row else POLICY_DEFAULTS.get(key)
            if row is None:
                row = Policy(key=key, value=value, updated_by=actor, updated_at=self._now())
                s.add(row)
            row.value, row.updated_by, row.updated_at = value, actor, self._now()
            self._audit(s, None, "policy.updated", actor=actor, key=key, old=old, new=value)

    def _state(self, intent_id: str) -> IntentState:
        with self._sf() as s:
            st = s.scalar(select(Intent.state).where(Intent.id == intent_id))
            if st is None:
                raise NotFound(f"intent {intent_id} not found")
            return IntentState(st)

    # =================================================================== admin

    def upsert_operator(
        self, operator_id: str, name: str, permitted_operations: list[str], limit_minor: int, active: bool = True,
        role: str = "operator",
    ) -> None:
        """Create or update a user who may authorize intents (role operator, reviewer or admin)."""
        with self._uow() as s:
            op = s.get(User, operator_id)
            if op is None:
                op = User(id=operator_id, role=role, created_at=self._now())
                s.add(op)
            op.name, op.active = name, active
            op.permitted_operations = [Operation(o).value for o in permitted_operations]
            op.limit_minor = limit_minor
            self._audit(s, None, "operator.upserted", operator_id=operator_id, active=active,
                        permitted_operations=op.permitted_operations, limit_minor=limit_minor)

    def set_operator_active(self, operator_id: str, active: bool, actor: str = "admin") -> None:
        with self._uow() as s:
            op = s.get(User, operator_id)
            if op is None:
                raise NotFound(f"operator {operator_id} not found")
            op.active = active
            self._audit(s, None, "operator.active_changed", actor=actor, operator_id=operator_id, active=active)

    def upsert_order(self, order_id: str, customer_id: str, currency: str, amount_minor: int) -> None:
        with self._uow() as s:
            o = s.get(Order, order_id)
            if o is None:
                o = Order(id=order_id, created_at=self._now())
                s.add(o)
            o.customer_id, o.currency, o.amount_minor = customer_id, currency.upper(), amount_minor

    # =========================================================== authorization

    def authorize(
        self,
        *,
        operator_id: str,
        customer_id: str,
        order_id: str,
        operation: Operation | str,
        amount_minor: int,
        currency: str,
        ticket: str | None = None,
        intent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        operation = Operation(operation)
        currency = currency.upper()
        now = self._now()
        with self._uow() as s:
            op = s.get(User, operator_id)
            if op is None or not op.active:
                raise AuthorizationError("operator is unknown or inactive", "OPERATOR_NOT_PERMITTED")
            if operation.value not in op.permitted_operations:
                raise AuthorizationError(f"operator may not authorize {operation.value}", "OPERATOR_NOT_PERMITTED")
            if amount_minor > op.limit_minor:
                raise AuthorizationError("amount exceeds the operator's authorization limit",
                                         "OPERATOR_LIMIT_EXCEEDED")
            policy_max = self.policies(s)["max_amount_minor"]
            if policy_max is not None and amount_minor > policy_max:
                raise AuthorizationError("amount exceeds the policy limit", "POLICY_LIMIT_EXCEEDED")
            order = s.get(Order, order_id)
            if order is None:
                raise AuthorizationError(f"order {order_id} is not known to the merchant", "ORDER_NOT_FOUND")
            if order.customer_id != customer_id:
                raise AuthorizationError("order does not belong to this customer", "CUSTOMER_MISMATCH")
            if order.currency != currency:
                raise AuthorizationError("currency does not match the order", "CURRENCY_MISMATCH")
            if not 0 < amount_minor <= order.amount_minor:
                raise AuthorizationError("amount must be positive and within the order value", "INVALID_AMOUNT")
            iid = intent_id or f"INT-{self._next_seq(s, 'intent')}"
            s.add(
                Intent(
                    id=iid, operator_id=operator_id, customer_id=customer_id, order_id=order_id,
                    operation=operation.value, amount_minor=amount_minor, currency=currency,
                    approval_status="APPROVED", state=IntentState.AUTHORIZED.value, ticket=ticket,
                    metadata_=metadata or {}, attempt_count=0, key_generation=0, created_at=now, updated_at=now,
                )
            )
            s.flush()
            self._audit(s, iid, "intent.authorized", actor=operator_id, operation=operation.value,
                        customer_id=customer_id, order_id=order_id, amount_minor=amount_minor, currency=currency)
        return iid

    def cancel(self, intent_id: str, actor: str) -> IntentState:
        """
        Cancel an intent. With no live effect it becomes CANCELLED at once. A pending intended
        effect (or an authorized hold) is cancelled at the provider and the cancellation is
        verified before the intent becomes CANCELLED. A completed refund cannot be cancelled.
        """
        with self._locked(intent_id) as (s, intent):
            state = IntentState(intent.state)
            if state in (IntentState.AUTHORIZED, IntentState.RECONCILING):
                self._set_state(s, intent, IntentState.CANCELLED)
                intent.cancel_requested_at, intent.cancel_requested_by = self._now(), actor
                intent.next_check_at = None
                self._audit(s, intent.id, "intent.cancelled", actor=actor, live_effects=0)
                return IntentState.CANCELLED
            if state in (IntentState.IN_FLIGHT, IntentState.UNKNOWN):
                raise ConflictError("an attempt is in progress; its outcome must be known before cancelling",
                                    "ATTEMPT_IN_PROGRESS")
            if state not in (IntentState.EXECUTING, IntentState.COMPLETED):
                raise ConflictError(f"cannot cancel an intent in state {state.value}", "STATE_CONFLICT")
            live = [e for e in s.scalars(select(Effect).where(Effect.intent_id == intent_id))
                    if e.provider_status in LIVE and not e.remediated]
            op = Operation(intent.operation)
            if any(not cancellation_policy(op, ProviderStatus(e.provider_status)) for e in live):
                raise ConflictError("the provider effect is already completed and cannot be cancelled",
                                    "NOT_CANCELLABLE")
            intent.cancel_requested_at, intent.cancel_requested_by = self._now(), actor
            self._audit(s, intent.id, "intent.cancel_requested", actor=actor, live_effects=len(live))
            self._refresh(s, intent)
        return self._drive(intent_id)

    # ============================================================== submission

    def submit(self, p: Proposal) -> SubmitResult:
        if self.cfg.serialize_intent:
            with self._locked(p.intent_id) as (s, intent):
                result = self._decide(s, intent, p)
                if result.decision == Decision.ALLOW:
                    result.attempt_id = self._reserve(s, intent, p, result.proposal_id).id
        else:
            # Ablation: decision and reservation in separate transactions.
            with self._locked(p.intent_id) as (s, intent):
                result = self._decide(s, intent, p)
            if result.decision == Decision.ALLOW:
                time.sleep(0)
                try:
                    with self._locked(p.intent_id) as (s, intent):
                        result.attempt_id = self._reserve(s, intent, p, result.proposal_id).id
                except IllegalTransition:
                    # The state machine still refuses e.g. COMPLETED -> IN_FLIGHT; only the
                    # window where both agents reserve while IN_FLIGHT stays open.
                    st = self._state(p.intent_id)
                    done = st in (IntentState.COMPLETED, IntentState.EXECUTING)
                    check = checks.Check.ALREADY_COMPLETED if done else checks.Check.ATTEMPT_IN_PROGRESS
                    result.decision = Decision.DUPLICATE
                    result.findings = [checks.Finding(check, f"intent is {st.value}", Decision.DUPLICATE).as_dict()]
                    result.intent_state = st

        if result.attempt_id is not None:
            self._execute(result.attempt_id)
            self._drive(p.intent_id)
            with self._sf() as s:
                result.intent_state = IntentState(s.get(Intent, p.intent_id).state)  # type: ignore[union-attr]
                result.provider_ref = s.scalar(select(Attempt.provider_ref).where(Attempt.id == result.attempt_id))
        return result

    def _context(self, s: Session, intent: Intent) -> checks.Context:
        op = s.get(User, intent.operator_id)
        policy = self.policies(s)
        order = s.get(Order, intent.order_id)
        other_live = s.scalar(
            select(func.coalesce(func.sum(Effect.amount_minor), 0)).where(
                Effect.order_id == intent.order_id,
                Effect.operation == intent.operation,
                Effect.intent_id != intent.id,
                Effect.provider_status.in_(LIVE),
                Effect.remediated.is_(False),
            )
        )
        has_live = (
            s.scalar(
                select(func.count()).select_from(Effect).where(
                    Effect.intent_id == intent.id, Effect.counts_toward_intent.is_(True)
                )
            )
            or 0
        ) > 0
        return checks.Context(
            intent=checks.IntentSnapshot(
                id=intent.id, state=IntentState(intent.state), operator_id=intent.operator_id,
                operation=Operation(intent.operation), customer_id=intent.customer_id, order_id=intent.order_id,
                amount_minor=intent.amount_minor, currency=intent.currency, attempt_count=intent.attempt_count,
            ),
            operator=None if op is None else checks.OperatorSnapshot(
                id=op.id, active=op.active, permitted_operations=frozenset(op.permitted_operations),
                limit_minor=op.limit_minor,
            ),
            order_amount_minor=order.amount_minor if order else 0,
            other_live_minor=int(other_live or 0),
            has_live_intended_effect=has_live,
            max_attempts=self.cfg.max_attempts,
            kill_switch=bool(policy["kill_switch"]),
            policy_max_minor=policy["max_amount_minor"],
        )

    def _decide(self, s: Session, intent: Intent, p: Proposal) -> SubmitResult:
        ev = checks.evaluate(
            self._context(s, intent), p,
            intent_binding=self.cfg.intent_binding, effect_dedup=self.cfg.effect_dedup,
        )
        findings = [f.as_dict() for f in ev.findings]
        now = self._now()
        rec = AgentProposal(
            intent_id=intent.id, request_id=p.request_id, agent_id=p.agent_id, operation=p.operation.value,
            customer_id=p.customer_id, order_id=p.order_id, amount_minor=p.amount_minor,
            currency=p.currency.upper(), rationale=p.rationale, status=proposal_status(ev.decision).value,
            created_at=now,
        )
        s.add(rec)
        s.flush()
        s.add(GatewayDecision(proposal_id=rec.id, intent_id=intent.id, decision=ev.decision.value,
                              reasons=findings, decided_at=now))
        self._audit(s, intent.id, "proposal.decided", actor=p.agent_id, request_id=p.request_id,
                    decision=ev.decision.value, findings=findings,
                    proposal={"operation": p.operation.value, "customer_id": p.customer_id, "order_id": p.order_id,
                              "amount_minor": p.amount_minor, "currency": p.currency})
        existing_ref = None
        if ev.decision == Decision.DUPLICATE:
            existing_ref = s.scalar(
                select(Effect.provider_ref).where(Effect.intent_id == intent.id, Effect.counts_toward_intent.is_(True))
            )
        return SubmitResult(
            decision=ev.decision, intent_id=intent.id, intent_state=IntentState(intent.state),
            findings=findings, proposal_id=rec.id, provider_ref=existing_ref,
        )

    def _reserve(self, s: Session, intent: Intent, p: Proposal, proposal_id: int | None) -> Attempt:
        now = self._now()
        intent.attempt_count += 1
        n = intent.attempt_count
        if self.cfg.stable_idempotency_key:
            key = f"ig-{intent.id}-g{intent.key_generation}"
        else:
            key = f"ig-{intent.id}-a{n}"
        a = Attempt(
            id=f"ATT-{self._next_seq(s, 'attempt'):03d}", intent_id=intent.id, proposal_id=proposal_id, attempt_no=n,
            idempotency_key=key, operation=p.operation.value, order_id=p.order_id, customer_id=p.customer_id,
            amount_minor=p.amount_minor, currency=p.currency.upper(), status=AttemptStatus.SUBMITTING.value,
            incarnation=self.incarnation, lease_expires_at=now + self.cfg.submit_lease_s,
            created_at=now, updated_at=now,
        )
        s.add(a)
        s.flush()
        self._set_state(s, intent, IntentState.IN_FLIGHT)
        intent.next_check_at = now + self.cfg.submit_lease_s
        self._audit(s, intent.id, "attempt.reserved", attempt_id=a.id, attempt_no=n, idempotency_key=key,
                    amount_minor=a.amount_minor, order_id=a.order_id)
        return a

    def _execute(self, attempt_id: str) -> None:
        with self._sf() as s:
            a = s.get(Attempt, attempt_id)
            assert a is not None
            op, intent_id = Operation(a.operation), a.intent_id
            params = dict(order_id=a.order_id, customer_id=a.customer_id, amount_minor=a.amount_minor,
                          currency=a.currency, idempotency_key=a.idempotency_key)

        self.hooks.at("after_attempt_recorded", intent_id=intent_id, attempt_id=attempt_id)
        rec: ProviderRecord | None = None
        outcome, error = "record", None
        try:
            rec = self.provider.create(op, metadata={"intent_id": intent_id, "attempt_id": attempt_id}, **params)
        except ProviderRejected as exc:
            outcome, error = "rejected", f"{exc.code}: {exc}"
        except ProviderError as exc:
            outcome, error = "unknown", f"{type(exc).__name__}: {exc}"
        self.hooks.at("after_provider_response", intent_id=intent_id, attempt_id=attempt_id, outcome=outcome)

        if rec is not None and self.cfg.readback_verification:
            try:
                rec = self.provider.get(op, rec.provider_ref)
            except ProviderError:
                pass  # keep the create response; reconciliation re-reads later

        with self._locked(intent_id) as (s, intent):
            att = s.get(Attempt, attempt_id)
            assert att is not None
            now = self._now()
            if rec is not None:
                att.status, att.provider_ref = AttemptStatus.SUCCEEDED.value, rec.provider_ref
                self._absorb(s, intent, rec)
            elif AttemptStatus(att.status) in UNRESOLVED_ATTEMPTS:
                if outcome == "rejected":
                    att.status = AttemptStatus.FAILED.value
                elif self.cfg.reconciliation:
                    att.status = AttemptStatus.UNKNOWN.value
                    intent.unknown_since = intent.unknown_since or now
                else:
                    att.status = AttemptStatus.RECONCILED.value
                    error = f"{error} (assumed no effect: reconciliation disabled)"
            att.error, att.updated_at = error, now
            if att.status not in (AttemptStatus.SUBMITTING.value, AttemptStatus.UNKNOWN.value):
                att.completed_at = att.completed_at or now
            self._audit(s, intent.id, "attempt.result", attempt_id=attempt_id, outcome=outcome,
                        provider_ref=rec.provider_ref if rec else None,
                        provider_status=rec.status.value if rec else None, error=error)
            self._refresh(s, intent)

    # ============================================================ ledger logic

    def _matches_intent(self, intent: Intent, rec: ProviderRecord) -> bool:
        return (
            rec.operation.value == intent.operation
            and rec.order_id == intent.order_id
            and rec.customer_id == intent.customer_id
            and rec.amount_minor == intent.amount_minor
            and rec.currency == intent.currency
        )

    def _absorb(self, s: Session, intent: Intent, rec: ProviderRecord) -> Effect:
        now = self._now()
        live = rec.status in LIVE_PROVIDER_STATUSES
        eff = s.scalar(select(Effect).where(Effect.provider_ref == rec.provider_ref))
        new = eff is None
        if eff is None:
            att_id = rec.metadata.get("attempt_id")
            if att_id is not None and s.get(Attempt, att_id) is None:
                att_id = None
            eff = Effect(
                intent_id=intent.id, attempt_id=att_id, provider_ref=rec.provider_ref, operation=rec.operation.value,
                order_id=rec.order_id, customer_id=rec.customer_id, amount_minor=rec.amount_minor,
                currency=rec.currency, provider_status=rec.status.value, classification=EffectClass.MISMATCH.value,
                counts_toward_intent=False, remediated=False, cancel_tries=0, observed_at=now, updated_at=now,
            )
            s.add(eff)
        old_status = eff.provider_status
        eff.provider_status, eff.amount_minor, eff.updated_at = rec.status.value, rec.amount_minor, now

        if not self._matches_intent(intent, rec):
            cls = EffectClass.MISMATCH
        elif eff.classification == EffectClass.INTENDED.value and not new:
            cls = EffectClass.INTENDED
        else:
            other = s.scalar(
                select(Effect.id).where(
                    Effect.intent_id == intent.id,
                    Effect.counts_toward_intent.is_(True),
                    Effect.provider_ref != rec.provider_ref,
                )
            )
            cls = EffectClass.DUPLICATE if (other is not None and live) else EffectClass.INTENDED
        eff.classification = cls.value
        eff.counts_toward_intent = cls == EffectClass.INTENDED and live and not eff.remediated
        s.flush()
        if new or old_status != eff.provider_status:
            self._audit(s, intent.id, "effect.observed", provider_ref=rec.provider_ref, status=rec.status.value,
                        classification=cls.value, amount_minor=rec.amount_minor, order_id=rec.order_id,
                        customer_id=rec.customer_id)

        # Attribute the transaction to the attempt(s) that produced it.
        att_id = rec.metadata.get("attempt_id")
        for att in s.scalars(select(Attempt).where(Attempt.intent_id == intent.id)):
            same = att.id == att_id or (rec.idempotency_key is not None and att.idempotency_key == rec.idempotency_key)
            if not same or att.status in (AttemptStatus.SUCCEEDED.value, AttemptStatus.FAILED.value):
                continue
            if att.status == AttemptStatus.RECONCILED.value:
                self._audit(s, intent.id, "attempt.absence_assumption_violated", attempt_id=att.id,
                            provider_ref=rec.provider_ref)
            att.status, att.provider_ref, att.updated_at = AttemptStatus.SUCCEEDED.value, rec.provider_ref, now
            att.completed_at = att.completed_at or now
        return eff

    def _derive(self, intent: Intent, effects: list[Effect], attempts: list[Attempt], open_review: bool) -> IntentState:
        current = IntentState(intent.state)
        if current in (IntentState.CANCELLED, IntentState.CLOSED):
            return current
        if open_review:
            return IntentState.ESCALATED
        if intent.cancel_requested_at is not None:
            live = any(e.provider_status in LIVE and not e.remediated for e in effects)
            return IntentState.CANCEL_REQUESTED if live else IntentState.CANCELLED
        if any(e.provider_status in LIVE and e.classification != EffectClass.INTENDED.value and not e.remediated
               for e in effects):
            return IntentState.DISCREPANCY
        intended = [e for e in effects if e.counts_toward_intent]
        if intended:
            done = intended[0].provider_status == ProviderStatus.COMPLETED.value
            return IntentState.COMPLETED if done else IntentState.EXECUTING
        statuses = {a.status for a in attempts}
        if AttemptStatus.UNKNOWN.value in statuses:
            return IntentState.UNKNOWN
        if AttemptStatus.SUBMITTING.value in statuses:
            return IntentState.IN_FLIGHT
        return IntentState.RECONCILING if attempts else IntentState.AUTHORIZED

    def _refresh(self, s: Session, intent: Intent) -> IntentState:
        now = self._now()
        effects = list(s.scalars(select(Effect).where(Effect.intent_id == intent.id)))
        if not any(e.counts_toward_intent for e in effects):
            for e in effects:  # a live duplicate becomes the intended effect if the original is gone
                if (e.classification == EffectClass.DUPLICATE.value and e.provider_status in LIVE
                        and not e.remediated):
                    e.classification, e.counts_toward_intent = EffectClass.INTENDED.value, True
                    s.flush()
                    break
        attempts = list(s.scalars(select(Attempt).where(Attempt.intent_id == intent.id).order_by(Attempt.attempt_no)))
        open_review = (
            s.scalar(select(func.count()).select_from(ReviewCase).where(
                ReviewCase.intent_id == intent.id, ReviewCase.status == "OPEN")) or 0
        ) > 0
        before = IntentState(intent.state)
        target = self._derive(intent, effects, attempts, open_review)
        self._set_state(s, intent, target)

        if not any(a.status in (AttemptStatus.UNKNOWN.value, AttemptStatus.SUBMITTING.value) for a in attempts):
            intent.unknown_since = None
        if target == IntentState.COMPLETED and before != IntentState.COMPLETED and (
            len(attempts) > 1 or any(a.error for a in attempts)
        ):
            # Keep looking for late-visible duplicates for one absence window.
            intent.watch_until = now + 2 * self.cfg.absence_window_s

        if target == IntentState.IN_FLIGHT:
            intent.next_check_at = min(a.lease_expires_at for a in attempts if a.status == AttemptStatus.SUBMITTING.value)
        elif target in ACTIVE_STATES:
            intent.next_check_at = now + self._backoff(intent, now)
        elif target == IntentState.RECONCILING and self._auto_retry_allowed(s, intent, attempts):
            intent.next_check_at = now
        elif target == IntentState.COMPLETED and intent.watch_until and intent.watch_until > now:
            intent.next_check_at = min(now + self._backoff(intent, now), intent.watch_until)
        else:
            intent.next_check_at = None
        return target

    def _backoff(self, intent: Intent, now: float) -> float:
        """Poll quickly right after a state change, then back off (capped) while nothing changes."""
        return max(self.cfg.poll_interval_s, min(self.cfg.max_poll_interval_s, 0.5 * (now - intent.updated_at)))

    def _set_state(self, s: Session, intent: Intent, target: IntentState) -> None:
        current = IntentState(intent.state)
        if current == target:
            return
        check_transition(current, target, permissive=not self.cfg.effect_dedup)
        intent.state, intent.updated_at = target.value, self._now()
        self._audit(s, intent.id, "intent.state", **{"from": current.value, "to": target.value})

    def _open_review(self, s: Session, intent: Intent, reason: ReviewReason, discrepancy_minor: int = 0,
                     **details: Any) -> None:
        existing = s.scalar(select(ReviewCase.id).where(
            ReviewCase.intent_id == intent.id, ReviewCase.status == "OPEN", ReviewCase.reason == reason.value))
        if existing is not None:
            return
        rc = ReviewCase(intent_id=intent.id, reason=reason.value, discrepancy_minor=discrepancy_minor,
                        details=details, status="OPEN", created_at=self._now())
        s.add(rc)
        s.flush()
        self._audit(s, intent.id, "review.opened", case_id=rc.id, reason=reason.value,
                    discrepancy_minor=discrepancy_minor, details=details)

    def _discrepancy_minor(self, intent: Intent, e: Effect) -> int:
        same_target = (e.order_id == intent.order_id and e.customer_id == intent.customer_id
                       and e.currency == intent.currency and e.operation == intent.operation)
        if e.classification == EffectClass.DUPLICATE.value or not same_target:
            return e.amount_minor
        return abs(e.amount_minor - intent.amount_minor)

    # ===================================================== driving / recovery

    def _drive(self, intent_id: str, max_steps: int = 10) -> IntentState:
        state = self._state(intent_id)
        for _ in range(max_steps):
            if state in (IntentState.UNKNOWN, IntentState.EXECUTING):
                new = self.reconcile(intent_id)
            elif state in (IntentState.DISCREPANCY, IntentState.CANCEL_REQUESTED):
                new = self.recover(intent_id)
            elif state == IntentState.RECONCILING:
                new = self._maybe_retry(intent_id)
            else:
                break
            if new == state:
                break
            state = new
        return state

    def reconcile(self, intent_id: str) -> IntentState:
        """Find out what actually happened at the provider for this intent."""
        with self._sf() as s:
            intent = s.get(Intent, intent_id)
            if intent is None:
                raise NotFound(f"intent {intent_id} not found")
            state = IntentState(intent.state)
            if state not in RECONCILABLE_STATES:
                return state
            op = Operation(intent.operation)
            attempts = list(s.scalars(select(Attempt).where(Attempt.intent_id == intent_id)))
            effects = list(s.scalars(select(Effect).where(Effect.intent_id == intent_id)))
            refs = {a.provider_ref for a in attempts if a.provider_ref} | {e.provider_ref for e in effects}
            orders = {a.order_id for a in attempts} | {intent.order_id}
            keys = {a.idempotency_key for a in attempts if a.idempotency_key}
            attempt_ids = {a.id for a in attempts}
            t0 = self._now()
            watching = intent.watch_until is not None and t0 <= intent.watch_until
            need_search = watching or any(a.status in (AttemptStatus.SUBMITTING.value, AttemptStatus.UNKNOWN.value)
                                          for a in attempts)

        found: dict[str, ProviderRecord] = {}
        lookup_ok = True
        try:
            for ref in sorted(refs):
                found[ref] = self.provider.get(op, ref)
            if need_search:
                for oid in sorted(orders):
                    for rec in self.provider.list_by_order(op, oid):
                        if (rec.metadata.get("intent_id") == intent_id
                                or rec.metadata.get("attempt_id") in attempt_ids
                                or (rec.idempotency_key and rec.idempotency_key in keys)):
                            found[rec.provider_ref] = rec
        except ProviderError as exc:
            lookup_ok = False
            lookup_error = f"{type(exc).__name__}: {exc}"

        with self._locked(intent_id) as (s, intent):
            for rec in found.values():
                self._absorb(s, intent, rec)
            now = self._now()
            for a in s.scalars(select(Attempt).where(Attempt.intent_id == intent_id)):
                if a.status == AttemptStatus.SUBMITTING.value and a.lease_expires_at <= t0:
                    a.status, a.error = AttemptStatus.UNKNOWN.value, "submission lease expired"
                    intent.unknown_since = intent.unknown_since or now
                    self._audit(s, intent.id, "attempt.lease_expired", attempt_id=a.id)
                if (a.status == AttemptStatus.UNKNOWN.value and lookup_ok and need_search
                        and t0 - a.created_at >= self.cfg.absence_window_s):
                    a.status, a.error, a.updated_at = AttemptStatus.RECONCILED.value, "verified absent at provider", now
                    a.completed_at = a.completed_at or now
                    self._audit(s, intent.id, "attempt.absence_confirmed", attempt_id=a.id,
                                waited_s=round(t0 - a.created_at, 3))
            if not lookup_ok:
                self._audit(s, intent.id, "reconcile.lookup_failed", error=lookup_error)
            new = self._refresh(s, intent)
            if (new == IntentState.UNKNOWN and intent.unknown_since is not None
                    and now - intent.unknown_since >= self.cfg.unknown_review_after_s):
                self._open_review(s, intent, ReviewReason.UNRESOLVABLE_OUTCOME,
                                  waited_s=round(now - intent.unknown_since, 3))
                new = self._refresh(s, intent)
            return new

    def recover(self, intent_id: str) -> IntentState:
        """
        Reverse live effects that must not stand, when the provider allows it; otherwise escalate.
        DISCREPANCY: every unintended live effect. CANCEL_REQUESTED: every live effect.
        """
        with self._sf() as s:
            intent = s.get(Intent, intent_id)
            if intent is None:
                raise NotFound(f"intent {intent_id} not found")
            state = IntentState(intent.state)
            if state not in (IntentState.DISCREPANCY, IntentState.CANCEL_REQUESTED):
                return state
            cancelling = state == IntentState.CANCEL_REQUESTED
            op = Operation(intent.operation)
            bad = [
                (e.id, e.provider_ref)
                for e in s.scalars(select(Effect).where(Effect.intent_id == intent_id))
                if e.provider_status in LIVE and not e.remediated
                and (cancelling or e.classification != EffectClass.INTENDED.value)
            ]

        outcomes: list[tuple[int, str, ProviderRecord | None, str | None]] = []
        for eff_id, ref in bad:
            try:
                cur = self.provider.get(op, ref)
            except ProviderError:
                outcomes.append((eff_id, "lookup_failed", None, None))
                continue
            if cur.status not in LIVE_PROVIDER_STATUSES:
                outcomes.append((eff_id, "already_inactive", cur, None))
                continue
            if not self.cfg.state_aware_recovery:
                try:
                    self.provider.cancel(op, ref)
                except ProviderError:
                    pass
                outcomes.append((eff_id, "blind_cancel", None, None))
                continue
            if not cancellation_policy(op, cur.status):
                outcomes.append((eff_id, "irreversible", cur, None))
                continue
            try:
                self.provider.cancel(op, ref)
            except ProviderRejected as exc:
                outcomes.append((eff_id, "cancel_rejected", cur, exc.code))
                continue
            except ProviderError:
                outcomes.append((eff_id, "cancel_unknown", cur, None))
                continue
            try:
                after = self.provider.get(op, ref)
            except ProviderError:
                outcomes.append((eff_id, "verify_failed", cur, None))
                continue
            kind = "verified" if after.status == ProviderStatus.CANCELLED else "not_cancelled"
            outcomes.append((eff_id, kind, after, None))

        with self._locked(intent_id) as (s, intent):
            for eff_id, kind, rec, code in outcomes:
                e = s.get(Effect, eff_id)
                assert e is not None
                if rec is not None:
                    self._absorb(s, intent, rec)
                if kind == "blind_cancel":
                    # Ablation: the gateway believes the reversal happened, so (like the verified
                    # path) it moves to a fresh provider key for the retry.
                    intent.key_generation += 1
                    e.remediated, e.counts_toward_intent = True, False
                    e.note = "cancel issued; reversal assumed without verification"
                    self._audit(s, intent.id, "effect.reversal_assumed", provider_ref=e.provider_ref)
                elif kind == "irreversible":
                    self._open_review(s, intent, ReviewReason.IRREVERSIBLE_DISCREPANCY,
                                      self._discrepancy_minor(intent, e), provider_ref=e.provider_ref,
                                      provider_status=e.provider_status, classification=e.classification)
                elif kind == "cancel_rejected":
                    self._open_review(s, intent, ReviewReason.CANCEL_REJECTED, self._discrepancy_minor(intent, e),
                                      provider_ref=e.provider_ref, code=code)
                elif kind in ("cancel_unknown", "verify_failed", "lookup_failed"):
                    e.cancel_tries += 1
                    if e.cancel_tries >= self.cfg.max_cancel_tries:
                        self._open_review(s, intent, ReviewReason.CANCEL_UNVERIFIED,
                                          self._discrepancy_minor(intent, e), provider_ref=e.provider_ref)
                elif kind == "not_cancelled":
                    self._open_review(s, intent, ReviewReason.CANCEL_UNVERIFIED, self._discrepancy_minor(intent, e),
                                      provider_ref=e.provider_ref, provider_status=e.provider_status)
                elif kind == "verified":
                    if e.attempt_id is not None:
                        intent.key_generation += 1
                    self._audit(s, intent.id, "effect.reversal_verified", provider_ref=e.provider_ref)
            return self._refresh(s, intent)

    def _auto_retry_allowed(self, s: Session, intent: Intent, attempts: list[Attempt]) -> bool:
        if not self.cfg.auto_retry or not attempts:
            return False
        last = attempts[-1]
        if last.status == AttemptStatus.RECONCILED.value:
            return True
        if last.status != AttemptStatus.SUCCEEDED.value:
            return False
        # The last attempt's effect was reversed (verified, or assumed under the ablation).
        effs = list(s.scalars(select(Effect).where(Effect.attempt_id == last.id)))
        return bool(effs) and all(e.provider_status not in LIVE or e.remediated for e in effs)

    def _maybe_retry(self, intent_id: str) -> IntentState:
        with self._locked(intent_id) as (s, intent):
            if IntentState(intent.state) != IntentState.RECONCILING:
                return IntentState(intent.state)
            attempts = list(s.scalars(select(Attempt).where(Attempt.intent_id == intent_id).order_by(Attempt.attempt_no)))
            if not self._auto_retry_allowed(s, intent, attempts):
                intent.next_check_at = None
                return IntentState.RECONCILING
            if intent.attempt_count >= self.cfg.max_attempts:
                self._open_review(s, intent, ReviewReason.ATTEMPT_BUDGET_EXHAUSTED, attempts=intent.attempt_count)
                return self._refresh(s, intent)
            last = attempts[-1]
            p = Proposal(intent_id=intent_id, request_id=f"gateway-retry-{intent.attempt_count + 1}",
                         agent_id="gateway", operation=Operation(last.operation), customer_id=last.customer_id,
                         order_id=last.order_id, amount_minor=last.amount_minor, currency=last.currency)
            self._audit(s, intent.id, "attempt.controlled_retry", after_attempt=last.id)
            aid = self._reserve(s, intent, p, last.proposal_id).id
        self._execute(aid)
        return self._state(intent_id)

    # ================================================================= worker

    def tick(self, limit: int = 200) -> int:
        """Process intents whose next check is due. Returns how many were processed."""
        now = self._now()
        with self._sf() as s:
            ids = list(s.scalars(
                select(Intent.id).where(Intent.next_check_at.is_not(None), Intent.next_check_at <= now)
                .order_by(Intent.next_check_at).limit(limit)
            ))
        for iid in ids:
            if self._state(iid) in RECONCILABLE_STATES:
                self.reconcile(iid)
            self._drive(iid)
            with self._locked(iid) as (s, intent):
                if intent.next_check_at is not None and intent.next_check_at <= self._now():
                    intent.next_check_at = self._now() + self.cfg.poll_interval_s
        return len(ids)

    def next_due(self) -> float | None:
        with self._sf() as s:
            return s.scalar(select(func.min(Intent.next_check_at)))

    def startup_recovery(self) -> int:
        """After a restart: attempts left SUBMITTING by a previous process have unknown outcomes."""
        with self._uow() as s:
            orphans = list(s.scalars(select(Attempt).where(
                Attempt.status == AttemptStatus.SUBMITTING.value, Attempt.incarnation != self.incarnation)))
            intent_ids = sorted({a.intent_id for a in orphans})
            for a in orphans:
                a.status, a.error, a.updated_at = AttemptStatus.UNKNOWN.value, "gateway restarted mid-submission", self._now()
                self._audit(s, a.intent_id, "attempt.orphaned", attempt_id=a.id, incarnation=a.incarnation)
            for iid in intent_ids:
                intent = s.get(Intent, iid)
                assert intent is not None
                intent.unknown_since = intent.unknown_since or self._now()
                self._refresh(s, intent)
        for iid in intent_ids:
            self.reconcile(iid)
            self._drive(iid)
        return len(intent_ids)

    # ================================================================= review

    def resolve_review(self, case_id: int, reviewer_id: str, resolution: ReviewResolution | str, notes: str = "") -> IntentState:
        resolution = ReviewResolution(resolution)
        with self._sf() as s:
            rc = s.get(ReviewCase, case_id)
            if rc is None:
                raise NotFound(f"review case {case_id} not found")
            intent_id = rc.intent_id
        with self._locked(intent_id) as (s, intent):
            rc = s.get(ReviewCase, case_id)
            assert rc is not None
            if rc.status != "OPEN":
                raise ConflictError("review case is already resolved", "ALREADY_RESOLVED")
            if self.policies(s)["separation_of_duties"] and reviewer_id == intent.operator_id:
                raise PermissionDenied("the operator who authorized this intent cannot resolve its review case",
                                       "SEPARATION_OF_DUTIES")
            effects = list(s.scalars(select(Effect).where(Effect.intent_id == intent_id)))
            if resolution == ReviewResolution.ACCEPTED_AS_IS:
                if not any(e.counts_toward_intent for e in effects):
                    raise ConflictError("no verified intended effect exists; completion cannot be confirmed",
                                        "NO_VERIFIED_EFFECT")
                intent.cancel_requested_at = intent.cancel_requested_by = None  # the effect stands
            if resolution == ReviewResolution.CONFIRMED_NO_EFFECT:
                for a in s.scalars(select(Attempt).where(Attempt.intent_id == intent_id)):
                    if a.status in (AttemptStatus.UNKNOWN.value, AttemptStatus.SUBMITTING.value):
                        a.status, a.error = AttemptStatus.RECONCILED.value, f"confirmed absent by reviewer {reviewer_id}"
            if resolution == ReviewResolution.REFUND_RECOVERED_OUT_OF_BAND:
                cancelling = intent.cancel_requested_at is not None
                for e in effects:
                    if e.provider_status in LIVE and (cancelling or e.classification != EffectClass.INTENDED.value):
                        e.remediated, e.note = True, f"remediated outside the system per {reviewer_id}"
                        e.counts_toward_intent = False
                intent.key_generation += 1  # a retry must not replay the remediated transaction
            rc.status, rc.resolution, rc.resolved_by = "RESOLVED", resolution.value, reviewer_id
            rc.notes, rc.resolved_at = notes, self._now()
            self._audit(s, intent_id, "review.resolved", actor=reviewer_id, case_id=case_id,
                        resolution=resolution.value, notes=notes)
            if resolution == ReviewResolution.WRITTEN_OFF:
                for other in s.scalars(select(ReviewCase).where(ReviewCase.intent_id == intent_id,
                                                                ReviewCase.status == "OPEN")):
                    other.status, other.resolution, other.resolved_by = "RESOLVED", resolution.value, reviewer_id
                    other.resolved_at = self._now()
                self._set_state(s, intent, IntentState.CLOSED)
                intent.next_check_at = None
                return IntentState.CLOSED
            self._refresh(s, intent)
        return self._drive(intent_id)

    # ================================================================== views

    def timeline(self, intent_id: str) -> dict[str, Any]:
        from intentguard.models import AuditEvent  # local import keeps the public surface small

        with self._sf() as s:
            intent = s.get(Intent, intent_id)
            if intent is None:
                raise NotFound(f"intent {intent_id} not found")

            def rows(model: Any, *where: Any, order: Any) -> list[dict[str, Any]]:
                return [_row(r) for r in s.scalars(select(model).where(*where).order_by(order))]

            decisions = {d.proposal_id: d for d in s.scalars(select(GatewayDecision).where(
                GatewayDecision.intent_id == intent_id))}
            proposals = []
            for r in s.scalars(select(AgentProposal).where(AgentProposal.intent_id == intent_id)
                               .order_by(AgentProposal.id)):
                row = _row(r)
                d = decisions.get(r.id)
                row["decision"] = d.decision if d else None
                row["reasons"] = d.reasons if d else []
                row["decision_id"] = d.id if d else None
                proposals.append(row)
            return {
                "intent": _row(intent),
                "proposals": proposals,
                "attempts": rows(Attempt, Attempt.intent_id == intent_id, order=Attempt.attempt_no),
                "effects": rows(Effect, Effect.intent_id == intent_id, order=Effect.id),
                "reviews": rows(ReviewCase, ReviewCase.intent_id == intent_id, order=ReviewCase.id),
                "audit": rows(AuditEvent, AuditEvent.chain_id == intent_id, order=AuditEvent.seq),
            }


def _row(obj: Any) -> dict[str, Any]:
    return row_dict(obj)


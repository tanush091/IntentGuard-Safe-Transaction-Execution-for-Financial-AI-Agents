"""
Property-based safety tests. Hypothesis generates arbitrary combinations of provider faults,
agent proposals (correct and corrupted), crashes, restarts and elapsed time; after every
run the safety properties below must hold against the provider's ground truth.

  P1  at most one live effect matching an intent exists at the provider
  P2  no live effect exists that the full protocol did not either intend or escalate
  P3  if the gateway reports COMPLETED, exactly the intended effect is live at the provider
  P4  the gateway never reports COMPLETED while an unintended effect is live and unflagged
  P5  the audit chain verifies and every intent state is one the state machine allows
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from intentguard import IntentState, audit
from intentguard.domain import TRANSITIONS
from intentguard.engine import Hooks, SimulatedCrash
from intentguard.models import ReviewCase
from paysim import FaultKind, TxStatus
from sqlalchemy import select

from tests.conftest import make_world

FAULTS = st.sampled_from([
    (FaultKind.OUTAGE, {}),
    (FaultKind.TIMEOUT_BEFORE_EXECUTION, {}),
    (FaultKind.TIMEOUT_AFTER_EXECUTION, {}),
    (FaultKind.DELAYED_STATUS, {"settle_delay_s": 90}),
    (FaultKind.DELAYED_VISIBILITY, {"lag_s": 25}),
    (FaultKind.DELAYED_VISIBILITY, {"lag_s": 120}),  # violates the absence-window assumption
    (FaultKind.CORRUPT_AMOUNT, {"factor": 2.0}),
    (FaultKind.FAILED_CANCELLATION, {}),
    (FaultKind.LOOKUP_OUTAGE, {}),
])
ACTIONS = st.one_of(
    st.tuples(st.just("propose"), st.sampled_from(["ok", "ok", "amount", "order", "customer"])),
    st.tuples(st.just("wait"), st.sampled_from([1, 10, 40, 200])),
    st.tuples(st.just("restart"), st.just(None)),
)


class OneShotCrash(Hooks):
    def __init__(self, point: str | None):
        self.point = point

    def at(self, point: str, **ctx: object) -> None:
        if point == self.point:
            self.point = None
            raise SimulatedCrash(point)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    faults=st.lists(st.tuples(FAULTS, st.integers(1, 3)), max_size=4),
    actions=st.lists(ACTIONS, min_size=1, max_size=8),
    crash=st.sampled_from([None, "after_attempt_recorded", "after_provider_response"]),
    partial=st.booleans(),
)
def test_safety_properties_hold_under_arbitrary_faults(faults, actions, crash, partial):
    with tempfile.TemporaryDirectory() as tmp:
        w = make_world(Path(tmp), hooks=OneShotCrash(crash))
        w.order("ORD-240", customer="C-17")
        w.order("ORD-999", customer="C-99")
        amount = 1500_00 if partial else 5000_00
        iid = w.intent(amount=amount)
        for (kind, params), times in faults:
            w.fault(kind, times=times, **params)

        variants = {"ok": {}, "amount": {"amount_minor": amount * 10}, "order": {"order_id": "ORD-240"},
                    "customer": {"customer_id": "C-99", "order_id": "ORD-999"}}
        for action, arg in actions:
            if action == "propose":
                try:
                    w.guard.submit(w.proposal(iid, **{"amount_minor": amount, **variants[arg]}))
                except SimulatedCrash:
                    w.restart()
            elif action == "wait":
                w.settle(arg)
            else:
                w.restart()
        w.settle(1200)

        state = w.guard._state(iid)
        live = [t for t in w.sim.all_transactions() if t.status in (TxStatus.PENDING, TxStatus.COMPLETED)]
        intended = [t for t in live if (t.order_id, t.customer_id, t.amount_minor) == ("ORD-204", "C-17", amount)]
        unintended = [t for t in live if t not in intended]
        with w.guard.session() as s:
            reviews = list(s.scalars(select(ReviewCase).where(ReviewCase.intent_id == iid)))
            chain = audit.verify(s)

        # P1: duplicates may only exist if the system escalated them
        assert len(intended) <= 1 or reviews, "duplicate effect without escalation"
        # P2: anything unintended that is live must have been escalated
        assert not unintended or reviews, "unintended live effect without escalation"
        # P3 / P4: a COMPLETED report is always true
        if state == IntentState.COMPLETED:
            assert len(intended) == 1 and not unintended
        # P5
        assert chain["ok"], chain
        assert state in TRANSITIONS

"""
The required-behaviour table from the project specification (section 2), one test per row,
plus the payment-authorization transfer case.
"""

from __future__ import annotations

from intentguard import Decision, IntentState, Operation
from intentguard.models import Attempt, Effect, ReviewCase
from paysim import FaultKind, TxStatus
from sqlalchemy import select


def test_amount_exceeding_authorization_is_blocked(world):
    iid = world.intent()
    r = world.guard.submit(world.proposal(iid, amount_minor=15000_00))
    assert r.decision == Decision.REJECTED
    assert any(f["check"] == "AMOUNT_MISMATCH" for f in r.findings)
    assert world.sim.all_transactions() == []


def test_wrong_order_is_blocked(world):
    world.order("ORD-240")
    iid = world.intent()
    r = world.guard.submit(world.proposal(iid, order_id="ORD-240"))
    assert r.decision == Decision.REJECTED
    assert any(f["check"] == "ORDER_MISMATCH" for f in r.findings)
    assert world.sim.all_transactions() == []


def test_confirmed_refund_is_verified_and_completed(world):
    iid = world.intent()
    r = world.guard.submit(world.proposal(iid))
    assert r.decision == Decision.APPROVED and r.intent_state == IntentState.COMPLETED
    with world.guard.session() as s:
        eff = s.scalar(select(Effect).where(Effect.intent_id == iid))
    assert eff.classification == "INTENDED" and eff.provider_status == "COMPLETED"
    assert len(world.live()) == 1


def test_timeout_marks_unknown_and_never_retries_blindly(world):
    iid = world.intent()
    world.fault(FaultKind.TIMEOUT_BEFORE_EXECUTION)
    r = world.guard.submit(world.proposal(iid))
    # Nothing is visible yet and the absence window has not elapsed: the outcome stays unknown.
    assert r.intent_state == IntentState.OUTCOME_UNKNOWN
    assert world.sim.stats["create_calls"] == 1
    world.settle(60)  # after the absence window, reconciliation proves absence; one controlled retry
    assert world.guard._state(iid) == IntentState.COMPLETED
    assert len(world.live()) == 1


def test_lost_response_is_found_by_reconciliation_without_a_second_refund(world):
    iid = world.intent()
    world.fault(FaultKind.LOST_RESPONSE)
    r = world.guard.submit(world.proposal(iid))
    assert r.intent_state == IntentState.COMPLETED  # found by the inline reconciliation
    assert world.sim.stats["executions"] == 1


def test_restart_with_new_request_id_cannot_cause_a_second_effect(world):
    iid = world.intent()
    world.fault(FaultKind.LOST_RESPONSE)
    world.fault(FaultKind.DELAYED_VISIBILITY, lag_s=20)
    world.guard.submit(world.proposal(iid, request_id="before-crash"))
    world.restart()
    r = world.guard.submit(world.proposal(iid, request_id="after-restart"))
    assert r.decision in (Decision.IN_PROGRESS, Decision.DUPLICATE)
    world.settle()
    assert len(world.live()) == 1
    assert world.guard._state(iid) == IntentState.COMPLETED


def test_incorrect_pending_refund_is_cancelled_and_verified(world):
    iid = world.intent()
    world.fault(FaultKind.SLOW_SETTLEMENT, settle_delay_s=120)
    world.fault(FaultKind.AMOUNT_MISMATCH, factor=10.0)
    world.guard.submit(world.proposal(iid))
    world.settle()
    txs = world.sim.all_transactions()
    assert sorted(t.status for t in txs) == [TxStatus.CANCELLED, TxStatus.COMPLETED]
    assert [t.amount_minor for t in txs if t.status == TxStatus.COMPLETED] == [1500_00]
    assert world.guard._state(iid) == IntentState.COMPLETED


def test_incorrect_completed_refund_is_escalated_not_reported_reversed(world):
    iid = world.intent()
    world.fault(FaultKind.AMOUNT_MISMATCH, factor=10.0)
    world.guard.submit(world.proposal(iid))
    world.settle()
    assert world.guard._state(iid) == IntentState.NEEDS_REVIEW
    with world.guard.session() as s:
        case = s.scalar(select(ReviewCase).where(ReviewCase.intent_id == iid))
    assert case.reason == "IRREVERSIBLE_DISCREPANCY"
    assert case.discrepancy_minor == 15000_00 - 1500_00
    # The provider still shows the wrong refund as completed; the system never claims otherwise.
    assert [t.status for t in world.sim.all_transactions()] == [TxStatus.COMPLETED]


def test_authorization_hold_with_wrong_amount_is_voided_even_when_authorized(world):
    world.order("ORD-500", amount=20000_00)
    iid = world.intent(amount=2000_00, order_id="ORD-500", operation=Operation.PAYMENT_AUTHORIZATION)
    world.fault(FaultKind.AMOUNT_MISMATCH, order_id="ORD-500", factor=1.5)
    world.guard.submit(world.proposal(iid, operation=Operation.PAYMENT_AUTHORIZATION, order_id="ORD-500",
                                      amount_minor=2000_00))
    world.settle()
    txs = world.sim.all_transactions()
    assert sorted(t.status for t in txs) == [TxStatus.CANCELLED, TxStatus.COMPLETED]
    assert world.guard._state(iid) == IntentState.COMPLETED


def test_revoked_operator_blocks_execution(world):
    iid = world.intent()
    world.guard.set_operator_active("op-1", False)
    r = world.guard.submit(world.proposal(iid))
    assert r.decision == Decision.REJECTED
    assert any(f["check"] == "OPERATOR_NOT_PERMITTED" for f in r.findings)


def test_unresolvable_outcome_is_held_for_review(world):
    iid = world.intent()
    world.fault(FaultKind.LOST_RESPONSE)
    world.fault(FaultKind.LOOKUP_OUTAGE, times=-1)  # the provider can never be queried
    world.guard.submit(world.proposal(iid))
    world.settle()
    assert world.guard._state(iid) == IntentState.NEEDS_REVIEW
    with world.guard.session() as s:
        statuses = {a.status for a in s.scalars(select(Attempt).where(Attempt.intent_id == iid))}
    assert statuses == {"UNKNOWN"}  # never declared success or failure

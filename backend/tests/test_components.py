"""Unit tests for the building blocks: money, simulator semantics, audit chain, extraction, state machine."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from intentguard import audit
from intentguard.agents import ExtractionError, extract
from intentguard.domain import IllegalTransition, IntentState, Operation, check_transition
from intentguard.money import MoneyError, fmt, to_minor
from paysim import (
    Fault,
    FaultKind,
    Order,
    PaymentSimulator,
    SimConflict,
    SimRejected,
    SimTimeout,
    TxKind,
    TxStatus,
)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def sim():
    c = Clock()
    s = PaymentSimulator(c, id_seed=3)
    s.add_order(Order("ORD-1", "C-1", "INR", 1000_00))
    s.clock = c  # type: ignore[attr-defined]
    return s


# ------------------------------------------------------------------- money

def test_money_round_trip_and_precision():
    assert to_minor("1,500.00".replace(",", ""), "INR") == 150000
    assert to_minor("15", "JPY") == 15
    assert fmt(150000, "INR") == "₹1,500.00"
    with pytest.raises(MoneyError):
        to_minor("1.005", "INR")


# --------------------------------------------------------------- simulator

def test_refund_settles_and_can_only_be_cancelled_while_pending(sim):
    sim.default_settle_delay_s = 10
    tx = sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=100_00, currency="INR")
    assert tx.status == TxStatus.PENDING and PaymentSimulator.is_cancellable(tx)
    sim.clock.t = 11
    assert sim.get(tx.id).status == TxStatus.COMPLETED
    with pytest.raises(SimConflict):
        sim.cancel(tx.id)


def test_authorization_can_be_voided_after_completion(sim):
    tx = sim.create(TxKind.AUTHORIZATION, order_id="ORD-1", customer_id="C-1", amount_minor=100_00, currency="INR")
    assert sim.get(tx.id).status == TxStatus.COMPLETED
    assert sim.cancel(tx.id).status == TxStatus.CANCELLED


def test_idempotency_replays_and_rejects_changed_parameters(sim):
    a = sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=100_00, currency="INR",
                   idempotency_key="k1")
    b = sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=100_00, currency="INR",
                   idempotency_key="k1")
    assert a.id == b.id and sim.stats["executions"] == 1
    with pytest.raises(SimRejected) as exc:
        sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=200_00, currency="INR",
                   idempotency_key="k1")
    assert exc.value.code == "idempotency_key_reuse"


def test_balance_and_ownership_are_enforced_by_the_provider(sim):
    with pytest.raises(SimRejected):
        sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-2", amount_minor=1, currency="INR")
    sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=900_00, currency="INR")
    with pytest.raises(SimRejected) as exc:
        sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=200_00, currency="INR")
    assert exc.value.code == "insufficient_balance"


def test_lost_response_executes_and_delayed_visibility_hides_it_from_search(sim):
    sim.inject(Fault(FaultKind.TIMEOUT_AFTER_EXECUTION, "ORD-1"))
    sim.inject(Fault(FaultKind.DELAYED_VISIBILITY, "ORD-1", params={"lag_s": 30}))
    with pytest.raises(SimTimeout):
        sim.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=100_00, currency="INR")
    assert sim.list_by_order("ORD-1") == []
    assert len(sim.all_transactions()) == 1
    sim.clock.t = 31
    assert len(sim.list_by_order("ORD-1")) == 1


def test_simulator_state_survives_restart(tmp_path):
    path = str(tmp_path / "paysim.json")
    s1 = PaymentSimulator(lambda: 0.0, state_path=path, id_seed=1)
    s1.add_order(Order("ORD-1", "C-1", "INR", 1000_00))
    tx = s1.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=1, currency="INR",
                   idempotency_key="k")
    s2 = PaymentSimulator(lambda: 0.0, state_path=path)
    assert s2.get(tx.id).amount_minor == 1
    assert s2.create(TxKind.REFUND, order_id="ORD-1", customer_id="C-1", amount_minor=1, currency="INR",
                     idempotency_key="k").id == tx.id


# ------------------------------------------------------------------- audit

def test_audit_log_is_append_only_and_tamper_evident(world):
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    with world.guard.session() as s:
        assert audit.verify(s)["ok"]
    with world.guard.session() as s, pytest.raises(DBAPIError):
        s.execute(text("UPDATE audit_logs SET kind = 'forged' WHERE seq = 1"))
        s.commit()
    with world.guard.session() as s, pytest.raises(DBAPIError):
        s.execute(text("DELETE FROM audit_logs"))
        s.commit()
    # Someone with schema access drops the trigger and rewrites history: verification catches it.
    with world.guard.session() as s:
        s.execute(text("DROP TRIGGER audit_no_update"))
        s.execute(text("UPDATE audit_logs SET payload = '{}' WHERE seq = 2"))
        s.commit()
        result = audit.verify(s)
    assert not result["ok"] and result["broken_at_seq"] == 2


# --------------------------------------------------------------- extraction

@pytest.mark.parametrize("ticket, order, customer, amount, currency", [
    ("Refund ₹1,500 for order ORD-204 to customer C-17.", "ORD-204", "C-17", 150000, "INR"),
    ("Customer C-17: refund INR 1500 on ORD-204", "ORD-204", "C-17", 150000, "INR"),
    ("C-1712 asks for 45.50 USD back on ORD-2041", "ORD-2041", "C-1712", 4550, "USD"),
    ("Refund Rs. 2,400.00 for ORD-311 (C-17). Customer also asked about ORD-312.", "ORD-311", "C-17", 240000, "INR"),
])
def test_extraction_never_confuses_ids_with_amounts(ticket, order, customer, amount, currency):
    ex = extract(ticket)
    assert (ex.order_id, ex.customer_id, ex.amount_minor, ex.currency) == (order, customer, amount, currency)
    assert ex.operation == Operation.REFUND


def test_extraction_detects_authorization_and_rejects_incomplete_tickets():
    assert extract("Authorize a hold of ₹500 on ORD-9 for C-3").operation == Operation.PAYMENT_AUTHORIZATION
    with pytest.raises(ExtractionError):
        extract("Please refund the customer")


# ----------------------------------------------------------- state machine

def test_state_machine_rejects_illegal_transitions():
    check_transition(IntentState.AUTHORIZED, IntentState.IN_FLIGHT)
    with pytest.raises(IllegalTransition):
        check_transition(IntentState.COMPLETED, IntentState.IN_FLIGHT)
    with pytest.raises(IllegalTransition):
        check_transition(IntentState.CANCELLED, IntentState.AUTHORIZED)

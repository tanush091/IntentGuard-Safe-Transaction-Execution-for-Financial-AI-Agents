"""
Engine features from docs/API.md and docs/SECURITY.md: operator cancellation (verified), the kill
switch, policy limits, separation of duties, review resolutions, identifiers, schema versioning,
and the remaining-balance check.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select, text

from intentguard import Decision, IntentState, Operation
from intentguard.db import SchemaMismatch, init_schema, make_engine
from intentguard.engine import AuthorizationError, ConflictError, PermissionDenied
from intentguard.models import AgentProposal, Attempt, Effect, GatewayDecision, ReviewCase
from paysim import FaultKind, TxStatus


def _review_case(world, iid):
    with world.guard.session() as s:
        return s.scalar(select(ReviewCase).where(ReviewCase.intent_id == iid, ReviewCase.status == "OPEN"))


# ------------------------------------------------------------------ identifiers


def test_intents_attempts_and_decisions_use_readable_ids_and_separate_records(world):
    iid = world.intent()
    assert iid == "INT-1001"
    r = world.guard.submit(world.proposal(iid))
    assert r.attempt_id == "ATT-001"
    with world.guard.session() as s:
        prop = s.get(AgentProposal, r.proposal_id)
        dec = s.scalar(select(GatewayDecision).where(GatewayDecision.proposal_id == r.proposal_id))
    assert prop.status == "VALIDATED" and dec.decision == "ALLOW"
    bad = world.guard.submit(world.proposal(world.intent(), amount_minor=1_00))
    with world.guard.session() as s:
        assert s.get(AgentProposal, bad.proposal_id).status == "REJECTED"
    assert any(f["check"] == "AMOUNT_BELOW_AUTHORIZATION" for f in bad.findings)


# ----------------------------------------------------------------------- cancel


def test_cancel_without_effect_is_immediate(world):
    iid = world.intent()
    assert world.guard.cancel(iid, "op-1") == IntentState.CANCELLED
    r = world.guard.submit(world.proposal(iid))
    assert r.decision == Decision.REJECT and r.findings[0]["check"] == "INTENT_NOT_ACTIVE"
    assert world.sim.all_transactions() == []


def test_cancel_of_pending_refund_is_verified_at_the_provider(world):
    world.fault(FaultKind.DELAYED_STATUS, settle_delay_s=120)
    iid = world.intent()
    assert world.guard.submit(world.proposal(iid)).intent_state == IntentState.EXECUTING
    assert world.guard.cancel(iid, "op-1") == IntentState.CANCELLED
    [tx] = world.sim.all_transactions()
    assert tx.status == TxStatus.CANCELLED and world.live() == []


def test_completed_refund_cannot_be_cancelled(world):
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    with pytest.raises(ConflictError) as exc:
        world.guard.cancel(iid, "op-1")
    assert exc.value.code == "NOT_CANCELLABLE"
    assert world.guard._state(iid) == IntentState.COMPLETED and len(world.live()) == 1


def test_completed_authorization_hold_can_be_voided(world):
    iid = world.intent(operation=Operation.PAYMENT_AUTHORIZATION)
    r = world.guard.submit(world.proposal(iid, operation=Operation.PAYMENT_AUTHORIZATION))
    assert r.intent_state == IntentState.COMPLETED
    assert world.guard.cancel(iid, "op-1") == IntentState.CANCELLED
    assert [t.status for t in world.sim.all_transactions()] == [TxStatus.CANCELLED]


def test_failed_cancellation_escalates_and_can_be_written_off(world):
    world.fault(FaultKind.DELAYED_STATUS, settle_delay_s=120)
    world.fault(FaultKind.FAILED_CANCELLATION)
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    assert world.guard.cancel(iid, "op-1") == IntentState.ESCALATED
    rc = _review_case(world, iid)
    assert rc.reason == "CANCEL_REJECTED"
    assert world.guard.resolve_review(rc.id, "rev-1", "WRITTEN_OFF") == IntentState.CLOSED


def test_cancel_refused_while_outcome_unknown(world):
    world.fault(FaultKind.TIMEOUT_AFTER_EXECUTION)
    world.fault(FaultKind.LOOKUP_OUTAGE, times=-1)
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    assert world.guard._state(iid) == IntentState.UNKNOWN
    with pytest.raises(ConflictError) as exc:
        world.guard.cancel(iid, "op-1")
    assert exc.value.code == "ATTEMPT_IN_PROGRESS"


# ------------------------------------------------------------------- policies


def test_kill_switch_holds_every_new_proposal_without_provider_calls(world):
    iid = world.intent()
    world.guard.set_policy("kill_switch", True, "admin")
    r = world.guard.submit(world.proposal(iid))
    assert r.decision == Decision.HOLD_FOR_REVIEW and r.findings[-1]["check"] == "KILL_SWITCH"
    assert world.sim.stats["create_calls"] == 0 and world.guard._state(iid) == IntentState.AUTHORIZED
    world.guard.set_policy("kill_switch", False, "admin")
    assert world.guard.submit(world.proposal(iid)).decision == Decision.ALLOW


def test_policy_amount_limit_applies_to_new_and_existing_intents(world):
    iid = world.intent(amount=1500_00)
    world.guard.set_policy("max_amount_minor", 1000_00, "admin")
    with pytest.raises(AuthorizationError) as exc:
        world.intent(amount=1200_00)
    assert exc.value.code == "POLICY_LIMIT_EXCEEDED"
    r = world.guard.submit(world.proposal(iid))
    assert r.decision == Decision.REJECT and any(f["check"] == "POLICY_LIMIT_EXCEEDED" for f in r.findings)
    assert world.sim.all_transactions() == []


def test_remaining_order_balance_is_enforced_by_the_gateway(world):
    first = world.intent(amount=4000_00)
    world.guard.submit(world.proposal(first, amount_minor=4000_00))
    second = world.intent(amount=1500_00)  # 4000 + 1500 > 5000 order value
    r = world.guard.submit(world.proposal(second))
    assert r.decision == Decision.REJECT
    assert [f["check"] for f in r.findings] == ["EXCEEDS_REMAINING_BALANCE"]
    assert world.sim.stats["create_calls"] == 1


# ------------------------------------------------------------ review resolutions


def _escalated_lost_response(world):
    world.fault(FaultKind.TIMEOUT_AFTER_EXECUTION)
    world.fault(FaultKind.LOOKUP_OUTAGE, times=-1)
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    world.settle()
    assert world.guard._state(iid) == IntentState.ESCALATED
    return iid, _review_case(world, iid)


def test_separation_of_duties_blocks_the_authorizing_operator(world):
    iid, rc = _escalated_lost_response(world)
    with pytest.raises(PermissionDenied) as exc:
        world.guard.resolve_review(rc.id, "op-1", "OTHER")
    assert exc.value.code == "SEPARATION_OF_DUTIES"
    world.guard.set_policy("separation_of_duties", False, "admin")
    world.sim.clear_faults()
    world.guard.resolve_review(rc.id, "op-1", "OTHER")


def test_accepted_as_is_requires_a_verified_effect(world):
    iid, rc = _escalated_lost_response(world)
    with pytest.raises(ConflictError) as exc:
        world.guard.resolve_review(rc.id, "rev-1", "ACCEPTED_AS_IS")
    assert exc.value.code == "NO_VERIFIED_EFFECT"


def test_accepted_as_is_keeps_a_refund_whose_cancellation_failed(world):
    world.fault(FaultKind.DELAYED_STATUS, settle_delay_s=120)
    world.fault(FaultKind.FAILED_CANCELLATION)
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    assert world.guard.cancel(iid, "op-1") == IntentState.ESCALATED
    rc = _review_case(world, iid)
    assert world.guard.resolve_review(rc.id, "rev-1", "ACCEPTED_AS_IS") == IntentState.EXECUTING
    world.settle()
    assert world.guard._state(iid) == IntentState.COMPLETED and len(world.live()) == 1


def test_confirmed_no_effect_allows_a_controlled_retry(world):
    world.fault(FaultKind.TIMEOUT_BEFORE_EXECUTION)
    world.fault(FaultKind.LOOKUP_OUTAGE, times=-1)
    iid = world.intent()
    world.guard.submit(world.proposal(iid))
    world.settle()
    rc = _review_case(world, iid)
    world.sim.clear_faults()
    assert world.guard.resolve_review(rc.id, "rev-1", "CONFIRMED_NO_EFFECT") == IntentState.COMPLETED
    with world.guard.session() as s:
        attempts = list(s.scalars(select(Attempt).where(Attempt.intent_id == iid)))
    # The retry reuses the intent's key, so the provider transaction is attributed to both attempts.
    assert len(attempts) == 2 and len(world.live()) == 1


def test_other_resolution_reescalates_while_the_provider_is_unreachable(world):
    iid, rc = _escalated_lost_response(world)
    assert world.guard.resolve_review(rc.id, "rev-1", "OTHER") == IntentState.ESCALATED
    new_case = _review_case(world, iid)
    assert new_case.id != rc.id and new_case.reason == "UNRESOLVABLE_OUTCOME"


def test_other_resolution_reconciles_once_the_provider_answers(world):
    iid, rc = _escalated_lost_response(world)
    world.sim.clear_faults()
    assert world.guard.resolve_review(rc.id, "rev-1", "OTHER", "provider is back") == IntentState.COMPLETED
    assert len(world.live()) == 1  # the lost refund was found, not repeated


# ---------------------------------------------------------------------- schema


def test_database_from_an_earlier_version_is_refused(tmp_path):
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    raw = create_engine(url)
    with raw.begin() as c:
        c.execute(text("CREATE TABLE audit_events (seq INTEGER PRIMARY KEY)"))
    raw.dispose()
    with pytest.raises(SchemaMismatch):
        init_schema(make_engine(url))


def test_proposal_rows_never_store_the_effect_when_rejected(world):
    iid = world.intent()
    world.guard.submit(world.proposal(iid, order_id="ORD-999"))
    with world.guard.session() as s:
        assert s.scalar(select(Effect).where(Effect.intent_id == iid)) is None

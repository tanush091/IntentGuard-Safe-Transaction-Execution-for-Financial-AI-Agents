"""
Safety Invariant & Safety Property Verification Tests for IntentGuard.
Directly validates Properties 1 through 6 defined in research specification.
"""

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.database import Base
from backend.app.models.intent import IntentModel
from backend.app.models.effect import EffectModel
from backend.app.schemas.intent import IntentCreate, OperationType
from backend.app.schemas.proposal import AgentProposal
from backend.app.services.authorization_service import AuthorizationService
from backend.app.services.gateway_service import GatewayService
from backend.app.services.idempotency_service import IdempotencyService
from backend.app.services.audit_service import AuditService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_property_2_mismatched_proposal_is_blocked(db_session):
    """
    Property 2: A proposal that does not match the durable authorization must not reach the payment service.
    """
    intent_in = IntentCreate(
        intent_id="INT-PROP2",
        operator_id="OP-10",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND,
        authorized_amount=1500.0,
        currency="INR"
    )
    intent = AuthorizationService.create_intent(db_session, intent_in)

    # 1. Wrong Amount (₹15,000 instead of ₹1,500)
    proposal_amount = AgentProposal(
        intent_id=intent.id,
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-204",
        amount=15000.0,
        currency="INR"
    )
    result = GatewayService.evaluate_proposal(db_session, intent, proposal_amount)
    assert result.decision == "BLOCKED"
    assert "CHECK_4_AMOUNT_MISMATCH" in result.checks_failed[0]

    # Reset state to test order mismatch
    intent.current_state = "AUTHORIZED"
    db_session.commit()

    # 2. Wrong Order (ORD-240 instead of ORD-204)
    proposal_order = AgentProposal(
        intent_id=intent.id,
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-240",
        amount=1500.0,
        currency="INR"
    )
    result_order = GatewayService.evaluate_proposal(db_session, intent, proposal_order)
    assert result_order.decision == "BLOCKED"
    assert "CHECK_2_ORDER_MISMATCH" in result_order.checks_failed[0]


def test_property_1_duplicate_completed_effect_prevention(db_session):
    """
    Property 1: One authorized refund should produce at most one completed refund effect.
    """
    intent_in = IntentCreate(
        intent_id="INT-PROP1",
        operator_id="OP-10",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND,
        authorized_amount=1500.0,
        currency="INR"
    )
    intent = AuthorizationService.create_intent(db_session, intent_in)

    # Simulate that an effect already settled in the ledger
    effect = EffectModel(
        id="eff-prior",
        intent_id=intent.id,
        provider_reference="ref_prior_999",
        effect_type="REFUND",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR",
        status="COMPLETED"
    )
    db_session.add(effect)
    intent.current_state = "COMPLETED"
    db_session.commit()

    # AI tries to propose the same refund again (e.g. after restart or prompt loop)
    proposal = AgentProposal(
        intent_id=intent.id,
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR"
    )
    eval_result = GatewayService.evaluate_proposal(db_session, intent, proposal)
    assert eval_result.decision == "BLOCKED"
    assert any("DUPLICATE_EFFECT" in f for f in eval_result.checks_failed)


def test_property_4_audit_history_preservation(db_session):
    """
    Property 4: Audit history must not be silently deleted or overwritten.
    """
    intent_in = IntentCreate(
        intent_id="INT-AUDIT",
        operator_id="OP-10",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND,
        authorized_amount=1500.0,
        currency="INR"
    )
    intent = AuthorizationService.create_intent(db_session, intent_in)

    AuditService.record_event(
        db=db_session,
        intent_id=intent.id,
        event_type="CUSTOM_CHECK",
        decision="BLOCKED",
        reason="Test audit event 1"
    )
    AuditService.record_event(
        db=db_session,
        intent_id=intent.id,
        event_type="CUSTOM_CHECK",
        decision="APPROVED",
        reason="Test audit event 2"
    )

    events = AuditService.get_events_for_intent(db_session, intent.id)
    # Events include creation + the 2 custom events
    assert len(events) >= 3
    # Ordered chronologically
    assert events[-1].reason == "Test audit event 2"

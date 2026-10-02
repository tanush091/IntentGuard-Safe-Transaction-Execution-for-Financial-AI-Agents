import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, AuthorizationModel, EffectModel
from src.schemas.types import (
    ProposalCreate, AuthorizationCreate, OperationType,
    DecisionType, DecisionReason, IntentState, ProviderTransactionStatus
)
from src.gateway.validator import GatewayValidator

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_validate_amount_exceeded(db_session):
    auth = AuthorizationModel(
        intent_id="INT-V1",
        operator_id="OP-01",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND.value,
        authorized_amount=1500.0,
        currency="INR"
    )
    db_session.add(auth)
    db_session.commit()

    prop = ProposalCreate(
        intent_id="INT-V1",
        request_id="req-1",
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-204",
        amount=15000.0, # 10x authorized!
        currency="INR"
    )
    res = GatewayValidator.validate_proposal(db_session, prop, auth)
    assert not res.is_valid
    assert res.decision == DecisionType.BLOCK
    assert res.reason == DecisionReason.AMOUNT_EXCEEDS_AUTHORIZATION

def test_validate_order_mismatch(db_session):
    auth = AuthorizationModel(
        intent_id="INT-V2",
        operator_id="OP-01",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND.value,
        authorized_amount=1500.0,
        currency="INR"
    )
    db_session.add(auth)
    db_session.commit()

    prop = ProposalCreate(
        intent_id="INT-V2",
        request_id="req-1",
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-240", # Transposed!
        amount=1500.0,
        currency="INR"
    )
    res = GatewayValidator.validate_proposal(db_session, prop, auth)
    assert not res.is_valid
    assert res.decision == DecisionType.BLOCK
    assert res.reason == DecisionReason.ORDER_MISMATCH

def test_validate_duplicate_prevention(db_session):
    auth = AuthorizationModel(
        intent_id="INT-V3",
        operator_id="OP-01",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND.value,
        authorized_amount=1500.0,
        currency="INR",
        current_state=IntentState.COMPLETED.value
    )
    db_session.add(auth)
    # Add completed effect to ledger
    eff = EffectModel(
        effect_id="eff-01",
        intent_id="INT-V3",
        provider_transaction_id="ref_123",
        customer_id="C-17",
        order_id="ORD-204",
        operation=OperationType.REFUND.value,
        amount=1500.0,
        currency="INR",
        status=ProviderTransactionStatus.COMPLETED.value
    )
    db_session.add(eff)
    db_session.commit()

    prop = ProposalCreate(
        intent_id="INT-V3",
        request_id="req-new-attempt",
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR"
    )
    res = GatewayValidator.validate_proposal(db_session, prop, auth)
    assert not res.is_valid
    assert res.decision == DecisionType.BLOCK
    assert res.reason == DecisionReason.ALREADY_COMPLETED

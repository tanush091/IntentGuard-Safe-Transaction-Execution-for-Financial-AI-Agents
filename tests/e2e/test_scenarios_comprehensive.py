import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, AuthorizationModel, ReviewCaseModel, EffectModel
from src.schemas.types import (
    AuthorizationCreate, ProposalCreate, OperationType,
    FaultType, DecisionType, DecisionReason, IntentState
)
from src.gateway.engine import GatewayEngine
from src.gateway.recovery import RecoveryPolicyEngine
from src.mock_payment.service import payment_service

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.mark.asyncio
async def test_all_12_scenarios(db_session):
    payment_service.reset()
    engine = GatewayEngine(db_session)

    # 1. Correct Refund
    auth1 = engine.create_authorization(AuthorizationCreate(
        intent_id="SCEN-1", operator_id="OP1", customer_id="C-17",
        order_id="ORD-204", operation_type=OperationType.REFUND,
        authorized_amount=1500.0, currency="INR"
    ))
    p1 = ProposalCreate(
        intent_id="SCEN-1", request_id="r1", operation=OperationType.REFUND,
        customer_id="C-17", order_id="ORD-204", amount=1500.0, currency="INR"
    )
    r1 = await engine.process_proposal(p1)
    assert r1["decision"] == DecisionType.ALLOW
    assert r1["current_state"] == IntentState.COMPLETED.value

    # 2. Wrong Amount (15,000)
    auth2 = engine.create_authorization(AuthorizationCreate(
        intent_id="SCEN-2", operator_id="OP1", customer_id="C-17",
        order_id="ORD-204", operation_type=OperationType.REFUND,
        authorized_amount=1500.0, currency="INR"
    ))
    p2 = ProposalCreate(
        intent_id="SCEN-2", request_id="r2", operation=OperationType.REFUND,
        customer_id="C-17", order_id="ORD-204", amount=15000.0, currency="INR"
    )
    r2 = await engine.process_proposal(p2)
    assert r2["decision"] == DecisionType.BLOCK
    assert r2["reason"] == DecisionReason.AMOUNT_EXCEEDS_AUTHORIZATION

    # 3. Wrong Order (ORD-240)
    auth3 = engine.create_authorization(AuthorizationCreate(
        intent_id="SCEN-3", operator_id="OP1", customer_id="C-17",
        order_id="ORD-204", operation_type=OperationType.REFUND,
        authorized_amount=1500.0, currency="INR"
    ))
    p3 = ProposalCreate(
        intent_id="SCEN-3", request_id="r3", operation=OperationType.REFUND,
        customer_id="C-17", order_id="ORD-240", amount=1500.0, currency="INR"
    )
    r3 = await engine.process_proposal(p3)
    assert r3["decision"] == DecisionType.BLOCK
    assert r3["reason"] == DecisionReason.ORDER_MISMATCH

    # 5. Timeout After Execution (Lost Response) -> Reconciliation verifies completion
    auth5 = engine.create_authorization(AuthorizationCreate(
        intent_id="SCEN-5", operator_id="OP1", customer_id="C-55",
        order_id="ORD-505", operation_type=OperationType.REFUND,
        authorized_amount=2000.0, currency="INR"
    ))
    p5 = ProposalCreate(
        intent_id="SCEN-5", request_id="r5", operation=OperationType.REFUND,
        customer_id="C-55", order_id="ORD-505", amount=2000.0, currency="INR"
    )
    r5 = await engine.process_proposal(p5, simulated_fault=FaultType.TIMEOUT_AFTER_EXECUTION)
    assert r5["reconciliation"]["final_state"] == "COMPLETED"

    # 6. Agent Restart -> Prevent second refund
    p6 = ProposalCreate(
        intent_id="SCEN-5", request_id="r6-restarted", operation=OperationType.REFUND,
        customer_id="C-55", order_id="ORD-505", amount=2000.0, currency="INR"
    )
    r6 = await engine.process_proposal(p6)
    assert r6["decision"] == DecisionType.BLOCK
    assert r6["reason"] == DecisionReason.ALREADY_COMPLETED

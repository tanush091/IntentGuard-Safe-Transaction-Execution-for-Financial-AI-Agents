import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, AuthorizationModel, EffectModel
from src.schemas.types import (
    AuthorizationCreate, ProposalCreate, OperationType,
    FaultType, IntentState, PaymentProviderRefundRequest
)
from src.gateway.engine import GatewayEngine
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
async def test_reconciliation_discovers_lost_response(db_session):
    payment_service.reset()
    engine = GatewayEngine(db_session)

    # 1. Authorize
    auth = engine.create_authorization(AuthorizationCreate(
        intent_id="INT-RECON-1",
        operator_id="OP-01",
        customer_id="C-17",
        order_id="ORD-204",
        operation_type=OperationType.REFUND,
        authorized_amount=1500.0,
        currency="INR"
    ))

    # 2. Propose with TIMEOUT_AFTER_EXECUTION
    prop = ProposalCreate(
        intent_id="INT-RECON-1",
        request_id="req-recon-1",
        operation=OperationType.REFUND,
        customer_id="C-17",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR"
    )

    result = await engine.process_proposal(prop, simulated_fault=FaultType.TIMEOUT_AFTER_EXECUTION)

    # Verify reconciliation completed it without double-charging or dropping
    assert result["reconciliation"]["resolved"] is True
    assert result["reconciliation"]["final_state"] == "COMPLETED"

    # Verify durable effect was recorded in ledger
    effects = db_session.query(EffectModel).filter(EffectModel.intent_id == "INT-RECON-1").all()
    assert len(effects) == 1
    assert effects[0].amount == 1500.0
    assert effects[0].status == "COMPLETED"

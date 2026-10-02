import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, EffectModel
from src.schemas.types import (
    AuthorizationCreate, ProposalCreate, OperationType,
    DecisionType, FaultType
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
async def test_payment_authorization_and_cancellation(db_session):
    payment_service.reset()
    engine = GatewayEngine(db_session)

    # Step 1: Authorize payment hold of ₹5,000 for order ORD-901
    auth = engine.create_authorization(AuthorizationCreate(
        intent_id="INT-AUTH-01",
        operator_id="OP-FIN",
        customer_id="C-88",
        order_id="ORD-901",
        operation_type=OperationType.PAYMENT_AUTHORIZATION,
        authorized_amount=5000.0,
        currency="INR"
    ))

    # Step 2: Propose payment authorization
    prop = ProposalCreate(
        intent_id="INT-AUTH-01",
        request_id="req-auth-1",
        operation=OperationType.PAYMENT_AUTHORIZATION,
        customer_id="C-88",
        order_id="ORD-901",
        amount=5000.0,
        currency="INR"
    )
    result = await engine.process_proposal(prop)
    assert result["decision"] == DecisionType.ALLOW
    provider_auth_id = result["provider_transaction_id"]
    assert provider_auth_id.startswith("auth_")

    # Step 3: Trigger state-aware cancellation & verification
    success = await RecoveryPolicyEngine.recover_pending_transaction(
        db_session,
        "INT-AUTH-01",
        provider_auth_id
    )
    assert success is True

    # Verify external state at provider is CANCELLED
    provider_record = payment_service.get_payment_auth(provider_auth_id)
    assert provider_record.status == "CANCELLED"

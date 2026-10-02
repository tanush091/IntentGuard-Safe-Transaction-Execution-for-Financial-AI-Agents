import pytest
from fastapi import HTTPException
from src.schemas.types import (
    PaymentProviderRefundRequest, PaymentProviderAuthRequest,
    ProviderTransactionStatus, FaultType
)
from src.mock_payment.service import payment_service

@pytest.fixture(autouse=True)
def reset_service():
    payment_service.reset()

@pytest.mark.asyncio
async def test_process_refund_success():
    req = PaymentProviderRefundRequest(
        customer_id="C-17",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR",
        idempotency_key="key-1"
    )
    resp = await payment_service.process_refund(req)
    assert resp.refund_id.startswith("ref_")
    assert resp.amount == 1500.0
    assert resp.status == ProviderTransactionStatus.COMPLETED

    # Test idempotency returns identical record
    resp_repeat = await payment_service.process_refund(req)
    assert resp_repeat.refund_id == resp.refund_id

@pytest.mark.asyncio
async def test_fault_timeout_before_execution():
    req = PaymentProviderRefundRequest(
        customer_id="C-17",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR",
        fault=FaultType.TIMEOUT_BEFORE_EXECUTION
    )
    with pytest.raises(HTTPException) as exc:
        await payment_service.process_refund(req)
    assert exc.value.status_code == 504
    # Verify no refund was recorded on provider
    assert len(payment_service.refunds) == 0

@pytest.mark.asyncio
async def test_fault_timeout_after_execution():
    req = PaymentProviderRefundRequest(
        customer_id="C-17",
        order_id="ORD-204",
        amount=1500.0,
        currency="INR",
        fault=FaultType.TIMEOUT_AFTER_EXECUTION
    )
    with pytest.raises(HTTPException) as exc:
        await payment_service.process_refund(req)
    assert exc.value.status_code == 504
    # Verify refund was actually completed on provider side!
    assert len(payment_service.refunds) == 1
    recorded = list(payment_service.refunds.values())[0]
    assert recorded["status"] == ProviderTransactionStatus.COMPLETED

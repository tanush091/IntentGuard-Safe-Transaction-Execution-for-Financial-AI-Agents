from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException
from src.schemas.types import (
    PaymentProviderRefundRequest,
    PaymentProviderRefundResponse,
    PaymentProviderAuthRequest,
    PaymentProviderAuthResponse,
    FaultConfig
)
from src.mock_payment.service import payment_service
from src.mock_payment.faults import fault_engine, FaultConfiguration

app = FastAPI(
    title="IntentGuard Mock Payment Service",
    description="Simulated Payment Service for Refunds & Authorizations with Fault Injection",
    version="1.0.0"
)

@app.post("/reset", tags=["Admin"])
def reset_service():
    payment_service.reset()
    return {"status": "reset_successful"}

@app.post("/faults", tags=["Fault Injection"])
def configure_fault(config: FaultConfig):
    if config.target_order_id:
        fault_engine.set_order_fault(
            config.target_order_id,
            FaultConfiguration(fault_type=config.fault_type, delay_seconds=config.delay_seconds)
        )
    else:
        fault_engine.set_global_fault(
            FaultConfiguration(fault_type=config.fault_type, delay_seconds=config.delay_seconds)
        )
    return {"status": "fault_configured", "config": config}

@app.post("/refunds", response_model=PaymentProviderRefundResponse, tags=["Refunds"])
async def create_refund(request: PaymentProviderRefundRequest):
    return await payment_service.process_refund(request)

@app.get("/refunds/{refund_id}", response_model=PaymentProviderRefundResponse, tags=["Refunds"])
def get_refund(refund_id: str):
    return payment_service.get_refund(refund_id)

@app.get("/refunds", response_model=List[PaymentProviderRefundResponse], tags=["Refunds"])
def list_refunds(order_id: Optional[str] = Query(None)):
    if order_id:
        return payment_service.list_refunds_by_order(order_id)
    return list(payment_service.refunds.values())

@app.post("/refunds/{refund_id}/cancel", response_model=PaymentProviderRefundResponse, tags=["Refunds"])
async def cancel_refund(refund_id: str, force_fail: bool = False):
    return await payment_service.cancel_refund(refund_id, force_fail=force_fail)

# Secondary Workflow: Payment Authorizations
@app.post("/payments/authorizations", response_model=PaymentProviderAuthResponse, tags=["Authorizations"])
async def create_payment_auth(request: PaymentProviderAuthRequest):
    return await payment_service.process_payment_auth(request)

@app.get("/payments/authorizations/{auth_id}", response_model=PaymentProviderAuthResponse, tags=["Authorizations"])
def get_payment_auth(auth_id: str):
    return payment_service.get_payment_auth(auth_id)

@app.get("/payments/authorizations", response_model=List[PaymentProviderAuthResponse], tags=["Authorizations"])
def list_payment_auths(order_id: Optional[str] = Query(None)):
    if order_id:
        return payment_service.list_payment_auths_by_order(order_id)
    return list(payment_service.payment_auths.values())

@app.post("/payments/authorizations/{auth_id}/cancel", response_model=PaymentProviderAuthResponse, tags=["Authorizations"])
async def cancel_payment_auth(auth_id: str):
    return await payment_service.cancel_payment_auth(auth_id)

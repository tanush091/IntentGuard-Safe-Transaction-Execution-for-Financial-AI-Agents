"""
Refund API Endpoints for Mock Payment Simulator.
"""

from typing import List, Optional
from fastapi import APIRouter, Header, HTTPException, status
from ..schemas import RefundCreateRequest, RefundResponse
from ..services.payment_service import payment_service

router = APIRouter(prefix="/refunds", tags=["Refunds"])


@router.post("", response_model=RefundResponse, status_code=status.HTTP_201_CREATED)
def process_refund(
    req: RefundCreateRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Process a simulated refund settlement."""
    return payment_service.process_refund(req, idempotency_key=idempotency_key)


@router.get("/{refund_id}", response_model=RefundResponse)
def get_refund(refund_id: str):
    """Retrieve refund status by provider reference ID."""
    ref = payment_service.get_refund(refund_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found")
    return ref


@router.get("", response_model=List[RefundResponse])
def list_refunds(order_id: Optional[str] = None):
    """Query refunds associated with an order ID."""
    if not order_id:
        return list(payment_service.refunds.values())
    return payment_service.list_refunds_by_order(order_id)


@router.post("/{refund_id}/cancel", response_model=RefundResponse)
def cancel_refund(refund_id: str):
    """Cancel or reverse a refund if permitted by settlement state."""
    return payment_service.cancel_refund(refund_id)

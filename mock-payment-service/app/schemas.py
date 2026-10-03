"""
Pydantic schemas for the Mock Payment Service Simulator.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class RefundCreateRequest(BaseModel):
    order_id: str = Field(..., description="Target business order identifier")
    customer_id: str = Field(..., description="Customer identifier")
    amount: float = Field(..., gt=0, description="Refund settlement amount")
    currency: str = Field(default="INR", description="ISO Currency code")
    reason: Optional[str] = Field(None, description="Optional refund justification")


class RefundResponse(BaseModel):
    id: str
    order_id: str
    customer_id: str
    amount: float
    currency: str
    status: str  # COMPLETED, PENDING, CANCELLED
    idempotency_key: Optional[str] = None
    created_at: str


class AuthorizationCreateRequest(BaseModel):
    order_id: str
    customer_id: str
    amount: float
    currency: str = "INR"


class AuthorizationResponse(BaseModel):
    id: str
    order_id: str
    customer_id: str
    amount: float
    currency: str
    status: str  # AUTHORIZED, CAPTURED, VOIDED
    created_at: str


class FaultConfigRequest(BaseModel):
    fault_type: str = Field(..., description="Fault mode name")
    target_order_id: Optional[str] = Field(None, description="Specific target order (or None for global)")
    delay_seconds: float = Field(default=0.0, description="Simulated network delay")

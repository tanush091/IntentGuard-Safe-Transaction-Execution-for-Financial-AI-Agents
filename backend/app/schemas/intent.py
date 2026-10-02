"""
Pydantic schemas for Durable Intent Records and Authorizations.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class OperationType(str, Enum):
    REFUND = "REFUND"
    PAYMENT_AUTHORIZE = "PAYMENT_AUTHORIZE"


class ApprovalStatus(str, Enum):
    APPROVED = "APPROVED"
    REVOKED = "REVOKED"
    PENDING = "PENDING"


class IntentCreate(BaseModel):
    intent_id: str = Field(..., description="Unique intent identifier (e.g. INT-001)")
    operator_id: str = Field(..., description="Authorizing human operator or system ID")
    customer_id: str = Field(..., description="Target customer identifier (e.g. C-17)")
    order_id: str = Field(..., description="Associated business order (e.g. ORD-204)")
    operation_type: OperationType = Field(default=OperationType.REFUND, description="Authorized financial operation")
    authorized_amount: float = Field(..., gt=0, description="Maximum permitted monetary amount")
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO-4217 Currency code")
    approval_status: ApprovalStatus = Field(default=ApprovalStatus.APPROVED)


class IntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    operator_id: str
    customer_id: str
    order_id: str
    operation_type: str
    authorized_amount: float
    currency: str
    approval_status: str
    current_state: str
    created_at: datetime
    updated_at: datetime

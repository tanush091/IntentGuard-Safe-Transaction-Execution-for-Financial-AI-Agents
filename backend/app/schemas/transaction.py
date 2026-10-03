"""
Pydantic schemas for Attempts, Effects, and Audit Trail Events.
"""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    intent_id: str
    attempt_number: int
    provider_reference: Optional[str] = None
    status: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class EffectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    intent_id: str
    attempt_id: Optional[str] = None
    provider_reference: str
    effect_type: str
    order_id: str
    amount: float
    currency: str
    status: str
    observed_at: datetime


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    intent_id: str
    attempt_id: Optional[str] = None
    event_type: str
    event_data: Optional[Dict[str, Any]] = None
    decision: str
    reason: str
    created_at: datetime

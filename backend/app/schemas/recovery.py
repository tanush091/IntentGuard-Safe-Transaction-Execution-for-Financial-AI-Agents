"""
Pydantic schemas for Review Cases and Recovery Actions.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ReviewCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    intent_id: str
    reason: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None


class ReviewCaseResolveRequest(BaseModel):
    resolution_notes: str = Field(..., min_length=5, description="Operator explanation for manual resolution")
    action: str = Field(default="RESOLVE", description="Action taken: RESOLVE or DISMISS")

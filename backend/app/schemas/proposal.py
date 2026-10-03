"""
Pydantic schemas for AI Agent Proposals and Gateway Decisions.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from backend.app.schemas.intent import OperationType


class AgentProposal(BaseModel):
    intent_id: str = Field(..., description="Target business intent identifier")
    operation: OperationType = Field(..., description="Proposed financial operation")
    customer_id: str = Field(..., description="Target customer identifier")
    order_id: str = Field(..., description="Target order identifier")
    amount: float = Field(..., gt=0, description="Proposed settlement amount")
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO Currency code")
    request_id: Optional[str] = Field(None, description="Optional unique proposal request identifier")


class GatewayDecisionType(str):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


class GatewayEvaluationResult(BaseModel):
    intent_id: str
    decision: str  # APPROVED, BLOCKED
    current_state: str
    reason: str
    checks_passed: List[str] = []
    checks_failed: List[str] = []
    attempt_number: Optional[int] = None
    provider_reference: Optional[str] = None

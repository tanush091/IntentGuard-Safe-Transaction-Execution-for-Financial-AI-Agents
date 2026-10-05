"""HTTP request/response models. Amounts cross the API as decimal strings in major units."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from intentguard.domain import Operation, ReviewResolution


class OperatorIn(BaseModel):
    id: str
    name: str
    permitted_operations: list[Operation]
    limit: Decimal = Field(description="Per-intent limit in major units of currency")
    currency: str = "INR"
    active: bool = True


class OperatorPatch(BaseModel):
    active: bool


class OrderIn(BaseModel):
    id: str
    customer_id: str
    currency: str = "INR"
    amount: Decimal


class IntentIn(BaseModel):
    operator_id: str
    customer_id: str
    order_id: str
    operation: Operation = Operation.REFUND
    amount: Decimal
    currency: str = "INR"
    ticket: str | None = None


class ProposalIn(BaseModel):
    request_id: str | None = None
    agent_id: str = "external-agent"
    operation: Operation
    customer_id: str
    order_id: str
    amount: Decimal
    currency: str = "INR"
    rationale: str = ""


class AgentRunIn(BaseModel):
    ticket: str | None = Field(default=None, description="Defaults to the ticket stored on the intent")
    agent_id: str = "support-agent"


class RevokeIn(BaseModel):
    actor: str


class ResolveIn(BaseModel):
    reviewer_id: str
    resolution: ReviewResolution
    notes: str = ""


class SubmitOut(BaseModel):
    decision: str
    intent_id: str
    intent_state: str
    findings: list[dict[str, str]]
    proposal_id: int | None
    attempt_id: str | None
    provider_ref: str | None


class AgentRunOut(BaseModel):
    extractor: str
    extracted: dict[str, Any] | None
    extraction_error: str | None
    result: SubmitOut | None

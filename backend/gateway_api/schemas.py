"""
Request models (docs/API.md). Write endpoints reject unknown fields (docs/SECURITY.md section 6).
Amounts cross the API as decimal strings in major units with an explicit ISO-4217 currency.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intentguard.domain import Operation, ReviewResolution

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"
CURRENCY_PATTERN = r"^[A-Za-z]{3}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------- auth


class LoginIn(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class RefreshIn(Strict):
    refresh_token: str | None = Field(default=None, max_length=256)


# ------------------------------------------------------------ authorizations


class AuthorizationIn(Strict):
    customer_id: str = Field(pattern=ID_PATTERN)
    order_id: str = Field(pattern=ID_PATTERN)
    operation: Operation = Operation.REFUND
    authorized_amount: Decimal = Field(gt=0, max_digits=18)
    currency: str = Field(default="INR", pattern=CURRENCY_PATTERN)
    ticket_text: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposalIn(Strict):
    request_id: str | None = Field(default=None, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    operation: Operation
    customer_id: str = Field(pattern=ID_PATTERN)
    order_id: str = Field(pattern=ID_PATTERN)
    amount: Decimal = Field(gt=0, max_digits=18)
    currency: str = Field(default="INR", pattern=CURRENCY_PATTERN)
    rationale: str = Field(default="", max_length=2000)


class AgentRunIn(Strict):
    ticket_text: str | None = Field(default=None, max_length=5000)


class CancelIn(Strict):
    note: str = Field(default="", max_length=2000)


class ResolveIn(Strict):
    resolution: ReviewResolution
    note: str = Field(default="", max_length=2000)


class MismatchResolveIn(Strict):
    note: str = Field(default="", max_length=2000)


# ----------------------------------------------------------------- admin


class UserIn(Strict):
    id: str | None = Field(default=None, pattern=ID_PATTERN)
    email: str | None = Field(default=None, max_length=254)
    name: str = Field(max_length=128)
    role: str = Field(pattern=r"^(operator|reviewer|admin|agent)$")
    password: str | None = Field(default=None, max_length=1024)
    permitted_operations: list[Operation] = Field(default_factory=list)
    limit: Decimal = Field(default=Decimal(0), ge=0, max_digits=18)


class UserPatch(Strict):
    name: str | None = Field(default=None, max_length=128)
    role: str | None = Field(default=None, pattern=r"^(operator|reviewer|admin|agent)$")
    active: bool | None = None
    password: str | None = Field(default=None, max_length=1024)
    permitted_operations: list[Operation] | None = None
    limit: Decimal | None = Field(default=None, ge=0, max_digits=18)


class ServiceTokenIn(Strict):
    principal_id: str = Field(pattern=ID_PATTERN)
    intent_ids: list[str] = Field(default_factory=list, max_length=100)
    customer_ids: list[str] = Field(default_factory=list, max_length=100)
    ttl_s: int = Field(default=300, ge=30)


class PoliciesIn(Strict):
    kill_switch: bool | None = None
    max_amount: Decimal | None = Field(default=None, ge=0, max_digits=18)
    clear_max_amount: bool = False
    separation_of_duties: bool | None = None
    attempt_budget: int | None = Field(default=None, ge=1, le=20)
    absence_window_s: float | None = Field(default=None, ge=0, le=86400)
    unknown_review_after_s: float | None = Field(default=None, ge=1, le=7 * 86400)


class ProviderIn(Strict):
    base_url: str | None = Field(default=None, max_length=256)
    timeout_s: float | None = Field(default=None, gt=0, le=120)
    webhook_secret: str | None = Field(default=None, min_length=16, max_length=256)


class OrderIn(Strict):
    id: str = Field(pattern=ID_PATTERN)
    customer_id: str = Field(pattern=ID_PATTERN)
    currency: str = Field(default="INR", pattern=CURRENCY_PATTERN)
    amount: Decimal = Field(gt=0, max_digits=18)


class FaultIn(Strict):
    kind: str = Field(max_length=64)
    order_id: str | None = Field(default=None, pattern=ID_PATTERN)
    times: int = Field(default=1, ge=-1, le=100)
    params: dict[str, Any] = Field(default_factory=dict)

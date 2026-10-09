"""
The payment-provider port. The gateway only talks to providers through this
interface, so the simulator can later be replaced by a real provider sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from intentguard.domain import Operation, ProviderStatus


@dataclass(frozen=True)
class ProviderRecord:
    provider_ref: str
    operation: Operation
    order_id: str
    customer_id: str
    amount_minor: int
    currency: str
    status: ProviderStatus
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Base class. Subclasses tell the gateway what is known about the outcome."""


class ProviderTimeout(ProviderError):
    """No response. The operation may or may not have executed."""


class ProviderUnavailable(ProviderError):
    """5xx. Treated as an unknown outcome for creates, as a failed lookup for reads."""


class ProviderRejected(ProviderError):
    """Definitive rejection: the provider guarantees nothing executed."""

    def __init__(self, message: str, code: str = "rejected"):
        super().__init__(message)
        self.code = code


class ProviderNotFound(ProviderRejected):
    pass


class ProviderConflict(ProviderRejected):
    """The operation is not allowed in the transaction's current state."""


class PaymentProvider(Protocol):
    def create(
        self,
        operation: Operation,
        *,
        order_id: str,
        customer_id: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str | None,
        metadata: dict[str, Any],
    ) -> ProviderRecord: ...

    def get(self, operation: Operation, provider_ref: str) -> ProviderRecord: ...

    def list_by_order(self, operation: Operation, order_id: str) -> list[ProviderRecord]: ...

    def cancel(self, operation: Operation, provider_ref: str) -> ProviderRecord: ...

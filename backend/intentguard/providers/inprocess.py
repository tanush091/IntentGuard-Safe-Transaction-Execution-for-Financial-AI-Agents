"""Adapter that calls a paysim.PaymentSimulator in the same process (benchmarks, tests)."""

from __future__ import annotations

from typing import Any

from paysim import (
    PaymentSimulator,
    SimConflict,
    SimNotFound,
    SimRejected,
    SimTimeout,
    SimUnavailable,
    Transaction,
    TxKind,
)

from intentguard.domain import Operation, ProviderStatus
from intentguard.providers.base import (
    ProviderConflict,
    ProviderNotFound,
    ProviderRecord,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
)

_KIND = {Operation.REFUND: TxKind.REFUND, Operation.PAYMENT_AUTHORIZATION: TxKind.AUTHORIZATION}
_OP = {v: k for k, v in _KIND.items()}


def to_record(tx: Transaction) -> ProviderRecord:
    return ProviderRecord(
        provider_ref=tx.id,
        operation=_OP[tx.kind],
        order_id=tx.order_id,
        customer_id=tx.customer_id,
        amount_minor=tx.amount_minor,
        currency=tx.currency,
        status=ProviderStatus(tx.status.value),
        idempotency_key=tx.idempotency_key,
        metadata=dict(tx.metadata),
    )


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, SimTimeout):
        return ProviderTimeout(str(exc))
    if isinstance(exc, SimUnavailable):
        return ProviderUnavailable(str(exc))
    if isinstance(exc, SimNotFound):
        return ProviderNotFound(str(exc), exc.code)
    if isinstance(exc, SimConflict):
        return ProviderConflict(str(exc), exc.code)
    if isinstance(exc, SimRejected):
        return ProviderRejected(str(exc), exc.code)
    return exc


class InProcessProvider:
    def __init__(self, simulator: PaymentSimulator):
        self.sim = simulator

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
    ) -> ProviderRecord:
        try:
            tx = self.sim.create(
                _KIND[operation],
                order_id=order_id,
                customer_id=customer_id,
                amount_minor=amount_minor,
                currency=currency,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001 - translated and re-raised
            raise _translate(exc) from exc
        return to_record(tx)

    def get(self, operation: Operation, provider_ref: str) -> ProviderRecord:
        try:
            return to_record(self.sim.get(provider_ref))
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

    def list_by_order(self, operation: Operation, order_id: str) -> list[ProviderRecord]:
        try:
            return [to_record(t) for t in self.sim.list_by_order(order_id, _KIND[operation])]
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

    def cancel(self, operation: Operation, provider_ref: str) -> ProviderRecord:
        try:
            return to_record(self.sim.cancel(provider_ref))
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc

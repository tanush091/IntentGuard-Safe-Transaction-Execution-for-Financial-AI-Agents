"""
paysim: a deterministic payment-provider simulator for IntentGuard research.

It models the provider behaviours that make agent-initiated payments hard to
get right: pending settlement, state-dependent cancellation, idempotency keys
with parameter fingerprints, eventually-consistent search, and injectable
network/provider faults. It never touches real money.
"""

from paysim.simulator import (
    Fault,
    FaultKind,
    Order,
    PaymentSimulator,
    SimConflict,
    SimError,
    SimNotFound,
    SimRejected,
    SimTimeout,
    SimUnavailable,
    Transaction,
    TxKind,
    TxStatus,
)

__all__ = [
    "Fault",
    "FaultKind",
    "Order",
    "PaymentSimulator",
    "SimConflict",
    "SimError",
    "SimNotFound",
    "SimRejected",
    "SimTimeout",
    "SimUnavailable",
    "Transaction",
    "TxKind",
    "TxStatus",
]

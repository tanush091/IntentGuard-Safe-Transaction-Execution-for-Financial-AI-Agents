"""
Payment-provider simulator.

Semantics (modelled on publicly documented provider behaviour):

* Refunds are created PENDING and settle to COMPLETED after ``settle_delay_s``
  (0 means they complete immediately). A refund can be cancelled only while it
  is PENDING; a COMPLETED refund cannot be reversed by the API.
* Authorizations (holds) are created PENDING and become COMPLETED ("authorized")
  after ``settle_delay_s``. A hold can be voided while PENDING or COMPLETED.
* Idempotency: a create request carrying an ``idempotency_key`` that was seen
  before returns the original transaction if the request parameters match, and
  is rejected with ``idempotency_key_reuse`` if they differ. Keys expire after
  ``idempotency_ttl_s``.
* Lookup by id is strongly consistent. Listing by order is eventually
  consistent: a transaction appears in listings only after ``visible_at``.
* Statuses are derived lazily from the injected clock, so experiments driven by
  a simulated clock are fully deterministic.

Faults are queued per order (or globally) and consumed when they fire.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Callable


class TxKind(StrEnum):
    REFUND = "REFUND"
    AUTHORIZATION = "AUTHORIZATION"


class TxStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


LIVE_STATUSES = frozenset({TxStatus.PENDING, TxStatus.COMPLETED})


class FaultKind(StrEnum):
    # Network-level faults on create (applied before/after idempotency replay).
    OUTAGE = "OUTAGE"  # 503, nothing executed
    TIMEOUT_BEFORE_EXECUTION = "TIMEOUT_BEFORE_EXECUTION"  # caller times out, nothing executed
    LOST_RESPONSE = "LOST_RESPONSE"  # executed, caller never sees the response
    # Execution-level faults (only on a fresh execution).
    SLOW_SETTLEMENT = "SLOW_SETTLEMENT"  # params: settle_delay_s
    DELAYED_VISIBILITY = "DELAYED_VISIBILITY"  # params: lag_s
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"  # params: factor (settled = requested * factor)
    # Faults on other operations.
    CANCEL_REJECTED = "CANCEL_REJECTED"  # cancel refused even when allowed
    LOOKUP_OUTAGE = "LOOKUP_OUTAGE"  # get/list fail with 503


CREATE_FAULTS = frozenset(
    {
        FaultKind.OUTAGE,
        FaultKind.TIMEOUT_BEFORE_EXECUTION,
        FaultKind.LOST_RESPONSE,
        FaultKind.SLOW_SETTLEMENT,
        FaultKind.DELAYED_VISIBILITY,
        FaultKind.AMOUNT_MISMATCH,
    }
)


class SimError(Exception):
    """Base class for simulator errors."""

    code = "error"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class SimTimeout(SimError):
    """The caller did not receive a response. Execution may or may not have happened."""

    code = "timeout"


class SimUnavailable(SimError):
    """Provider returned 503."""

    code = "unavailable"


class SimRejected(SimError):
    """Definitive 4xx rejection; nothing was executed."""

    code = "rejected"


class SimNotFound(SimRejected):
    code = "not_found"


class SimConflict(SimRejected):
    """Operation not permitted in the current state (e.g. cancel a completed refund)."""

    code = "conflict"


@dataclass
class Order:
    order_id: str
    customer_id: str
    currency: str
    amount_minor: int


@dataclass
class Transaction:
    id: str
    kind: TxKind
    order_id: str
    customer_id: str
    amount_minor: int
    requested_minor: int
    currency: str
    status: TxStatus
    idempotency_key: str | None
    fingerprint: str
    metadata: dict[str, Any]
    created_at: float
    settles_at: float
    visible_at: float
    cancelled_at: float | None = None

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("fingerprint")
        d.pop("requested_minor")
        return d


@dataclass
class Fault:
    kind: FaultKind
    order_id: str | None = None  # None = applies to any order
    times: int = 1  # -1 = never consumed
    params: dict[str, Any] = field(default_factory=dict)


def _fingerprint(kind: TxKind, order_id: str, customer_id: str, amount_minor: int, currency: str) -> str:
    raw = f"{kind}|{order_id}|{customer_id}|{amount_minor}|{currency}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class PaymentSimulator:
    def __init__(
        self,
        now: Callable[[], float] = time.time,
        *,
        default_settle_delay_s: float = 0.0,
        idempotency_ttl_s: float = 24 * 3600.0,
        real_latency_s: float = 0.0,
        state_path: str | None = None,
        id_seed: int | None = None,
    ):
        self._now = now
        self.default_settle_delay_s = default_settle_delay_s
        self.idempotency_ttl_s = idempotency_ttl_s
        self.real_latency_s = real_latency_s
        self._state_path = state_path
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._txs: dict[str, Transaction] = {}
        self._idem: dict[str, tuple[str, float]] = {}  # key -> (tx_id, created_at)
        self._faults: list[Fault] = []
        self._counter = 0
        self._id_prefix = f"{id_seed:04x}" if id_seed is not None else uuid.uuid4().hex[:4]
        self.stats = {"create_calls": 0, "executions": 0, "lookups": 0, "cancels": 0}
        if state_path and os.path.exists(state_path):
            self._load()

    # ------------------------------------------------------------------ setup

    def add_order(self, order: Order) -> None:
        with self._lock:
            self._orders[order.order_id] = order
            self._save()

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def inject(self, fault: Fault) -> None:
        with self._lock:
            self._faults.append(fault)
            self._save()

    def clear_faults(self) -> None:
        with self._lock:
            self._faults.clear()
            self._save()

    def faults(self) -> list[Fault]:
        with self._lock:
            return list(self._faults)

    def reset(self) -> None:
        with self._lock:
            self._orders.clear()
            self._txs.clear()
            self._idem.clear()
            self._faults.clear()
            self._save()

    # -------------------------------------------------------------- operations

    def create(
        self,
        kind: TxKind,
        *,
        order_id: str,
        customer_id: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Transaction:
        if self.real_latency_s:
            time.sleep(self.real_latency_s)
        with self._lock:
            self.stats["create_calls"] += 1
            if self._take_fault(FaultKind.OUTAGE, order_id):
                raise SimUnavailable("provider unavailable (simulated 503)")
            if self._take_fault(FaultKind.TIMEOUT_BEFORE_EXECUTION, order_id):
                raise SimTimeout("request timed out before reaching the provider")

            currency = currency.upper()
            fp = _fingerprint(kind, order_id, customer_id, amount_minor, currency)
            now = self._now()

            replay = self._replay(idempotency_key, fp, now)
            if replay is not None:
                tx = replay
            else:
                tx = self._execute(kind, order_id, customer_id, amount_minor, currency, idempotency_key, fp, metadata or {}, now)

            if self._take_fault(FaultKind.LOST_RESPONSE, order_id):
                raise SimTimeout("response lost after execution")
            return self._refresh(tx)

    def get(self, tx_id: str) -> Transaction:
        with self._lock:
            self.stats["lookups"] += 1
            tx = self._txs.get(tx_id)
            if tx is not None and self._take_fault(FaultKind.LOOKUP_OUTAGE, tx.order_id):
                raise SimUnavailable("lookup unavailable (simulated 503)")
            if tx is None:
                raise SimNotFound(f"transaction {tx_id} not found")
            return self._refresh(tx)

    def list_by_order(self, order_id: str, kind: TxKind | None = None) -> list[Transaction]:
        with self._lock:
            self.stats["lookups"] += 1
            if self._take_fault(FaultKind.LOOKUP_OUTAGE, order_id):
                raise SimUnavailable("lookup unavailable (simulated 503)")
            now = self._now()
            out = [
                self._refresh(tx)
                for tx in self._txs.values()
                if tx.order_id == order_id and (kind is None or tx.kind == kind) and now >= tx.visible_at
            ]
            return sorted(out, key=lambda t: t.created_at)

    def cancel(self, tx_id: str) -> Transaction:
        with self._lock:
            self.stats["cancels"] += 1
            tx = self._txs.get(tx_id)
            if tx is None:
                raise SimNotFound(f"transaction {tx_id} not found")
            tx = self._refresh(tx)
            if tx.status == TxStatus.CANCELLED:
                return tx  # cancel is idempotent
            if self._take_fault(FaultKind.CANCEL_REJECTED, tx.order_id):
                raise SimConflict("cancellation rejected by provider", code="cancel_rejected")
            if not self.is_cancellable(tx):
                raise SimConflict(
                    f"{tx.kind} in status {tx.status} cannot be cancelled", code="not_cancellable"
                )
            tx.status = TxStatus.CANCELLED
            tx.cancelled_at = self._now()
            self._save()
            return tx

    @staticmethod
    def is_cancellable(tx: Transaction) -> bool:
        if tx.kind == TxKind.REFUND:
            return tx.status == TxStatus.PENDING
        return tx.status in LIVE_STATUSES

    # ------------------------------------------------------------ ground truth

    def all_transactions(self) -> list[Transaction]:
        """Every transaction regardless of visibility. For evaluation only."""
        with self._lock:
            return [self._refresh(tx) for tx in self._txs.values()]

    # --------------------------------------------------------------- internals

    def _replay(self, key: str | None, fp: str, now: float) -> Transaction | None:
        if not key:
            return None
        entry = self._idem.get(key)
        if entry is None:
            return None
        tx_id, created = entry
        if now - created > self.idempotency_ttl_s:
            del self._idem[key]
            return None
        tx = self._txs[tx_id]
        if tx.fingerprint != fp:
            raise SimRejected(
                "idempotency key reused with different parameters", code="idempotency_key_reuse"
            )
        return tx

    def _execute(
        self,
        kind: TxKind,
        order_id: str,
        customer_id: str,
        amount_minor: int,
        currency: str,
        key: str | None,
        fp: str,
        metadata: dict[str, Any],
        now: float,
    ) -> Transaction:
        order = self._orders.get(order_id)
        if order is None:
            raise SimNotFound(f"order {order_id} not found", code="order_not_found")
        if order.customer_id != customer_id:
            raise SimRejected("customer does not own this order", code="customer_mismatch")
        if order.currency != currency:
            raise SimRejected("currency does not match the order", code="currency_mismatch")
        if amount_minor <= 0:
            raise SimRejected("amount must be positive", code="invalid_amount")
        used = sum(
            t.requested_minor
            for t in self._txs.values()
            if t.order_id == order_id and t.kind == kind and self._refresh(t).status in LIVE_STATUSES
        )
        if used + amount_minor > order.amount_minor:
            raise SimRejected("amount exceeds remaining balance for this order", code="insufficient_balance")

        settle_delay = self.default_settle_delay_s
        lag = 0.0
        settled = amount_minor
        if (f := self._take_fault(FaultKind.SLOW_SETTLEMENT, order_id)) is not None:
            settle_delay = float(f.params.get("settle_delay_s", 60.0))
        if (f := self._take_fault(FaultKind.DELAYED_VISIBILITY, order_id)) is not None:
            lag = float(f.params.get("lag_s", 20.0))
        if (f := self._take_fault(FaultKind.AMOUNT_MISMATCH, order_id)) is not None:
            settled = int(round(amount_minor * float(f.params.get("factor", 10.0))))

        self._counter += 1
        prefix = "rf" if kind == TxKind.REFUND else "au"
        tx = Transaction(
            id=f"{prefix}_{self._id_prefix}{self._counter:06d}",
            kind=kind,
            order_id=order_id,
            customer_id=customer_id,
            amount_minor=settled,
            requested_minor=amount_minor,
            currency=currency,
            status=TxStatus.PENDING,
            idempotency_key=key,
            fingerprint=fp,
            metadata=dict(metadata),
            created_at=now,
            settles_at=now + settle_delay,
            visible_at=now + lag,
        )
        self._txs[tx.id] = tx
        if key:
            self._idem[key] = (tx.id, now)
        self.stats["executions"] += 1
        self._save()
        return tx

    def _refresh(self, tx: Transaction) -> Transaction:
        if tx.status == TxStatus.PENDING and self._now() >= tx.settles_at:
            tx.status = TxStatus.COMPLETED
        return tx

    def _take_fault(self, kind: FaultKind, order_id: str | None) -> Fault | None:
        for i, f in enumerate(self._faults):
            if f.kind == kind and (f.order_id is None or f.order_id == order_id):
                if f.times > 0:
                    f.times -= 1
                    if f.times == 0:
                        del self._faults[i]
                return f
        return None

    # ------------------------------------------------------------- persistence

    def _save(self) -> None:
        if not self._state_path:
            return
        state = {
            "orders": [asdict(o) for o in self._orders.values()],
            "txs": [asdict(t) for t in self._txs.values()],
            "idem": self._idem,
            "faults": [asdict(f) for f in self._faults],
            "counter": self._counter,
            "id_prefix": self._id_prefix,
        }
        tmp = self._state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, self._state_path)

    def _load(self) -> None:
        with open(self._state_path, encoding="utf-8") as fh:  # type: ignore[arg-type]
            state = json.load(fh)
        self._orders = {o["order_id"]: Order(**o) for o in state["orders"]}
        self._txs = {}
        for t in state["txs"]:
            t["kind"] = TxKind(t["kind"])
            t["status"] = TxStatus(t["status"])
            self._txs[t["id"]] = Transaction(**t)
        self._idem = {k: (v[0], v[1]) for k, v in state["idem"].items()}
        self._faults = [Fault(kind=FaultKind(f["kind"]), order_id=f["order_id"], times=f["times"], params=f["params"]) for f in state["faults"]]
        self._counter = state["counter"]
        self._id_prefix = state["id_prefix"]

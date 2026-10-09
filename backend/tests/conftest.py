from __future__ import annotations

import itertools
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from intentguard import IntentGuard, Operation, Proposal, ProtocolConfig
from intentguard.clock import SimulatedClock
from intentguard.db import init_schema, make_engine, make_session_factory
from intentguard.engine import Hooks
from intentguard.providers.inprocess import InProcessProvider
from paysim import Fault, FaultKind, Order, PaymentSimulator, TxStatus
from tests.api_support import api, api_inprocess  # noqa: F401 - HTTP fixtures

_ids = itertools.count()

# Set TEST_DATABASE_URL (PostgreSQL) to run every test against that database instead of SQLite; CI does
# this in its PostgreSQL job. The database is wiped before each test, so its name must contain "test".
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def fresh_database_url(tmp_path: Path, *, file_db: bool = True) -> str:
    """A fresh database for one test: TEST_DATABASE_URL (reset), else a SQLite file or memory database."""
    if not TEST_DATABASE_URL:
        return f"sqlite:///{(tmp_path / 'ig.db').as_posix()}" if file_db else "sqlite://"
    if "test" not in (make_url(TEST_DATABASE_URL).database or ""):
        raise RuntimeError("TEST_DATABASE_URL must name a dedicated test database (its name must contain 'test')")
    engine = make_engine(TEST_DATABASE_URL)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return TEST_DATABASE_URL


@dataclass
class World:
    """A gateway, a simulator and a simulated clock sharing one database."""

    clock: SimulatedClock
    sim: PaymentSimulator
    guard: IntentGuard
    sf: object
    config: ProtocolConfig
    db_url: str
    hooks: Hooks = field(default_factory=Hooks)

    def order(self, order_id: str = "ORD-204", customer: str = "C-17", amount: int = 5000_00, currency: str = "INR") -> str:
        self.guard.upsert_order(order_id, customer, currency, amount)
        self.sim.add_order(Order(order_id, customer, currency, amount))
        return order_id

    def intent(self, amount: int = 1500_00, order_id: str = "ORD-204", customer: str = "C-17",
               operation: Operation = Operation.REFUND, operator: str = "op-1") -> str:
        return self.guard.authorize(operator_id=operator, customer_id=customer, order_id=order_id,
                                    operation=operation, amount_minor=amount, currency="INR")

    def proposal(self, intent_id: str, **kw: object) -> Proposal:
        base = dict(intent_id=intent_id, request_id=f"req-{next(_ids)}", agent_id="agent", operation=Operation.REFUND,
                    customer_id="C-17", order_id="ORD-204", amount_minor=1500_00, currency="INR")
        base.update(kw)
        return Proposal(**base)  # type: ignore[arg-type]

    def fault(self, kind: FaultKind, order_id: str = "ORD-204", times: int = 1, **params: object) -> None:
        self.sim.inject(Fault(kind, order_id, times, dict(params)))

    def settle(self, seconds: float = 900.0) -> None:
        """Advance simulated time, running the worker whenever something is due."""
        end = self.clock.now() + seconds
        for _ in range(500):
            due = self.guard.next_due()
            if due is None or due > end:
                break
            self.clock.advance_to(max(due, self.clock.now() + 1e-3))
            self.guard.tick()
        self.clock.advance_to(end)
        self.guard.tick()

    def live(self, order_id: str = "ORD-204") -> list:
        return [t for t in self.sim.all_transactions()
                if t.order_id == order_id and t.status in (TxStatus.PENDING, TxStatus.COMPLETED)]

    def restart(self) -> IntentGuard:
        self.guard = IntentGuard(self.sf, self.guard.provider, self.clock, self.config, self.hooks)  # type: ignore[arg-type]
        self.guard.startup_recovery()
        return self.guard


def make_world(tmp_path: Path, config: ProtocolConfig | None = None, *, file_db: bool = False,
               hooks: Hooks | None = None) -> World:
    config = config or ProtocolConfig()
    clock = SimulatedClock()
    sim = PaymentSimulator(clock.now, id_seed=1)
    tmp_path.mkdir(parents=True, exist_ok=True)
    url = fresh_database_url(tmp_path, file_db=file_db)
    engine = make_engine(url)
    init_schema(engine)
    sf = make_session_factory(engine)
    hooks = hooks or Hooks()
    guard = IntentGuard(sf, InProcessProvider(sim), clock, config, hooks)
    guard.upsert_operator("op-1", "Asha", ["REFUND", "PAYMENT_AUTHORIZATION"], 100_000_00)
    w = World(clock, sim, guard, sf, config, url, hooks)
    w.order()
    return w


@pytest.fixture
def world(tmp_path: Path) -> World:
    return make_world(tmp_path)

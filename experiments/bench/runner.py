"""
Runs scenarios against an arm on a simulated clock.

For each scenario: build the world, inject faults, run the agent session(s)
(threads for concurrency scenarios), let the arm's background work run until the
settlement horizon by jumping the clock to its next due time, then score.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from paysim import Fault, FaultKind, Order, PaymentSimulator

from intentguard.clock import SimulatedClock
from intentguard.engine import SimulatedCrash
from intentguard.providers.inprocess import InProcessProvider

from bench.agent import ScriptedAgent, new_request_id
from bench.arms import Arm, ArmContext, IntentGuardArm, Resp, build_arm
from bench.scenarios import IntentSpec, Scenario, generate
from bench.scoring import ScenarioResult, score

HORIZON_S = 900.0  # simulated seconds each scenario is allowed to settle
AGENT_MAX_RETRIES = 2  # retries of the same request after a transient error
AGENT_MAX_PROPOSALS = 3  # proposals per agent session (re-proposals after rejection)
AGENT_BACKOFF_S = 2.0
CONCURRENT_LATENCY_S = 0.003  # real provider latency so concurrent sessions overlap


class _Session:
    """One agent working one intent. Shared bookkeeping is lock-protected."""

    def __init__(self, arm: Arm, sc: Scenario, it: IntentSpec, clock: SimulatedClock, agent_id: str,
                 stats: dict[str, Any], lock: threading.Lock):
        self.arm, self.sc, self.it, self.clock = arm, sc, it, clock
        self.agent = ScriptedAgent(it, agent_id, sc.restart_error)
        self.stats, self.lock = stats, lock

    def _submit(self, p: Any) -> Resp:
        t0 = time.perf_counter()
        try:
            return self.arm.submit(self.it, p)
        finally:
            with self.lock:
                self.stats["latencies"].append((time.perf_counter() - t0) * 1000)

    def run(self) -> None:
        prefix = f"{self.sc.id}-{self.it.key}-{self.agent.agent_id}"
        rid = new_request_id(prefix)
        p = self.agent.propose(rid)
        retries = 0
        restarted = False
        while self.agent.proposals <= AGENT_MAX_PROPOSALS:
            try:
                resp = self._submit(p)
            except SimulatedCrash:
                if restarted:
                    return
                restarted = True
                with self.lock:
                    self.arm.restart()
                rid = new_request_id(prefix)
                p = self.agent.propose(rid, restarted=True)
                retries = 0
                continue
            if resp == Resp.REJECTED and self.agent.is_correct(p):
                with self.lock:
                    self.stats["rejected_correct"][self.it.key] = self.stats["rejected_correct"].get(self.it.key, 0) + 1
            if resp in (Resp.DONE, Resp.DUPLICATE, Resp.ACCEPTED):
                return
            if resp == Resp.ERROR:
                if retries >= AGENT_MAX_RETRIES:
                    return
                retries += 1
                self.clock.advance(AGENT_BACKOFF_S)
                continue  # same request, same proposal
            if self.agent.proposals >= AGENT_MAX_PROPOSALS:
                return
            rid = new_request_id(prefix)  # REJECTED: re-read the ticket and propose again
            p = self.agent.propose(rid)
            retries = 0


def run_scenario(arm: Arm, sc: Scenario, sim: PaymentSimulator, clock: SimulatedClock, seed: int) -> ScenarioResult:
    for o in sc.orders:
        sim.add_order(Order(o.order_id, o.customer_id, o.currency, o.amount_minor))
        arm.add_order(o)
    for op in sc.operators:
        arm.add_operator(op)
    for it in sc.intents:
        arm.authorize(it)
    if sc.revoke_operator:
        for op in sc.operators:
            arm.revoke_operator(op.operator_id)
    for f in sc.faults:
        sim.inject(Fault(FaultKind(f.kind), f.order_id, f.times, dict(f.params)))
    arm.crash.arm(sc.crash_point)
    sim.real_latency_s = CONCURRENT_LATENCY_S if sc.concurrency > 1 else 0.0

    stats: dict[str, Any] = {"latencies": [], "rejected_correct": {}}
    lock = threading.Lock()
    start = clock.now()
    for it in sc.intents:
        sessions = [_Session(arm, sc, it, clock, f"agent{k}", stats, lock) for k in range(sc.concurrency)]
        if len(sessions) == 1:
            sessions[0].run()
        else:
            barrier = threading.Barrier(len(sessions))
            errors: list[BaseException] = []

            def go(s: _Session) -> None:
                barrier.wait()
                try:
                    s.run()
                except BaseException as exc:  # noqa: BLE001 - re-raised in the main thread
                    errors.append(exc)

            threads = [threading.Thread(target=go, args=(s,)) for s in sessions]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            if errors:
                raise RuntimeError(f"agent thread failed in {sc.id}") from errors[0]

    horizon = start + HORIZON_S
    for _ in range(1000):
        due = arm.next_due()
        if due is None or due > horizon:
            break
        clock.advance_to(max(due, clock.now() + 1e-3))
        arm.tick()
    clock.advance_to(horizon)
    arm.tick()

    arm.crash.arm(None)
    sim.clear_faults()
    sim.real_latency_s = 0.0
    result = score(sc, arm, sim, seed=seed, rejected_correct=stats["rejected_correct"],
                   latencies_ms=stats["latencies"])
    arm.forget_scenario()
    clock.advance(60.0)  # gap between scenarios
    return result


def run_job(arm_name: str, seed: int, n_scenarios: int,
            reviewer_factory: Callable[[], Callable[[str], Any]] | None = None) -> list[dict[str, Any]]:
    """One (arm, seed) cell of the experiment. Runs in a worker process."""
    clock = SimulatedClock()
    sim = PaymentSimulator(clock.now, id_seed=seed)
    # Shared-cache in-memory SQLite: real multi-connection transactions, no disk I/O.
    db_url = f"sqlite:///file:ig_{arm_name}_{seed}_{os.getpid()}?mode=memory&cache=shared&uri=true"
    ctx = ArmContext(provider=InProcessProvider(sim), clock=clock, db_url=db_url)
    arm = build_arm(arm_name, ctx, reviewer=reviewer_factory() if reviewer_factory else None)
    results = []
    try:
        for sc in generate(seed, n_scenarios):
            results.append(run_scenario(arm, sc, sim, clock, seed).as_dict())
    finally:
        if isinstance(arm, IntentGuardArm):
            arm.close()
    return results

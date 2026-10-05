from __future__ import annotations

import threading

import pytest

from intentguard import Decision, IntentState
from intentguard.engine import Hooks, SimulatedCrash
from paysim import FaultKind

from tests_intentguard.conftest import make_world


@pytest.mark.parametrize("agents", [2, 4, 8])
def test_concurrent_agents_produce_exactly_one_effect(tmp_path, agents):
    w = make_world(tmp_path, file_db=True)
    w.sim.real_latency_s = 0.005  # keep provider calls overlapping
    iid = w.intent()
    barrier = threading.Barrier(agents)
    decisions, errors = [], []

    def agent(n):
        barrier.wait()
        try:
            decisions.append(w.guard.submit(w.proposal(iid, request_id=f"agent-{n}")).decision)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=agent, args=(n,)) for n in range(agents)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors
    assert decisions.count(Decision.APPROVED) == 1
    assert set(decisions) <= {Decision.APPROVED, Decision.IN_PROGRESS, Decision.DUPLICATE}
    assert len(w.live()) == 1
    assert w.sim.stats["executions"] == 1


class CrashAt(Hooks):
    def __init__(self, point):
        self.point = point

    def at(self, point, **ctx):
        if point == self.point:
            self.point = None
            raise SimulatedCrash(point)


@pytest.mark.parametrize("point", ["after_attempt_recorded", "after_provider_response"])
def test_gateway_crash_is_recovered_on_restart_with_one_effect(tmp_path, point):
    w = make_world(tmp_path, file_db=True, hooks=CrashAt(point))
    iid = w.intent()
    with pytest.raises(SimulatedCrash):
        w.guard.submit(w.proposal(iid))
    assert w.guard._state(iid) == IntentState.IN_FLIGHT  # the durable record survived the crash

    w.restart()  # new incarnation: orphaned SUBMITTING attempts become UNKNOWN and are reconciled
    again = w.guard.submit(w.proposal(iid, request_id="restarted-agent"))
    assert again.decision in (Decision.IN_PROGRESS, Decision.DUPLICATE)
    w.settle()
    assert w.guard._state(iid) == IntentState.COMPLETED
    assert len(w.live()) == 1


def test_attempt_budget_exhaustion_escalates(tmp_path):
    w = make_world(tmp_path)
    iid = w.intent()
    w.fault(FaultKind.TIMEOUT_BEFORE_EXECUTION, times=-1)
    w.guard.submit(w.proposal(iid))
    w.settle()
    assert w.guard._state(iid) == IntentState.NEEDS_REVIEW
    assert w.sim.stats["executions"] == 0
    assert w.sim.stats["create_calls"] == w.config.max_attempts

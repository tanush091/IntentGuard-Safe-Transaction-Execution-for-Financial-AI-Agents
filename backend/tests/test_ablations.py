"""
Each ablation must be a real code path: removing a component must change behaviour in the
scenario that component exists for. Where a single removal is masked by another component
(defence in depth), the test documents that and shows the combined removal failing.
Partial refunds are used so the provider's own balance check cannot mask a duplicate.
"""

from __future__ import annotations

import threading

import pytest

from intentguard import Decision, IntentState, ProtocolConfig
from intentguard.models import Attempt
from paysim import FaultKind, TxStatus
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.conftest import make_world

FULL = ProtocolConfig()


def _attempt_statuses(w, iid):
    with w.guard.session() as s:
        return [a.status for a in s.scalars(select(Attempt).where(Attempt.intent_id == iid).order_by(Attempt.attempt_no))]


def test_intent_binding_off_executes_hallucinated_amount(tmp_path):
    for cfg, executed in ((FULL, False), (FULL.without(intent_binding=False), True)):
        w = make_world(tmp_path / str(executed), cfg)
        iid = w.intent()
        w.guard.submit(w.proposal(iid, amount_minor=3000_00))
        assert any(t.amount_minor == 3000_00 for t in w.sim.all_transactions()) is executed


def test_effect_dedup_off_approves_second_proposal_but_stable_key_masks_it(tmp_path):
    w = make_world(tmp_path / "a", FULL.without(effect_dedup=False))
    iid = w.intent()
    w.guard.submit(w.proposal(iid))
    second = w.guard.submit(w.proposal(iid))
    assert second.decision == Decision.ALLOW  # the gate is gone...
    assert len(w.live()) == 1  # ...but the provider replays the same idempotency key

    w2 = make_world(tmp_path / "b", FULL.without(effect_dedup=False, stable_idempotency_key=False))
    iid2 = w2.intent()
    w2.guard.submit(w2.proposal(iid2))
    w2.guard.submit(w2.proposal(iid2))
    assert len(w2.live()) == 2  # with both gone, the second proposal moves money again


def test_reconciliation_off_assumes_failure_after_lost_response(tmp_path):
    w = make_world(tmp_path / "a", FULL.without(reconciliation=False))
    iid = w.intent()
    w.fault(FaultKind.TIMEOUT_AFTER_EXECUTION)
    w.guard.submit(w.proposal(iid))
    # The gateway wrongly concluded "no effect" and retried; the stable key made the provider
    # replay the original refund, and the ledger recorded that its assumption was violated.
    assert len(w.live()) == 1
    kinds = [e["kind"] for e in w.guard.timeline(iid)["audit"]]
    assert "attempt.absence_assumption_violated" in kinds

    w2 = make_world(tmp_path / "b", FULL.without(reconciliation=False, stable_idempotency_key=False))
    iid2 = w2.intent()
    w2.fault(FaultKind.TIMEOUT_AFTER_EXECUTION)
    w2.guard.submit(w2.proposal(iid2))
    w2.settle()
    assert len(w2.live()) == 2


@pytest.mark.parametrize("window, expected_live", [(30.0, 1), (0.0, 2)])
def test_absence_window_prevents_premature_retry_under_delayed_visibility(tmp_path, window, expected_live):
    w = make_world(tmp_path, FULL.without(absence_window_s=window, stable_idempotency_key=False))
    iid = w.intent()
    w.fault(FaultKind.TIMEOUT_AFTER_EXECUTION)
    w.fault(FaultKind.DELAYED_VISIBILITY, lag_s=20)
    w.guard.submit(w.proposal(iid))
    w.settle()
    # With the window, absence is never concluded before the record becomes visible.
    # Without it, "not found yet" is taken as proof and a second refund executes.
    assert len(w.live()) == expected_live
    # The window also sizes the post-completion watch, so without it the duplicate goes unnoticed.
    assert w.guard._state(iid) == IntentState.COMPLETED


def test_state_aware_recovery_off_claims_reversal_that_never_happened(tmp_path):
    w = make_world(tmp_path, FULL.without(state_aware_recovery=False))
    iid = w.intent()
    w.fault(FaultKind.CORRUPT_AMOUNT, factor=2.0)  # completes immediately: not cancellable
    w.guard.submit(w.proposal(iid))
    w.settle()
    assert w.guard._state(iid) == IntentState.COMPLETED  # the system believes all is well
    statuses = sorted(t.amount_minor for t in w.sim.all_transactions() if t.status == TxStatus.COMPLETED)
    assert statuses == [1500_00, 3000_00]  # the wrong refund was never reversed


def test_serialization_off_lets_concurrent_agents_both_pass_the_gate(tmp_path, monkeypatch):
    """
    Deterministic interleaving: both agents decide, then both reserve, before either calls
    the provider. With serialization the second agent is turned away at the decision.
    """
    import intentguard.engine as engine_mod
    from intentguard.engine import Hooks

    results = {}
    for serialize in (True, False):
        decided = threading.Barrier(2, timeout=2)
        reserved = threading.Barrier(2, timeout=2)

        class RaceHooks(Hooks):
            def at(self, point, **ctx):
                if point == "after_attempt_recorded":
                    try:
                        reserved.wait()
                    except threading.BrokenBarrierError:
                        pass  # serialized: only one agent ever gets here

        class _Time:
            @staticmethod
            def sleep(_s):  # the gap between decision and reservation in the ablated path
                decided.wait()

        cfg = FULL.without(serialize_intent=serialize, stable_idempotency_key=False)
        w = make_world(tmp_path / str(serialize), cfg, file_db=True, hooks=RaceHooks())
        iid = w.intent()
        monkeypatch.setattr(engine_mod, "time", _Time)
        decisions, errors = [], []

        def agent(n):
            try:
                decisions.append(w.guard.submit(w.proposal(iid, request_id=f"agent-{n}")).decision)
            except BaseException as exc:  # noqa: BLE001 - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=agent, args=(n,)) for n in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        monkeypatch.undo()
        sqlite = w.db_url.startswith("sqlite")
        if errors and (serialize or sqlite or not _attempt_number_conflict(errors[0])):
            raise errors[0]
        results[serialize] = (decisions, len(w.live()), errors)

    assert results[True][0].count(Decision.ALLOW) == 1 and results[True][1] == 1
    if sqlite:
        # SQLite's database-wide write lock orders the two reservations: both agents execute.
        assert results[False][0].count(Decision.ALLOW) == 2 and results[False][1] == 2
    else:
        # PostgreSQL: both agents reserve attempt 1 concurrently; the (intent_id, attempt_no) unique constraint
        # rejects the second reservation, so the ablated path fails loudly instead of executing twice.
        assert results[False][0] == [Decision.ALLOW] and results[False][1] == 1 and len(results[False][2]) == 1


def _attempt_number_conflict(exc: BaseException) -> bool:
    return isinstance(exc, IntegrityError) and "uq_attempt_no" in str(exc)

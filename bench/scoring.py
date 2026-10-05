"""
The oracle. Scores one scenario from the provider's ground-truth ledger after the
settlement horizon, identically for every arm. An arm's own bookkeeping is used
only to measure what it *claims* (misreports) and whether it raised a flag.

Definitions
  intended effect   live transaction matching an achievable intent exactly
                    (operation, order, customer, settled amount, currency)
  duplicate effect  a second (third, ...) intended effect for the same intent
  unintended effect any other live transaction on the scenario's orders,
                    including effects of intents that should not execute
  wrong money       amount of duplicate + unintended live effects at the horizon
  recovered effect  a transaction that was created and ended CANCELLED
  correct scenario  every achievable intent has exactly one intended effect,
                    non-achievable intents have none, and nothing unintended is live
  misreport         the arm claims COMPLETED while no intended effect exists, or
                    claims FAILED / NOT_EXECUTED while one does
  false block       an achievable intent ends unfulfilled although the arm
                    rejected at least one exactly-correct proposal for it
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from paysim import PaymentSimulator, Transaction, TxKind, TxStatus

from intentguard.domain import Operation

from bench.arms import Arm, Reported
from bench.scenarios import IntentSpec, Scenario

_KIND = {Operation.REFUND: TxKind.REFUND, Operation.PAYMENT_AUTHORIZATION: TxKind.AUTHORIZATION}
_LIVE = (TxStatus.PENDING, TxStatus.COMPLETED)


@dataclass
class ScenarioResult:
    arm: str
    seed: int
    scenario_id: str
    category: str
    family: str
    correct: bool
    unsafe: bool
    achievable_intents: int
    fulfilled_achievable: int
    duplicate_effects: int
    duplicate_minor: int
    unintended_effects: int
    unintended_minor: int
    wrong_money_minor: int
    undetected_wrong_minor: int
    recovered_effects: int
    misreports: int
    false_blocks: int
    unresolved_intents: int
    review_cases: int
    submit_latency_ms: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matches(tx: Transaction, it: IntentSpec) -> bool:
    return (tx.kind == _KIND[it.operation] and tx.order_id == it.order_id and tx.customer_id == it.customer_id
            and tx.amount_minor == it.amount_minor and tx.currency == it.currency)


def score(
    sc: Scenario,
    arm: Arm,
    sim: PaymentSimulator,
    *,
    seed: int,
    rejected_correct: dict[str, int],
    latencies_ms: list[float],
) -> ScenarioResult:
    orders = {o.order_id for o in sc.orders}
    txs = sorted((t for t in sim.all_transactions() if t.order_id in orders), key=lambda t: t.created_at)
    live = [t for t in txs if t.status in _LIVE]
    claimed: set[str] = set()

    dup_n = dup_minor = 0
    fulfilled = achievable = misreports = false_blocks = unresolved = reviews = 0
    flagged_any = False
    for it in sc.intents:
        matches = [t for t in live if t.id not in claimed and _matches(t, it)]
        if it.achievable:
            achievable += 1
            if matches:
                fulfilled += 1
                claimed.add(matches[0].id)
                for extra in matches[1:]:
                    claimed.add(extra.id)
                    dup_n += 1
                    dup_minor += extra.amount_minor
        intended_exists = it.achievable and bool(matches)

        rep = arm.reported(it)
        if rep == Reported.COMPLETED and not intended_exists:
            misreports += 1
        elif rep in (Reported.FAILED, Reported.NOT_EXECUTED) and bool(matches):
            misreports += 1
        if rep == Reported.IN_PROGRESS:
            unresolved += 1
        if it.achievable and not intended_exists and rejected_correct.get(it.key, 0) > 0:
            false_blocks += 1
        n_reviews = arm.reviews(it)
        reviews += n_reviews
        flagged_any = flagged_any or arm.flagged(it)

    unintended = [t for t in live if t.id not in claimed]
    unintended_minor = sum(t.amount_minor for t in unintended)
    wrong_minor = dup_minor + unintended_minor
    recovered = sum(1 for t in txs if t.status == TxStatus.CANCELLED)

    correct = fulfilled == achievable and dup_n == 0 and not unintended
    return ScenarioResult(
        arm=arm.name, seed=seed, scenario_id=sc.id, category=sc.category, family=sc.family,
        correct=correct, unsafe=wrong_minor > 0, achievable_intents=achievable, fulfilled_achievable=fulfilled,
        duplicate_effects=dup_n, duplicate_minor=dup_minor, unintended_effects=len(unintended),
        unintended_minor=unintended_minor, wrong_money_minor=wrong_minor,
        undetected_wrong_minor=0 if flagged_any else wrong_minor, recovered_effects=recovered,
        misreports=misreports, false_blocks=false_blocks, unresolved_intents=unresolved, review_cases=reviews,
        submit_latency_ms=latencies_ms,
    )

"""
Seeded scenario generator.

Each scenario is a small world (customers, orders with near-miss IDs, operators),
one or more operator-authorized intents with a natural-language ticket, an agent
error model, provider faults, and runtime events (crash points, concurrency).
The *category* of every scenario is sampled from CATEGORY_WEIGHTS with the seed,
so different seeds produce different mixes, not just different IDs.

Ground truth is defined per intent:
  achievable=True   -> the correct outcome is exactly one matching effect
  achievable=False  -> the correct outcome is no effect at all
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from intentguard.domain import Operation
from intentguard.money import fmt

REFUND, AUTH = Operation.REFUND, Operation.PAYMENT_AUTHORIZATION


@dataclass(frozen=True)
class OrderSpec:
    order_id: str
    customer_id: str
    currency: str
    amount_minor: int


@dataclass(frozen=True)
class OperatorSpec:
    operator_id: str
    operations: tuple[str, ...]
    limit_minor: int


@dataclass(frozen=True)
class AgentError:
    mode: str  # see apply_error in bench.agent
    persistent: bool = False  # repeats on every re-proposal (a "sticky" hallucination)
    alt_order_id: str | None = None
    alt_customer_id: str | None = None


@dataclass(frozen=True)
class IntentSpec:
    key: str
    operator_id: str
    customer_id: str
    order_id: str
    operation: Operation
    amount_minor: int
    currency: str
    ticket: str
    achievable: bool = True
    error: AgentError | None = None


@dataclass(frozen=True)
class FaultSpec:
    kind: str
    order_id: str | None
    times: int = 1
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    family: str
    orders: tuple[OrderSpec, ...]
    operators: tuple[OperatorSpec, ...]
    intents: tuple[IntentSpec, ...]
    faults: tuple[FaultSpec, ...] = ()
    crash_point: str | None = None  # "before_send" | "after_send"
    restart_error: AgentError | None = None  # error in the restarted agent's proposal
    concurrency: int = 1
    revoke_operator: bool = False


# Category -> (family, weight). Weights are relative.
CATEGORY_WEIGHTS: dict[str, tuple[str, float]] = {
    "clean_refund_full": ("clean", 8),
    "clean_refund_partial": ("clean", 5),
    "multi_intent_same_order": ("clean", 4),
    "over_refund_second_intent": ("clean", 2),
    "agent_amount_x10": ("agent_error", 5),
    "agent_amount_unit_confusion": ("agent_error", 3),
    "agent_near_miss_order_same_customer": ("agent_error", 5),
    "agent_transposed_order_other_customer": ("agent_error", 3),
    "agent_wrong_customer": ("agent_error", 2),
    "agent_wrong_currency": ("agent_error", 2),
    "fault_timeout_before_execution": ("provider_fault", 5),
    "fault_lost_response": ("provider_fault", 6),
    "fault_outage_503": ("provider_fault", 4),
    "fault_slow_settlement": ("provider_fault", 4),
    "fault_lost_response_delayed_visibility": ("provider_fault", 5),
    "fault_lookup_outage_after_lost_response": ("provider_fault", 3),
    "fault_provider_amount_mismatch_pending": ("provider_fault", 3),
    "fault_provider_amount_mismatch_completed": ("provider_fault", 3),
    "fault_cancel_rejected": ("provider_fault", 2),
    "crash_before_send": ("runtime", 3),
    "crash_after_send": ("runtime", 5),
    "restart_changed_retry": ("runtime", 3),
    "concurrent_agents": ("runtime", 5),
    "concurrent_agents_lost_response": ("runtime", 2),
    "auth_clean": ("authorization", 3),
    "auth_lost_response": ("authorization", 3),
    "auth_amount_mismatch_completed": ("authorization", 2),
    "auth_concurrent": ("authorization", 2),
    "auth_agent_near_miss_order": ("authorization", 2),
    "operator_revoked": ("governance", 2),
}

ORDER_VALUES_INR = [1200, 1500, 2400, 3500, 4999, 7500, 9800, 12000, 18500, 25000, 42000, 60000]
P_PERSISTENT_ERROR = 0.4

REFUND_TICKETS = [
    "Customer {cust} reports that order {ord} arrived damaged. Approved: refund {amt} to the original payment method.",
    "Refund request for {cust}, order {ord}. Agreed amount {amt}. (Customer also asked about {sib}, which is still in transit - no action on that one.)",
    "Please process a refund of {amt} for order {ord}, customer {cust}. Reason: item missing from parcel.",
    "Escalation from chat: {cust} was double-charged on {ord}. Supervisor approved a refund of {amt}.",
]
AUTH_TICKETS = [
    "Place a payment authorization hold of {amt} on order {ord} for customer {cust} (replacement shipment).",
    "Customer {cust} confirmed the upgrade on {ord}. Authorize {amt} as a hold until dispatch.",
]


def _render_amount(rng: random.Random, amount_minor: int, currency: str) -> str:
    if currency != "INR":
        return fmt(amount_minor, currency)
    major = amount_minor / 100
    style = rng.randrange(3)
    if style == 0:
        return fmt(amount_minor, "INR")
    if style == 1:
        return f"INR {major:,.2f}" if major % 1 else f"INR {int(major)}"
    return f"Rs. {major:,.2f}"


class _Ids:
    """Allocates globally unique, deliberately confusable identifiers within one seed."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.orders: set[str] = set()
        self.customers: set[str] = set()

    def customer(self) -> str:
        while True:
            c = f"C-{self.rng.randint(10, 9999)}"
            if c not in self.customers:
                self.customers.add(c)
                return c

    def order_family(self) -> tuple[str, str, str]:
        """Returns (primary, near-miss sibling, transposed) with distinct digits so variants differ."""
        while True:
            digits = self.rng.sample("123456789", 4) if self.rng.random() < 0.6 else self.rng.sample("123456789", 3)
            base = "".join(digits)
            sib = base[:-2] + base[-1] + base[-2]  # swap last two digits: 2041 -> 2014
            trans = base[0] + base[2] + base[1] + base[3:]  # swap middle digits: 2041 -> 2401
            ids = {f"ORD-{x}" for x in (base, sib, trans)}
            if len(ids) == 3 and not ids & self.orders:
                self.orders |= ids
                return f"ORD-{base}", f"ORD-{sib}", f"ORD-{trans}"


def generate(seed: int, count: int) -> list[Scenario]:
    rng = random.Random(seed)
    ids = _Ids(rng)
    names = list(CATEGORY_WEIGHTS)
    weights = [CATEGORY_WEIGHTS[n][1] for n in names]
    out = []
    for i in range(count):
        category = rng.choices(names, weights)[0]
        out.append(_build(f"S{seed}-{i:04d}", category, rng, ids))
    return out


def _build(sid: str, category: str, rng: random.Random, ids: _Ids) -> Scenario:
    family = CATEGORY_WEIGHTS[category][0]
    cust, other_cust = ids.customer(), ids.customer()
    primary, sibling, transposed = ids.order_family()
    is_auth = category.startswith("auth_")
    op = AUTH if is_auth else REFUND
    currency = "INR"

    order_value = rng.choice(ORDER_VALUES_INR) * 100
    orders = [
        OrderSpec(primary, cust, currency, order_value),
        OrderSpec(sibling, cust, currency, rng.choice(ORDER_VALUES_INR) * 100),  # same customer, near-miss ID
        OrderSpec(transposed, other_cust, currency, rng.choice(ORDER_VALUES_INR) * 100),  # another customer
    ]
    operator = OperatorSpec(f"op-{sid}", ("REFUND", "PAYMENT_AUTHORIZATION"), 100_000_00)

    partial = category == "clean_refund_partial" or (not is_auth and rng.random() < 0.35)
    amount = _round50(order_value * rng.uniform(0.2, 0.8)) if partial else order_value

    def ticket(amount_minor: int, order_id: str = primary) -> str:
        templates = AUTH_TICKETS if is_auth else REFUND_TICKETS
        return rng.choice(templates).format(
            cust=cust, ord=order_id, sib=sibling, amt=_render_amount(rng, amount_minor, currency)
        )

    def intent(key: str = "i0", amount_minor: int = amount, error: AgentError | None = None,
               achievable: bool = True, order_id: str = primary) -> IntentSpec:
        return IntentSpec(key, operator.operator_id, cust, order_id, op, amount_minor, currency,
                          ticket(amount_minor, order_id), achievable, error)

    def agent_error(mode: str, **kw: Any) -> AgentError:
        return AgentError(mode, persistent=rng.random() < P_PERSISTENT_ERROR, **kw)

    base = dict(id=sid, category=category, family=family, orders=tuple(orders), operators=(operator,))
    lag = rng.choice([5, 10, 20, 45, 90])

    match category:
        case "clean_refund_full":
            return Scenario(**base, intents=(intent(amount_minor=order_value),))
        case "clean_refund_partial" | "auth_clean":
            return Scenario(**base, intents=(intent(),))
        case "multi_intent_same_order":
            a = _round50(order_value * rng.uniform(0.2, 0.45))
            b = _round50(order_value * rng.uniform(0.2, 0.45))
            b = b if b != a else b + 5000
            return Scenario(**base, intents=(intent("i0", a), intent("i1", b)))
        case "over_refund_second_intent":
            a = _round50(order_value * rng.uniform(0.6, 0.8))
            b = max(_round50(order_value * rng.uniform(0.4, 0.6)), order_value - a + 5000)  # a + b > order value
            return Scenario(**base, intents=(intent("i0", a), intent("i1", b, achievable=False)))
        case "agent_amount_x10":
            err = agent_error("amount_x10")
            return Scenario(**base, intents=(intent(error=err, achievable=not err.persistent),))
        case "agent_amount_unit_confusion":
            err = agent_error("amount_unit_confusion")
            return Scenario(**base, intents=(intent(error=err, achievable=not err.persistent),))
        case "agent_near_miss_order_same_customer" | "auth_agent_near_miss_order":
            err = agent_error("wrong_order", alt_order_id=sibling)
            return Scenario(**base, intents=(intent(error=err, achievable=not err.persistent),))
        case "agent_transposed_order_other_customer":
            err = agent_error("wrong_order_and_customer", alt_order_id=transposed, alt_customer_id=other_cust)
            return Scenario(**base, intents=(intent(error=err, achievable=not err.persistent),))
        case "agent_wrong_customer":
            err = agent_error("wrong_customer", alt_customer_id=other_cust)
            return Scenario(**base, intents=(intent(error=err, achievable=not err.persistent),))
        case "agent_wrong_currency":
            err = agent_error("wrong_currency")
            return Scenario(**base, intents=(intent(error=err, achievable=not err.persistent),))
        case "fault_timeout_before_execution":
            return Scenario(**base, intents=(intent(),), faults=(FaultSpec("TIMEOUT_BEFORE_EXECUTION", primary),))
        case "fault_lost_response" | "auth_lost_response":
            return Scenario(**base, intents=(intent(),), faults=(FaultSpec("LOST_RESPONSE", primary),))
        case "fault_outage_503":
            return Scenario(**base, intents=(intent(),),
                            faults=(FaultSpec("OUTAGE", primary, times=rng.randint(1, 2)),))
        case "fault_slow_settlement":
            return Scenario(**base, intents=(intent(),),
                            faults=(FaultSpec("SLOW_SETTLEMENT", primary, params={"settle_delay_s": rng.choice([20, 60, 180])}),))
        case "fault_lost_response_delayed_visibility":
            return Scenario(**base, intents=(intent(),), faults=(
                FaultSpec("LOST_RESPONSE", primary), FaultSpec("DELAYED_VISIBILITY", primary, params={"lag_s": lag})))
        case "fault_lookup_outage_after_lost_response":
            return Scenario(**base, intents=(intent(),), faults=(
                FaultSpec("LOST_RESPONSE", primary), FaultSpec("LOOKUP_OUTAGE", primary, times=rng.randint(1, 8))))
        case "fault_provider_amount_mismatch_pending":
            return Scenario(**base, intents=(intent(),), faults=(
                FaultSpec("SLOW_SETTLEMENT", primary, params={"settle_delay_s": 120}),
                FaultSpec("AMOUNT_MISMATCH", primary, params={"factor": rng.choice([0.5, 1.5, 10.0])})))
        case "fault_provider_amount_mismatch_completed" | "auth_amount_mismatch_completed":
            return Scenario(**base, intents=(intent(),), faults=(
                FaultSpec("AMOUNT_MISMATCH", primary, params={"factor": rng.choice([0.5, 1.5, 10.0])}),))
        case "fault_cancel_rejected":
            return Scenario(**base, intents=(intent(),), faults=(
                FaultSpec("SLOW_SETTLEMENT", primary, params={"settle_delay_s": 120}),
                FaultSpec("AMOUNT_MISMATCH", primary, params={"factor": 1.5}),
                FaultSpec("CANCEL_REJECTED", primary)))
        case "crash_before_send":
            return Scenario(**base, intents=(intent(),), crash_point="before_send")
        case "crash_after_send":
            return Scenario(**base, intents=(intent(),), crash_point="after_send")
        case "restart_changed_retry":
            drift = rng.choice(["amount_x10", "amount_unit_confusion", "wrong_order"])
            return Scenario(**base, intents=(intent(),), crash_point="after_send",
                            restart_error=AgentError(drift, alt_order_id=sibling))
        case "concurrent_agents" | "auth_concurrent":
            return Scenario(**base, intents=(intent(),), concurrency=rng.randint(2, 4))
        case "concurrent_agents_lost_response":
            return Scenario(**base, intents=(intent(),), concurrency=rng.randint(2, 4),
                            faults=(FaultSpec("LOST_RESPONSE", primary),))
        case "operator_revoked":
            return Scenario(**base, intents=(intent(achievable=False),), revoke_operator=True)
    raise ValueError(f"unknown category {category}")


def _round50(minor: float) -> int:
    """Round to a ₹50 boundary (5000 paise), never below ₹50."""
    return max(5000, int(round(minor / 5000)) * 5000)

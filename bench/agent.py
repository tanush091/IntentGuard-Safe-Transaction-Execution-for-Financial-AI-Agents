"""
Scripted agent with an explicit error model.

The agent reads the facts of its ticket and proposes an operation. An AgentError
corrupts the proposal the way LLM agents are known to: wrong magnitude, unit
confusion, a near-miss identifier, the wrong customer, the wrong currency.
Transient errors affect only the first proposal; persistent errors repeat on
every re-proposal. The same agent behaviour is used for every architecture.
"""

from __future__ import annotations

import itertools
import threading

from intentguard.checks import Proposal

from bench.scenarios import AgentError, IntentSpec

_counter = itertools.count()
_counter_lock = threading.Lock()


def new_request_id(prefix: str) -> str:
    with _counter_lock:
        return f"{prefix}-r{next(_counter)}"


def apply_error(p: Proposal, err: AgentError) -> Proposal:
    fields = p.__dict__.copy()
    match err.mode:
        case "amount_x10":
            fields["amount_minor"] = p.amount_minor * 10
        case "amount_unit_confusion":  # rupees read as paise: ₹1,500 -> ₹15
            fields["amount_minor"] = max(1, p.amount_minor // 100)
        case "wrong_order":
            fields["order_id"] = err.alt_order_id
        case "wrong_order_and_customer":
            fields["order_id"], fields["customer_id"] = err.alt_order_id, err.alt_customer_id
        case "wrong_customer":
            fields["customer_id"] = err.alt_customer_id
        case "wrong_currency":
            fields["currency"] = "USD" if p.currency != "USD" else "INR"
        case _:
            raise ValueError(f"unknown agent error mode {err.mode}")
    return Proposal(**fields)


class ScriptedAgent:
    def __init__(self, spec: IntentSpec, agent_id: str, restart_error: AgentError | None = None):
        self.spec = spec
        self.agent_id = agent_id
        self.restart_error = restart_error
        self.proposals = 0

    def correct(self, request_id: str) -> Proposal:
        s = self.spec
        return Proposal(intent_id=s.key, request_id=request_id, agent_id=self.agent_id, operation=s.operation,
                        customer_id=s.customer_id, order_id=s.order_id, amount_minor=s.amount_minor,
                        currency=s.currency, rationale="scripted agent")

    def propose(self, request_id: str, *, restarted: bool = False) -> Proposal:
        p = self.correct(request_id)
        err = self.spec.error
        first = self.proposals == 0
        self.proposals += 1
        if restarted and self.restart_error is not None:
            return apply_error(p, self.restart_error)
        if err is not None and (first or err.persistent):
            return apply_error(p, err)
        return p

    def is_correct(self, p: Proposal) -> bool:
        c = self.correct(p.request_id)
        return (p.operation, p.customer_id, p.order_id, p.amount_minor, p.currency) == (
            c.operation, c.customer_id, c.order_id, c.amount_minor, c.currency)

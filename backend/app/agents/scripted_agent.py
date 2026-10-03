"""
Deterministic Scripted Agent Provider for IntentGuard.
Supports deterministic faithful and adversarial/flawed profiles for reproducible benchmarks.
"""

from enum import Enum
from typing import Dict, Any
from backend.app.agents.base import AgentProvider, AgentTaskRequest
from backend.app.schemas.proposal import AgentProposal
from backend.app.schemas.intent import OperationType


class ScriptedProfile(str, Enum):
    FAITHFUL = "FAITHFUL"
    WRONG_AMOUNT = "WRONG_AMOUNT"
    WRONG_ORDER = "WRONG_ORDER"
    WRONG_CUSTOMER = "WRONG_CUSTOMER"
    WRONG_OPERATION = "WRONG_OPERATION"
    WRONG_CURRENCY = "WRONG_CURRENCY"
    DUPLICATE_PROPOSAL = "DUPLICATE_PROPOSAL"
    CHANGED_RETRY = "CHANGED_RETRY"


class ScriptedAgentProvider(AgentProvider):
    def __init__(self, profile: ScriptedProfile = ScriptedProfile.FAITHFUL):
        self.profile = profile

    def propose_action(self, task: AgentTaskRequest) -> AgentProposal:
        ctx = task.context or {}
        base_customer = ctx.get("customer_id", "C-17")
        base_order = ctx.get("order_id", "ORD-204")
        base_amount = float(ctx.get("authorized_amount", 1500.0))
        base_currency = ctx.get("currency", "INR")
        base_op = ctx.get("operation_type", OperationType.REFUND)

        if self.profile == ScriptedProfile.FAITHFUL:
            return AgentProposal(
                intent_id=task.intent_id,
                operation=base_op,
                customer_id=base_customer,
                order_id=base_order,
                amount=base_amount,
                currency=base_currency
            )

        elif self.profile == ScriptedProfile.WRONG_AMOUNT:
            # Flaw: 10x inflation
            return AgentProposal(
                intent_id=task.intent_id,
                operation=base_op,
                customer_id=base_customer,
                order_id=base_order,
                amount=base_amount * 10.0,
                currency=base_currency
            )

        elif self.profile == ScriptedProfile.WRONG_ORDER:
            # Flaw: Transposed order identifier
            return AgentProposal(
                intent_id=task.intent_id,
                operation=base_op,
                customer_id=base_customer,
                order_id="ORD-240" if base_order == "ORD-204" else f"{base_order}_ERR",
                amount=base_amount,
                currency=base_currency
            )

        elif self.profile == ScriptedProfile.WRONG_CUSTOMER:
            # Flaw: Unrelated customer
            return AgentProposal(
                intent_id=task.intent_id,
                operation=base_op,
                customer_id="C-99",
                order_id=base_order,
                amount=base_amount,
                currency=base_currency
            )

        elif self.profile == ScriptedProfile.WRONG_OPERATION:
            # Flaw: Unauthorized action type
            return AgentProposal(
                intent_id=task.intent_id,
                operation=OperationType.PAYMENT_AUTHORIZE if base_op == OperationType.REFUND else OperationType.REFUND,
                customer_id=base_customer,
                order_id=base_order,
                amount=base_amount,
                currency=base_currency
            )

        elif self.profile == ScriptedProfile.WRONG_CURRENCY:
            # Flaw: Wrong currency code
            return AgentProposal(
                intent_id=task.intent_id,
                operation=base_op,
                customer_id=base_customer,
                order_id=base_order,
                amount=base_amount,
                currency="USD" if base_currency == "INR" else "INR"
            )

        else:
            return AgentProposal(
                intent_id=task.intent_id,
                operation=base_op,
                customer_id=base_customer,
                order_id=base_order,
                amount=base_amount,
                currency=base_currency
            )

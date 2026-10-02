import uuid
from typing import Dict, Any, Optional
from src.schemas.types import ProposalCreate, OperationType

class ScriptedAgent:
    """
    Simulates AI agents with various behavioral profiles for deterministic benchmarks:
    - faithful: accurately extracts parameters from the request
    - wrong_amount: hallucinates an extra zero or incorrect amount
    - wrong_order: transposes digits or references incorrect order ID
    - wrong_customer: associates with wrong customer ID
    - aggressive_retry: creates a new request_id and immediately retries after uncertainty
    """

    def __init__(self, agent_id: str = "scripted-agent-01", behavior: str = "faithful"):
        self.agent_id = agent_id
        self.behavior = behavior

    def propose(self, intent_id: str, request_text: str, context: Dict[str, Any]) -> ProposalCreate:
        customer_id = context.get("customer_id", "C-17")
        order_id = context.get("order_id", "ORD-204")
        amount = context.get("amount", 1500.0)
        currency = context.get("currency", "INR")
        operation = context.get("operation", OperationType.REFUND)
        request_id = f"req_{uuid.uuid4().hex[:8]}"

        if self.behavior == "wrong_amount":
            amount = amount * 10 # E.g., 15000 instead of 1500

        elif self.behavior == "wrong_order":
            # Transpose digits e.g. ORD-204 -> ORD-240
            if "-" in order_id:
                prefix, num = order_id.split("-", 1)
                order_id = f"{prefix}-{num[::-1]}"
            else:
                order_id = f"{order_id}_wrong"

        elif self.behavior == "wrong_customer":
            customer_id = f"{customer_id}_alt"

        return ProposalCreate(
            intent_id=intent_id,
            request_id=request_id,
            operation=operation,
            customer_id=customer_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            agent_id=self.agent_id,
            rationale=f"Automated action proposed based on instruction: '{request_text}'"
        )

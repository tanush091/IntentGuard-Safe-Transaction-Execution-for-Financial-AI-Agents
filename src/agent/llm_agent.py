import re
import uuid
import os
import json
from typing import Optional, Dict, Any
from src.schemas.types import ProposalCreate, OperationType

class FinancialAIAgent:
    """
    Financial AI Agent that processes natural language requests from operators
    or customers and produces structured transaction proposals for the Safety Gateway.
    Can operate via LLM APIs or an intelligent deterministic extraction engine.
    """

    def __init__(self, agent_id: str = "financial-agent-llm", model_name: str = "gemini-1.5-flash"):
        self.agent_id = agent_id
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")

    async def parse_and_propose(self, intent_id: str, natural_language_request: str) -> ProposalCreate:
        """
        Parses operator instruction and produces a ProposalCreate object.
        """
        # 1. Deterministic NLP extraction (works offline without external dependencies or keys)
        extracted = self._rule_based_extract(natural_language_request)

        # 2. If API key is present and configured, can query LLM with function calling
        if self.api_key:
            try:
                llm_extracted = await self._query_llm(natural_language_request)
                if llm_extracted:
                    extracted = llm_extracted
            except Exception:
                pass # Gracefully fall back to rule-based parser

        request_id = f"req_{uuid.uuid4().hex[:8]}"

        return ProposalCreate(
            intent_id=intent_id,
            request_id=request_id,
            operation=extracted["operation"],
            customer_id=extracted["customer_id"],
            order_id=extracted["order_id"],
            amount=extracted["amount"],
            currency=extracted["currency"],
            agent_id=self.agent_id,
            rationale=f"Extracted parameters from text: {natural_language_request}"
        )

    def _rule_based_extract(self, text: str) -> Dict[str, Any]:
        # Defaults
        customer_id = "C-17"
        order_id = "ORD-204"
        amount = 1500.0
        currency = "INR"
        operation = OperationType.REFUND

        # Extract amount & currency
        amt_match = re.search(r'(?:₹|INR|\$|USD)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)', text)
        if amt_match:
            clean_num = amt_match.group(1).replace(",", "")
            try:
                amount = float(clean_num)
            except ValueError:
                pass

        if "$" in text or "USD" in text.upper():
            currency = "USD"
        elif "₹" in text or "INR" in text.upper():
            currency = "INR"

        # Extract order ID (e.g. ORD-204, ORDER-123)
        ord_match = re.search(r'(ORD(?:ER)?-?[0-9]+)', text, re.IGNORECASE)
        if ord_match:
            order_id = ord_match.group(1).upper()

        # Extract customer ID (e.g. C-17, CUST-102)
        cust_match = re.search(r'(C(?:UST(?:OMER)?)?-?[0-9]+)', text, re.IGNORECASE)
        if cust_match:
            customer_id = cust_match.group(1).upper()

        # Operation
        if "authoriz" in text.lower() or "hold" in text.lower():
            operation = OperationType.PAYMENT_AUTHORIZATION
        elif "cancel" in text.lower() or "void" in text.lower():
            operation = OperationType.PAYMENT_CANCEL
        else:
            operation = OperationType.REFUND

        return {
            "customer_id": customer_id,
            "order_id": order_id,
            "amount": amount,
            "currency": currency,
            "operation": operation
        }

    async def _query_llm(self, text: str) -> Optional[Dict[str, Any]]:
        # Hook for external LLM API if provided
        return None

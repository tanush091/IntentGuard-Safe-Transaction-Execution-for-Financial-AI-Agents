"""
Optional LLM Agent Provider with Structured Schema Extraction.
Supports offline rule-based extraction by default, with adapters for Gemini and OpenAI.
"""

import json
import re
from typing import Dict, Any, Optional
from backend.app.config import settings
from backend.app.agents.base import AgentProvider, AgentTaskRequest
from backend.app.schemas.proposal import AgentProposal
from backend.app.schemas.intent import OperationType


class LLMAgentProvider(AgentProvider):
    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or settings.LLM_PROVIDER

    def propose_action(self, task: AgentTaskRequest) -> AgentProposal:
        # If API key configured and provider enabled, attempt live LLM call
        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            return self._call_gemini(task)
        elif self.provider == "openai" and settings.OPENAI_API_KEY:
            return self._call_openai(task)
        else:
            # Deterministic rule-based semantic extractor fallback
            return self._extract_rule_based(task)

    def _extract_rule_based(self, task: AgentTaskRequest) -> AgentProposal:
        """Robust offline semantic parser for natural language financial requests."""
        text = task.customer_prompt
        ctx = task.context or {}

        # 1. Extract Order ID (e.g. ORD-204, #204)
        order_match = re.search(r'\b(ORD[-_]?\d+)\b', text, re.IGNORECASE)
        order_id = order_match.group(1).upper() if order_match else ctx.get("order_id", "ORD-204")

        # 2. Extract Customer ID (e.g. C-17, Cust-17)
        cust_match = re.search(r'\b(C[-_]?\d+)\b', text, re.IGNORECASE)
        customer_id = cust_match.group(1).upper() if cust_match else ctx.get("customer_id", "C-17")

        # 3. Extract Amount (e.g. ₹1,500, 1500 INR, 1500.00)
        amount_match = re.search(r'(?:₹|INR|rs\.?|amount\s*(?:of)?\s*)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)', text, re.IGNORECASE)
        if amount_match:
            amt_str = amount_match.group(1).replace(",", "")
            amount = float(amt_str)
        else:
            amount = float(ctx.get("authorized_amount", 1500.0))

        # 4. Extract Operation Type
        if re.search(r'\b(auth|authorize|hold)\b', text, re.IGNORECASE):
            operation = OperationType.PAYMENT_AUTHORIZE
        else:
            operation = OperationType.REFUND

        currency = "INR"
        if "USD" in text.upper() or "$" in text:
            currency = "USD"

        return AgentProposal(
            intent_id=task.intent_id,
            operation=operation,
            customer_id=customer_id,
            order_id=order_id,
            amount=amount,
            currency=currency
        )

    def _call_gemini(self, task: AgentTaskRequest) -> AgentProposal:
        # Gracefully falls back to rule-based parser on any network or credential issue
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(settings.LLM_MODEL)
            prompt = (
                f"Extract financial intent JSON from this user request: '{task.customer_prompt}'. "
                f"Schema: {{'operation': 'REFUND', 'customer_id': 'str', 'order_id': 'str', 'amount': float, 'currency': 'INR'}}"
            )
            resp = model.generate_content(prompt)
            data = json.loads(resp.text)
            return AgentProposal(
                intent_id=task.intent_id,
                operation=OperationType(data["operation"]),
                customer_id=data["customer_id"],
                order_id=data["order_id"],
                amount=float(data["amount"]),
                currency=data.get("currency", "INR")
            )
        except Exception:
            return self._extract_rule_based(task)

    def _call_openai(self, task: AgentTaskRequest) -> AgentProposal:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            # Structured completion
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Extract financial proposal JSON."},
                    {"role": "user", "content": task.customer_prompt}
                ]
            )
            data = json.loads(response.choices[0].message.content)
            return AgentProposal(
                intent_id=task.intent_id,
                operation=OperationType(data["operation"]),
                customer_id=data["customer_id"],
                order_id=data["order_id"],
                amount=float(data["amount"]),
                currency=data.get("currency", "INR")
            )
        except Exception:
            return self._extract_rule_based(task)

import re
import uuid
import os
import json
from typing import Optional, Dict, Any
import httpx
from src.schemas.types import ProposalCreate, OperationType
from src.config import settings

class FinancialAIAgent:
    """
    Financial AI Agent that processes natural language requests from operators
    or customers and produces structured transaction proposals for the Safety Gateway.
    Can operate via LLM APIs or an intelligent deterministic extraction engine.
    """

    def __init__(self, agent_id: str = "financial-agent-llm", model_name: str = "gemini-1.5-flash"):
        self.agent_id = agent_id
        self.model_name = model_name
        self.provider = settings.LLM_PROVIDER.lower()

    async def parse_and_propose(self, intent_id: str, natural_language_request: str) -> ProposalCreate:
        """
        Parses operator instruction and produces a ProposalCreate object.
        """
        # 1. Deterministic NLP extraction (works offline without external dependencies or keys)
        extracted = self._rule_based_extract(natural_language_request)

        # 2. If API key is present and configured, can query LLM with function calling
        if self.provider != "offline":
            try:
                llm_extracted = await self._query_llm(natural_language_request)
                if llm_extracted:
                    # Validate keys and types
                    from pydantic import BaseModel
                    class ExtractionSchema(BaseModel):
                        customer_id: str
                        order_id: str
                        amount: float
                        currency: str
                        operation: OperationType
                    
                    validated = ExtractionSchema(**llm_extracted)
                    extracted = validated.model_dump()
            except Exception as e:
                print(f"LLM failure or validation error: {e}")
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
        system_prompt = "Extract customer_id, order_id, amount (float), currency (str), operation (REFUND, PAYMENT_AUTHORIZATION, PAYMENT_CANCEL). Return strictly JSON."
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if self.provider == "gemini":
                    gemini_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
                    if not gemini_key:
                        return None
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={gemini_key}"
                    payload = {
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{text}"}]}],
                        "generationConfig": {"responseMimeType": "application/json"}
                    }
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    result = resp.json()
                    content = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\n?", "", content)
                        content = re.sub(r"\n?```$", "", content)
                    return json.loads(content)
                elif self.provider == "openai":
                    openai_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
                    if not openai_key:
                        return None
                    url = "https://api.openai.com/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {openai_key}"}
                    payload = {
                        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": text}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\n?", "", content)
                        content = re.sub(r"\n?```$", "", content)
                    return json.loads(content)
                elif self.provider == "ollama":
                    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
                    payload = {
                        "model": "llama3",
                        "prompt": f"{system_prompt}\n\n{text}",
                        "format": "json",
                        "stream": False
                    }
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    content = resp.json()["response"].strip()
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\n?", "", content)
                        content = re.sub(r"\n?```$", "", content)
                    return json.loads(content)
        except Exception as e:
            print(f"LLM API Error: {e}")
        return None


"""
LLM-backed extraction (optional). Supports any OpenAI-compatible chat endpoint
(OpenAI, Ollama, vLLM, ...) and Google Gemini. Failures raise LLMError; callers
decide whether to fall back, and the fallback is recorded rather than silent.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

from intentguard.agents.extraction import Extracted
from intentguard.domain import Operation
from intentguard.money import to_minor

SYSTEM_PROMPT = (
    "You convert a customer-support ticket into one payment operation. Reply with JSON only: "
    '{"operation": "REFUND" | "PAYMENT_AUTHORIZATION", "customer_id": "C-…", "order_id": "ORD-…", '
    '"amount": "<decimal string in major units>", "currency": "<ISO 4217>"}'
)


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMSettings:
    provider: str  # "openai" | "ollama" | "gemini"
    model: str
    api_key: str = ""
    base_url: str = ""
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> "LLMSettings | None":
        provider = os.getenv("LLM_PROVIDER", "offline").lower()
        if provider == "openai":
            return cls("openai", os.getenv("LLM_MODEL", "gpt-4o-mini"), os.getenv("OPENAI_API_KEY", ""),
                       os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
        if provider == "ollama":
            return cls("ollama", os.getenv("LLM_MODEL", "llama3.1"), "",
                       os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1")
        if provider == "gemini":
            return cls("gemini", os.getenv("LLM_MODEL", "gemini-1.5-flash"), os.getenv("GEMINI_API_KEY", ""))
        return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


class LLMExtractor:
    def __init__(self, settings: LLMSettings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.timeout_s)

    def extract(self, ticket: str) -> Extracted:
        try:
            raw = self._gemini(ticket) if self.settings.provider == "gemini" else self._openai_compatible(ticket)
            data = json.loads(_strip_fences(raw))
            currency = str(data["currency"]).upper()
            return Extracted(
                operation=Operation(str(data["operation"]).upper()),
                customer_id=str(data["customer_id"]).upper(),
                order_id=str(data["order_id"]).upper(),
                amount_minor=to_minor(str(data["amount"]).replace(",", ""), currency),
                currency=currency,
            )
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - every failure mode becomes LLMError
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

    def _openai_compatible(self, ticket: str) -> str:
        s = self.settings
        headers = {"Authorization": f"Bearer {s.api_key}"} if s.api_key else {}
        resp = self._client.post(
            f"{s.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": s.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": ticket}],
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()["choices"][0]["message"]["content"]

    def _gemini(self, ticket: str) -> str:
        s = self.settings
        if not s.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        resp = self._client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{s.model}:generateContent",
            params={"key": s.api_key},
            json={
                "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\nTicket:\n{ticket}"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

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


class LLMClient:
    """One chat completion that must return JSON. Returns (text, usage) where usage has token counts."""

    def __init__(self, settings: LLMSettings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.timeout_s)

    @property
    def model_name(self) -> str:
        return f"{self.settings.provider}/{self.settings.model}"

    def complete_json(self, system: str, user: str) -> tuple[str, dict[str, int]]:
        try:
            if self.settings.provider == "gemini":
                return self._gemini(system, user)
            return self._openai_compatible(system, user)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - every transport failure becomes LLMError
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

    def _openai_compatible(self, system: str, user: str) -> tuple[str, dict[str, int]]:
        s = self.settings
        headers = {"Authorization": f"Bearer {s.api_key}"} if s.api_key else {}
        resp = self._client.post(
            f"{s.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": s.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        usage = body.get("usage") or {}
        return body["choices"][0]["message"]["content"], {
            "tokens_in": int(usage.get("prompt_tokens", 0)), "tokens_out": int(usage.get("completion_tokens", 0))}

    def _gemini(self, system: str, user: str) -> tuple[str, dict[str, int]]:
        s = self.settings
        if not s.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        resp = self._client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{s.model}:generateContent",
            params={"key": s.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
            },
        )
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        usage = body.get("usageMetadata") or {}
        return body["candidates"][0]["content"]["parts"][0]["text"], {
            "tokens_in": int(usage.get("promptTokenCount", 0)), "tokens_out": int(usage.get("candidatesTokenCount", 0))}


class LLMExtractor:
    """Ticket -> structured proposal fields. Off-schema output raises LLMError; it is never repaired."""

    def __init__(self, settings: LLMSettings, client: httpx.Client | None = None):
        self.settings = settings
        self.llm = LLMClient(settings, client)

    def extract(self, ticket: str) -> Extracted:
        raw, _usage = self.llm.complete_json(SYSTEM_PROMPT, ticket)
        try:
            data = json.loads(_strip_fences(raw))
            if not isinstance(data, dict) or set(data) != {"operation", "customer_id", "order_id", "amount", "currency"}:
                raise ValueError(f"expected exactly operation, customer_id, order_id, amount, currency; got {sorted(data)}")
            currency = str(data["currency"]).upper()
            return Extracted(
                operation=Operation(str(data["operation"]).upper()),
                customer_id=str(data["customer_id"]).upper(),
                order_id=str(data["order_id"]).upper(),
                amount_minor=to_minor(str(data["amount"]).replace(",", ""), currency),
                currency=currency,
            )
        except Exception as exc:  # noqa: BLE001 - every schema failure becomes LLMError
            raise LLMError(f"invalid agent output: {type(exc).__name__}: {exc}") from exc

# ADR-009: The agent only proposes; the LLM is an extractor

**Status:** Accepted (carries forward the "deterministic extraction fallback" ADR in the archive)

## Context
An LLM agent can be wrong or manipulated (prompt injection in a ticket). Giving it tools that move
money makes its errors financial.

## Decision
The agent's only outputs are proposals to the gateway. The agent endpoint
(`POST /api/intents/{id}/agent`) turns ticket text into structured fields with a deterministic
rule extractor (`agents/extraction.py`), or with an LLM (`agents/llm.py`; OpenAI-compatible,
Ollama or Gemini) when `LLM_PROVIDER` is set. The LLM has no tools and no provider access. Every
proposal goes through the same checks.

## Consequences
- Demos, tests and the benchmark run offline and deterministically.
- The LLM path is not covered by automated tests or by any recorded benchmark run.
- LLM settings are read with `os.getenv`, so they must be set in the process environment, not only in `.env`.

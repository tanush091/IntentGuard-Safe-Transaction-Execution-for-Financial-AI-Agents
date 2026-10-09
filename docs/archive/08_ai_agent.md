> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 08. AI Agent

## Agent Architecture & Provider Interface

The AI Agent component in IntentGuard is responsible for interpreting unstructured human/customer communications and formulating candidate transaction proposals.

---

## 1. Architectural Boundary
```
[Unstructured Customer Prompt]
               │
               ▼
   ┌───────────────────────┐
   │     AgentProvider     │
   │  propose_action(...)  │
   └───────────┬───────────┘
               │
               ▼ Strict Pydantic Validation
      [AgentProposal JSON]
               │
               ▼ (Submitted to Gateway via HTTP POST)
   ┌───────────────────────┐
   │ Safety Gateway / Port │
   └───────────────────────┘
```

**Key Security Boundaries**:
1. The AI Agent has **no direct access or credentials** to the payment service.
2. The AI Agent cannot invoke any internal financial database update methods.
3. Every agent proposal must parse strictly into the `AgentProposal` schema. Malformed outputs are rejected before gateway analysis.

---

## 2. The Abstract Provider Interface

```python
from abc import ABC, abstractmethod
from backend.app.schemas.proposal import AgentProposal, AgentRequest

class AgentProvider(ABC):
    @abstractmethod
    def propose_action(self, request: AgentRequest) -> AgentProposal:
        """
        Formulate a structured transaction proposal based on input context.
        Raises MalformedProposalException if output cannot be validated.
        """
        pass
```

---

## 3. ScriptedAgentProvider (Deterministic Baseline)
To guarantee reproducible experiments without depending on external network access, API tokens, or non-deterministic token sampling, IntentGuard implements a comprehensive `ScriptedAgentProvider`.

The scripted provider supports deterministic behavior profiles:
- `FAITHFUL`: Accurately replicates the authorized parameters.
- `WRONG_AMOUNT`: Dispatches an altered amount (e.g., 10x authorized amount).
- `WRONG_ORDER`: Transposes or alters the order ID (e.g., `ORD-240` instead of `ORD-204`).
- `WRONG_CUSTOMER`: Proposes a different customer ID (e.g., `C-99`).
- `WRONG_OPERATION`: Proposes an unauthorized operation (e.g., `PAYMENT` instead of `REFUND`).
- `WRONG_CURRENCY`: Proposes an altered currency code (e.g., `USD` instead of `INR`).
- `DUPLICATE_PROPOSAL`: Re-submits an already-completed proposal.
- `MALFORMED_OUTPUT`: Generates unparseable JSON to test gateway schema resilience.

---

## 4. LLMAgentProvider (Optional Adapter)
For real-world evaluation, an optional LLM adapter connects to modern LLM APIs (Google Gemini, OpenAI, or local Ollama instances) using structured output / JSON tool calling mode.
- Configuration is loaded entirely via environment variables (`LLM_PROVIDER`, `GEMINI_API_KEY`, `OPENAI_API_KEY`).
- When offline or keys are absent, the system gracefully falls back to deterministic rule-based semantic extraction.

"""
Abstract Agent Provider Interface.
Defines the contract for AI agents proposing financial transactions.
AI agents must NEVER have direct access or credentials to payment providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.proposal import AgentProposal


class AgentTaskRequest(BaseModel):
    intent_id: str
    customer_prompt: str
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AgentProvider(ABC):
    @abstractmethod
    def propose_action(self, task: AgentTaskRequest) -> AgentProposal:
        """
        Synthesize context and propose a structured financial transaction.
        Raises MalformedProposalException if proposal schema cannot be satisfied.
        """
        pass

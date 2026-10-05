"""IntentGuard: an intent-consistent transaction protocol between AI agents and payment providers."""

from intentguard.checks import Proposal
from intentguard.config import ProtocolConfig
from intentguard.domain import Decision, IntentState, Operation
from intentguard.engine import IntentGuard, SubmitResult

__all__ = ["Decision", "IntentGuard", "IntentState", "Operation", "Proposal", "ProtocolConfig", "SubmitResult"]

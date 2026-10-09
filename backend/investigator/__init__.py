"""
AI exception investigator (docs/DECISIONS.md ADR-013, ADR-014).

The LLM interprets an exception: it classifies it, summarizes the evidence and recommends one
action from a fixed set. It decides nothing. A deterministic policy gate decides whether the
recommended action is permitted in the intent's current state, and only a permitted action can be
applied, through the same engine paths the worker uses. Without an LLM configured, a
deterministic rule classifier produces the recommendation.
"""

from investigator.classifier import (
    ACTIONS,
    CLASSIFICATIONS,
    Classifier,
    InvalidOutput,
    LLMClassifier,
    OfflineClassifier,
)
from investigator.evidence import EXCEPTION_STATES, Bundle, build_bundle
from investigator.policy import Verdict, gate
from investigator.service import InvestigatorOutputRejected, apply_investigation, investigate

__all__ = [
    "ACTIONS",
    "CLASSIFICATIONS",
    "EXCEPTION_STATES",
    "Bundle",
    "Classifier",
    "InvalidOutput",
    "InvestigatorOutputRejected",
    "LLMClassifier",
    "OfflineClassifier",
    "Verdict",
    "apply_investigation",
    "build_bundle",
    "gate",
    "investigate",
]

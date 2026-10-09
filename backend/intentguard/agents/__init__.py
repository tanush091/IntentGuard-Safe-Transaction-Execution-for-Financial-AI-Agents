"""
Agents turn a support ticket into a structured proposal. They never hold provider
credentials: their only output is a Proposal that the gateway evaluates.
"""

from intentguard.agents.extraction import Extracted, ExtractionError, extract
from intentguard.agents.llm import LLMClient, LLMError, LLMExtractor, LLMSettings

__all__ = ["Extracted", "ExtractionError", "LLMClient", "LLMError", "LLMExtractor", "LLMSettings", "extract"]

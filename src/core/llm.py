from __future__ import annotations

from src.tools.deep_research.tools import TradingAgentsLLM


def get_llm_client() -> TradingAgentsLLM:
    """Return the project OpenAI-compatible LLM client."""
    return TradingAgentsLLM()

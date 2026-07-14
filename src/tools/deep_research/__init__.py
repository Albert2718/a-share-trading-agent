from __future__ import annotations

from .pipeline import TradingAgentOrchestrator
from .schemas import AnalysisContext, to_dict
from .utils import normalize_a_share_code


def run_deep_research(code: str, depth: str = "standard", risk_profile: str = "balanced") -> dict:
    """Run the deterministic deep-research pipeline as one ChatAgent tool."""
    norm = normalize_a_share_code(code)
    orchestrator = TradingAgentOrchestrator()
    candidates = orchestrator.candidates_from_codes([norm])
    report = orchestrator.analyze(
        candidates,
        AnalysisContext(depth=depth, risk_profile=risk_profile, use_llm=True, history_days=160),
        mode="chat_deep_research",
    )
    data = to_dict(report)
    decisions = data.get("all_decisions", [])
    return {
        "ok": bool(decisions),
        "code": norm,
        "summary": data.get("summary", ""),
        "top_decision": decisions[0] if decisions else None,
        "source": "deep_research_pipeline",
    }


__all__ = ["TradingAgentOrchestrator", "run_deep_research"]

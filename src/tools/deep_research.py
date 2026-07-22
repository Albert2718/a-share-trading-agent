from __future__ import annotations

from typing import Any

from src.research.orchestrator import ResearchOrchestrator
from src.research.schemas import AnalysisContext, to_dict
from src.tools.utils import normalize_a_share_code


class DeepResearchTool:
    def __init__(self, orchestrator: ResearchOrchestrator | None = None):
        self.orchestrator = orchestrator or ResearchOrchestrator()

    def run(
        self,
        code: str,
        depth: str = "standard",
        risk_profile: str = "balanced",
        personal_context: dict[str, Any] | None = None,
    ) -> dict:
        norm = normalize_a_share_code(code)
        candidates = self.orchestrator.candidates_from_codes([norm])
        report = self.orchestrator.analyze(
            candidates,
            AnalysisContext(
                depth=depth,
                risk_profile=risk_profile,
                use_llm=True,
                history_days=160,
                personal_context=personal_context or {},
            ),
            mode="chat_deep_research",
        )
        data = to_dict(report)
        decisions = data.get("all_decisions", [])
        return {
            "ok": bool(decisions),
            "code": norm,
            "summary": data.get("summary", ""),
            "top_decision": decisions[0] if decisions else None,
            "personal_context": personal_context or {},
            "source": "deep_research_pipeline",
        }

def run_deep_research(
    code: str,
    depth: str = "standard",
    risk_profile: str = "balanced",
    personal_context: dict[str, Any] | None = None,
) -> dict:
    return DeepResearchTool().run(code, depth, risk_profile, personal_context)

from __future__ import annotations

from src.tools.definitions import ToolDefinition
from src.tools.utils import normalize_a_share_code

from .orchestrator import ResearchOrchestrator
from .schemas import AnalysisContext, to_dict


class DeepResearchTool:
    def __init__(self, orchestrator: ResearchOrchestrator | None = None):
        self.orchestrator = orchestrator or ResearchOrchestrator()

    def run(self, code: str, depth: str = "standard", risk_profile: str = "balanced") -> dict:
        norm = normalize_a_share_code(code)
        candidates = self.orchestrator.candidates_from_codes([norm])
        report = self.orchestrator.analyze(
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

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_deep_research",
            description="对单只 A 股运行量化、基本面、新闻、情绪和 CIO 综合深度分析。",
            properties={
                "code": {"type": "string", "description": "6 位 A 股代码。"},
                "depth": {"type": "string", "description": "分析深度：quick、standard 或 full。"},
                "risk_profile": {
                    "type": "string",
                    "description": "风险偏好：conservative、balanced 或 aggressive。",
                },
            },
            required=("code",),
            handler=self.run,
        )


def run_deep_research(code: str, depth: str = "standard", risk_profile: str = "balanced") -> dict:
    return DeepResearchTool().run(code, depth, risk_profile)

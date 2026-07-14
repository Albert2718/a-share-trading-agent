from __future__ import annotations

import unittest

from src.agents.research.orchestrator import ResearchOrchestrator
from src.agents.research.schemas import (
    AnalysisContext,
    FinalReport,
    FundamentalReport,
    NewsReport,
    QuantReport,
    SentimentReport,
    StockCandidate,
    StockDecision,
)
from src.agents.research.tool import DeepResearchTool
from src.agents.research.analysts.sentiment import SentimentAnalyst


class _CompositeOrchestrator:
    def candidates_from_codes(self, codes):
        return [StockCandidate(code=codes[0], name="贵州茅台")]

    def analyze(self, candidates, context, mode="single", **kwargs):
        decision = StockDecision(code=candidates[0].code, name=candidates[0].name, action="watch", rank_score=66)
        return FinalReport(
            generated_at="2026-07-14 00:00:00",
            mode=mode,
            all_decisions=[decision],
            top_picks=[decision],
            summary="one decision",
        )


class _Analyst:
    def __init__(self, report):
        self.report = report

    def analyze(self, candidate, context):
        return self.report


class _RaisingAnalyst:
    def analyze(self, candidate, context):
        raise RuntimeError("provider unavailable")


class _MarketData:
    def hot_candidates(self, top=100):
        return [{"code": "600519", "name": "贵州茅台"}]

    def baidu_vote(self, code):
        return []


class _CIO:
    def __init__(self):
        self.received = None

    def decide_one(self, quant, fundamental, news, sentiment, **kwargs):
        self.received = (quant, fundamental, news, sentiment)
        return StockDecision(code=quant.code, name=quant.name, action="watch")

    def build_report(self, decisions, mode):
        return FinalReport(generated_at="now", mode=mode, all_decisions=decisions, summary="fallback complete")


class _FailingCIO:
    def decide_one(self, quant, fundamental, news, sentiment, **kwargs):
        raise RuntimeError("cio unavailable")

    def build_report(self, decisions, mode):
        return FinalReport(generated_at="now", mode=mode, all_decisions=decisions, summary="cio fallback")


class ResearchToolTests(unittest.TestCase):
    def test_composite_tool_preserves_chat_payload(self):
        result = DeepResearchTool(_CompositeOrchestrator()).run("SH.600519", depth="full")

        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "600519")
        self.assertEqual(result["top_decision"]["rank_score"], 66)
        self.assertEqual(result["source"], "deep_research_pipeline")

    def test_orchestrator_continues_with_unavailable_role(self):
        candidate = StockCandidate(code="600519", name="贵州茅台")
        cio = _CIO()
        orchestrator = ResearchOrchestrator(
            market_data=object(),
            quant=_Analyst(QuantReport(code=candidate.code, name=candidate.name)),
            fundamental=_Analyst(FundamentalReport(code=candidate.code, name=candidate.name, status="unavailable")),
            news=_Analyst(NewsReport(code=candidate.code, name=candidate.name)),
            sentiment=_Analyst(SentimentReport(code=candidate.code, name=candidate.name)),
            cio=cio,
        )

        report = orchestrator.analyze([candidate], AnalysisContext(use_llm=False))

        self.assertEqual(report.summary, "fallback complete")
        self.assertEqual(cio.received[1].status, "unavailable")

    def test_orchestrator_converts_raised_role_to_unavailable_report(self):
        candidate = StockCandidate(code="600519", name="贵州茅台")
        reports = {
            "quant": QuantReport(code=candidate.code, name=candidate.name),
            "fundamental": FundamentalReport(code=candidate.code, name=candidate.name),
            "news": NewsReport(code=candidate.code, name=candidate.name),
            "sentiment": SentimentReport(code=candidate.code, name=candidate.name),
        }
        for failing_role in reports:
            with self.subTest(role=failing_role):
                cio = _CIO()
                analysts = {
                    name: _RaisingAnalyst() if name == failing_role else _Analyst(report)
                    for name, report in reports.items()
                }
                orchestrator = ResearchOrchestrator(market_data=object(), cio=cio, **analysts)

                report = orchestrator.analyze([candidate], AnalysisContext(use_llm=False))

                self.assertEqual(report.summary, "fallback complete")
                received = dict(zip(("quant", "fundamental", "news", "sentiment"), cio.received))
                self.assertEqual(received[failing_role].status, "unavailable")

    def test_sentiment_accepts_market_data_records(self):
        analyst = SentimentAnalyst(_MarketData())

        report = analyst.analyze(StockCandidate(code="600519", name="贵州茅台"), AnalysisContext(use_llm=False))

        self.assertEqual(report.status, "ok", report.error)

    def test_orchestrator_uses_conservative_decision_when_cio_raises(self):
        candidate = StockCandidate(code="600519", name="贵州茅台")
        orchestrator = ResearchOrchestrator(
            market_data=object(),
            quant=_Analyst(QuantReport(code=candidate.code, name=candidate.name)),
            fundamental=_Analyst(FundamentalReport(code=candidate.code, name=candidate.name)),
            news=_Analyst(NewsReport(code=candidate.code, name=candidate.name)),
            sentiment=_Analyst(SentimentReport(code=candidate.code, name=candidate.name)),
            cio=_FailingCIO(),
        )

        report = orchestrator.analyze([candidate], AnalysisContext(use_llm=False))

        self.assertEqual(report.all_decisions[0].action, "avoid")
        self.assertIn("CIO analysis unavailable", report.all_decisions[0].risk_flags)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from src.agents.research.orchestrator import ResearchOrchestrator
from src.agents.research.schemas import (
    AnalysisContext,
    EventCard,
    FinalReport,
    FundamentalReport,
    NewsReport,
    QuantReport,
    SentimentReport,
    StockCandidate,
    StockDecision,
)
from src.agents.research.analysts.cio import CIOAgent
from src.agents.research.tool import DeepResearchTool
from src.agents.research.analysts.sentiment import SentimentAnalyst
from src.agents.research.analysts.news import NewsAnalyst
from src.agents.research.analysts.quant import QuantAnalyst


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


class _HistoryMarketData:
    def __init__(self, latest=date(2026, 7, 14)):
        self.latest = latest
        self.calls = []

    def history(self, code, **kwargs):
        self.calls.append({"code": code, **kwargs})
        dates = pd.date_range(end=self.latest, periods=40, freq="D")
        return pd.DataFrame({
            "date": dates,
            "close": [100.0 + index for index in range(40)],
            "volume": [1000.0] * 40,
        })


class _ModelSignal:
    def __init__(self, value=0.20):
        self.value = value
        self.calls = []

    def predict_return(self, close):
        self.calls.append(close.copy())
        return self.value


class _NewsMarketData:
    def stock_news(self, code):
        return [
            {"标题": "有效新闻", "内容": "经营稳定", "发布时间": "2026-07-14T17:00:00+08:00"},
            {"标题": "未来新闻", "内容": "未来事件", "发布时间": "2026-07-14T19:00:00+08:00"},
            {"标题": "无时间新闻", "内容": "时间缺失", "发布时间": ""},
            {"标题": "坏时间新闻", "内容": "时间错误", "发布时间": "not-a-time"},
        ]


class _CredentialNewsMarketData:
    def stock_news(self, code):
        return [{
            "标题": "凭据边界",
            "内容": (
                "Authorization: Bearer news-secret; token=token-secret; "
                "passwd=passwd-secret; api_key: colon-secret; Bearer bare-secret"
            ),
            "新闻链接": "https://user:password@news.example/item?api_key=query-secret&token=url-token",
            "发布时间": "2026-07-14T17:00:00+08:00",
        }]


class _RaisingCredentialNewsMarketData:
    def stock_news(self, code):
        raise RuntimeError(
            "Authorization: Bearer source-secret; token=source-token; "
            "passwd=source-passwd; api_key: source-colon; "
            "https://user:source-userinfo@news.example/item?token=source-query"
        )


class _RecordingStructuredLLM:
    model = "research-news-model"

    def __init__(self):
        self.payload = None

    def structured(self, **kwargs):
        self.payload = kwargs["user_payload"]
        item = self.payload["news"][0]
        return {"events": [{
            "event_type": "other",
            "sentiment": "neutral",
            "severity": "low",
            "summary": item["title"],
            "published_at": item["published_at"],
            "source": item["url"],
        }]}


class _FutureEventLLM(_RecordingStructuredLLM):
    def structured(self, **kwargs):
        self.payload = kwargs["user_payload"]
        return {"events": [{
            "event_type": "other",
            "sentiment": "positive",
            "severity": "high",
            "summary": "压缩模型生成的未来事件",
            "published_at": "2026-07-14T19:00:00+08:00",
            "source": "news.example",
        }]}


class _CapturingCIOLLM:
    model = "research-cio-model"

    def __init__(self):
        self.payload = None

    def structured(self, **kwargs):
        self.payload = kwargs["user_payload"]
        return {
            "action": "watch",
            "confidence": 0.5,
            "position_bias": "5%",
            "top_reasons": ["sanitized evidence", "bounded risk"],
            "risk_flags": [],
            "invalidation_conditions": ["refresh evidence"],
        }


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
    def test_analysis_context_defaults_preserve_existing_research_behavior(self):
        context = AnalysisContext()

        self.assertEqual(context.cutoff_at, "")
        self.assertTrue(context.include_model_signal)

    def test_quant_exact_as_of_disables_stale_fallback_and_excludes_model_signal(self):
        market = _HistoryMarketData()
        model = _ModelSignal()
        analyst = QuantAnalyst(akshare_tools=market, model_tool=model)

        report = analyst.analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(
                as_of="2026-07-14",
                history_days=250,
                include_model_signal=False,
            ),
        )

        self.assertEqual(market.calls, [{
            "code": "600519",
            "days": 250,
            "end_date": date(2026, 7, 14),
            "allow_stale_fallback": False,
        }])
        self.assertEqual(report.status, "ok", report.error)
        self.assertIsNone(report.model_expected_return)
        self.assertEqual(model.calls, [])
        self.assertNotIn("lstm", str(report.key_factors).lower())
        baseline = QuantAnalyst(
            akshare_tools=_HistoryMarketData(),
            model_tool=_ModelSignal(None),
        ).analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(as_of="2026-07-14", history_days=250),
        )
        self.assertEqual(report.quant_score, baseline.quant_score)
        self.assertEqual(report.trend, baseline.trend)

    def test_quant_rejects_history_whose_latest_date_is_not_as_of(self):
        analyst = QuantAnalyst(
            akshare_tools=_HistoryMarketData(latest=date(2026, 7, 13)),
            model_tool=_ModelSignal(),
        )

        report = analyst.analyze(
            StockCandidate(code="600519"),
            AnalysisContext(as_of="2026-07-14"),
        )

        self.assertEqual(report.status, "error")
        self.assertIn("latest date", report.error)

    def test_quant_default_context_still_includes_model_signal(self):
        market = _HistoryMarketData()
        model = _ModelSignal(0.02)
        analyst = QuantAnalyst(akshare_tools=market, model_tool=model)

        report = analyst.analyze(StockCandidate(code="600519"), AnalysisContext())

        self.assertEqual(market.calls, [{"code": "600519", "days": 160}])
        self.assertEqual(report.model_expected_return, 0.02)
        self.assertEqual(len(model.calls), 1)
        self.assertIn("lstm", str(report.key_factors).lower())

    def test_news_cutoff_filters_raw_items_before_llm_compression(self):
        llm = _RecordingStructuredLLM()
        analyst = NewsAnalyst(
            akshare_tools=_NewsMarketData(),
            llm_client=llm,
            tavily_api_key="disabled",
        )
        analyst.tavily_api_key = None

        report = analyst.analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(
                cutoff_at="2026-07-14T18:30:00+08:00",
                use_llm=True,
            ),
        )

        self.assertEqual(
            [item["title"] for item in llm.payload["news"]],
            ["有效新闻"],
        )
        self.assertEqual([event.summary for event in report.events], ["有效新闻"])
        self.assertIn("news_after_cutoff=1", report.error)
        self.assertIn("news_timestamp_blank=1", report.error)
        self.assertIn("news_timestamp_unparseable=1", report.error)

    def test_news_default_context_does_not_apply_evaluation_cutoff(self):
        analyst = NewsAnalyst(
            akshare_tools=_NewsMarketData(),
            tavily_api_key="disabled",
        )
        analyst.tavily_api_key = None

        report = analyst.analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(use_llm=False),
        )

        self.assertEqual(report.raw_count, 4)

    def test_news_llm_payload_redacts_credentials(self):
        llm = _RecordingStructuredLLM()
        analyst = NewsAnalyst(
            akshare_tools=_CredentialNewsMarketData(),
            llm_client=llm,
            tavily_api_key="disabled",
        )
        analyst.tavily_api_key = None

        analyst.analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(
                cutoff_at="2026-07-14T18:30:00+08:00",
                use_llm=True,
            ),
        )

        serialized = str(llm.payload).lower()
        for secret in (
            "news-secret",
            "token-secret",
            "passwd-secret",
            "colon-secret",
            "bare-secret",
            "query-secret",
            "url-token",
            "user:password",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("[redacted]", serialized)

    def test_news_source_errors_redact_sanitizer_bypass_strings(self):
        analyst = NewsAnalyst(
            akshare_tools=_RaisingCredentialNewsMarketData(),
            tavily_api_key="disabled",
        )
        analyst.tavily_api_key = None

        report = analyst.analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(use_llm=False),
        )

        serialized = str(report.error).lower()
        for secret in (
            "source-secret",
            "source-token",
            "source-passwd",
            "source-colon",
            "source-userinfo",
            "source-query",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("[redacted]", serialized)

    def test_news_rejects_future_event_returned_by_compression_llm(self):
        analyst = NewsAnalyst(
            akshare_tools=_NewsMarketData(),
            llm_client=_FutureEventLLM(),
            tavily_api_key="disabled",
        )
        analyst.tavily_api_key = None

        report = analyst.analyze(
            StockCandidate(code="600519", name="贵州茅台"),
            AnalysisContext(
                cutoff_at="2026-07-14T18:30:00+08:00",
                use_llm=True,
            ),
        )

        self.assertEqual(report.events, [])
        self.assertIn("news_after_cutoff", report.error)

    def test_cio_llm_payload_and_decision_snapshots_redact_credentials(self):
        llm = _CapturingCIOLLM()
        analyst = CIOAgent(openai_api_key="enabled", llm_client=llm)
        secret_text = (
            "Authorization: Bearer bearer-secret; "
            "client_secret=client-secret; "
            "openai_api_key=sk-openai-secret; "
            "token=token-secret; passwd=passwd-secret; api_key: colon-secret; "
            "Bearer bare-secret; "
            "https://user:userinfo-secret@cio.example/path?token=query-secret&api_key=api-secret"
        )

        decision = analyst.decide_one(
            QuantReport(
                code="600519",
                name="贵州茅台",
                status="error",
                error=f"quant failed {secret_text}",
            ),
            FundamentalReport(
                code="600519",
                name="贵州茅台",
                status="ok",
                key_factors=[f"factor {secret_text}"],
            ),
            NewsReport(
                code="600519",
                name="贵州茅台",
                status="ok",
                events=[
                    EventCard(
                        summary=f"event {secret_text}",
                        source="https://user:userinfo-secret@news.example/item?token=query-secret",
                    )
                ],
                error=f"news warning {secret_text}",
            ),
            SentimentReport(
                code="600519",
                name="贵州茅台",
                status="error",
                error=f"sentiment failed {secret_text}",
            ),
            use_llm=True,
        )

        serialized_payload = str(llm.payload).lower()
        serialized_decision = str({
            "quant": decision.quant,
            "fundamental": decision.fundamental,
            "news": decision.news,
            "sentiment": decision.sentiment,
        }).lower()
        for serialized in (serialized_payload, serialized_decision):
            for secret in (
                "bearer-secret",
                "client-secret",
                "sk-openai-secret",
                "token-secret",
                "passwd-secret",
                "colon-secret",
                "bare-secret",
                "userinfo-secret",
                "query-secret",
                "api-secret",
                "user:userinfo-secret",
            ):
                self.assertNotIn(secret, serialized)
            self.assertIn("[redacted]", serialized)
            self.assertIn("cio.example/path", serialized)

    def test_cio_rule_fallback_snapshots_redact_credentials(self):
        analyst = CIOAgent(openai_api_key="", llm_client=None)
        secret_text = (
            "Authorization: Bearer fallback-secret; token=fallback-token; "
            "passwd=fallback-passwd; api_key: fallback-colon; "
            "https://user:fallback-userinfo@cio.example/path?token=fallback-query"
        )

        decision = analyst.decide_one(
            QuantReport(
                code="600519",
                name="贵州茅台",
                status="error",
                error=f"quant failed {secret_text}",
            ),
            FundamentalReport(
                code="600519",
                name="贵州茅台",
                status="ok",
                key_factors=[f"factor {secret_text}"],
            ),
            NewsReport(
                code="600519",
                name="贵州茅台",
                status="ok",
                events=[EventCard(summary=f"event {secret_text}")],
            ),
            SentimentReport(
                code="600519",
                name="贵州茅台",
                status="error",
                error=f"sentiment failed {secret_text}",
            ),
            use_llm=False,
        )

        serialized = str({
            "quant": decision.quant,
            "fundamental": decision.fundamental,
            "news": decision.news,
            "sentiment": decision.sentiment,
        }).lower()
        for secret in (
            "fallback-secret",
            "fallback-token",
            "fallback-passwd",
            "fallback-colon",
            "fallback-userinfo",
            "fallback-query",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("[redacted]", serialized)

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

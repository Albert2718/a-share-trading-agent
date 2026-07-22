from __future__ import annotations

from typing import Iterable, List

from src.core import DataAccessLayer
from src.tools.market_data import AkshareMarketData

from .analysts import CIOAgent, FundamentalAnalyst, NewsAnalyst, QuantAnalyst, SentimentAnalyst
from .schemas import (
    AnalysisContext,
    FinalReport,
    FundamentalReport,
    NewsReport,
    QuantReport,
    SentimentReport,
    StockCandidate,
    StockDecision,
)


class ResearchOrchestrator:
    def __init__(
        self,
        data_access: DataAccessLayer | None = None,
        market_data: AkshareMarketData | None = None,
        quant=None,
        fundamental=None,
        news=None,
        sentiment=None,
        cio=None,
    ):
        self.data_access = data_access or DataAccessLayer()
        self.market_data = market_data or AkshareMarketData(self.data_access)
        self.quant = quant or QuantAnalyst(self.market_data)
        self.fundamental = fundamental or FundamentalAnalyst(self.market_data)
        self.news = news or NewsAnalyst(self.data_access, self.market_data)
        self.sentiment = sentiment or SentimentAnalyst(self.market_data)
        self.cio = cio or CIOAgent()

    def candidates_from_codes(self, codes: Iterable[str]) -> List[StockCandidate]:
        rows = self.market_data.candidates_from_codes(list(codes))
        return [StockCandidate(code=row["code"], name=row.get("name", "")) for row in rows]

    def hot_candidates(self, top: int) -> List[StockCandidate]:
        rows = self.market_data.hot_candidates(top=top)
        return [StockCandidate(code=row["code"], name=row.get("name", "")) for row in rows]

    def analyze(
        self,
        candidates: List[StockCandidate],
        context: AnalysisContext,
        mode: str = "single",
        include_fundamental: bool = True,
        include_news: bool = True,
        include_sentiment: bool = True,
    ) -> FinalReport:
        decisions = []
        for candidate in candidates:
            quant_report = self._safe_analyze(
                self.quant,
                candidate,
                context,
                QuantReport,
                "quant analysis failed",
            )
            fundamental_report = (
                self._safe_analyze(
                    self.fundamental,
                    candidate,
                    context,
                    FundamentalReport,
                    "fundamental analysis failed",
                )
                if include_fundamental
                else FundamentalReport(code=candidate.code, name=candidate.name, status="unavailable", error="skipped by caller")
            )
            news_report = (
                self._safe_analyze(
                    self.news,
                    candidate,
                    context,
                    NewsReport,
                    "news analysis failed",
                )
                if include_news
                else NewsReport(code=candidate.code, name=candidate.name, status="unavailable", error="skipped by caller")
            )
            sentiment_report = (
                self._safe_analyze(
                    self.sentiment,
                    candidate,
                    context,
                    SentimentReport,
                    "sentiment analysis failed",
                )
                if include_sentiment
                else SentimentReport(code=candidate.code, name=candidate.name, status="unavailable", error="skipped by caller")
            )
            try:
                decision = self.cio.decide_one(
                    quant_report,
                    fundamental_report,
                    news_report,
                    sentiment_report,
                    risk_profile=context.risk_profile,
                    use_llm=context.use_llm,
                    personal_context=context.personal_context,
                )
            except Exception:
                decision = StockDecision(
                    code=candidate.code,
                    name=candidate.name,
                    action="avoid",
                    confidence=0.0,
                    rank_score=0,
                    position_bias="0%",
                    reason="CIO analysis unavailable",
                    risk_flags=["CIO analysis unavailable"],
                )
            decisions.append(decision)
        return self.cio.build_report(decisions, mode=mode)

    @staticmethod
    def _safe_analyze(analyst, candidate, context, report_type, error: str):
        try:
            return analyst.analyze(candidate, context)
        except Exception:
            return report_type(
                code=candidate.code,
                name=candidate.name,
                status="unavailable",
                error=error,
            )

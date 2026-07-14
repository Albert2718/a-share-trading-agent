from __future__ import annotations

from typing import Iterable, List

from .agents import CIOAgent, FundamentalAnalyst, NewsAnalyst, QuantAnalyst, SentimentAnalyst
from .schemas import AnalysisContext, FinalReport, StockCandidate
from .tools import AkshareTools
from src.core import DataAccessLayer


class TradingAgentOrchestrator:
    def __init__(self, data_access: DataAccessLayer | None = None):
        self.data_access = data_access or DataAccessLayer()
        self.akshare_tools = AkshareTools(self.data_access)
        self.quant = QuantAnalyst(self.akshare_tools)
        self.fundamental = FundamentalAnalyst(self.akshare_tools)
        self.news = NewsAnalyst(self.data_access, self.akshare_tools)
        self.sentiment = SentimentAnalyst(self.akshare_tools)
        self.cio = CIOAgent()

    def candidates_from_codes(self, codes: Iterable[str]) -> List[StockCandidate]:
        return self.akshare_tools.candidates_from_codes(list(codes))

    def hot_candidates(self, top: int) -> List[StockCandidate]:
        return self.akshare_tools.hot_candidates(top=top)

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
            quant_report = self.quant.analyze(candidate, context)
            fundamental_report = (
                self.fundamental.analyze(candidate, context)
                if include_fundamental
                else self._fundamental_unavailable(candidate, "skipped by CLI")
            )
            news_report = (
                self.news.analyze(candidate, context)
                if include_news
                else self._news_unavailable(candidate, "skipped by CLI")
            )
            sentiment_report = (
                self.sentiment.analyze(candidate, context)
                if include_sentiment
                else self._sentiment_unavailable(candidate, "skipped by CLI")
            )
            decisions.append(
                self.cio.decide_one(
                    quant_report,
                    fundamental_report,
                    news_report,
                    sentiment_report,
                    risk_profile=context.risk_profile,
                    use_llm=context.use_llm,
                )
            )
        return self.cio.build_report(decisions, mode=mode)

    def _fundamental_unavailable(self, candidate: StockCandidate, reason: str):
        from .schemas import FundamentalReport

        return FundamentalReport(code=candidate.code, name=candidate.name, status="unavailable", error=reason)

    def _news_unavailable(self, candidate: StockCandidate, reason: str):
        from .schemas import NewsReport

        return NewsReport(code=candidate.code, name=candidate.name, status="unavailable", error=reason)

    def _sentiment_unavailable(self, candidate: StockCandidate, reason: str):
        from .schemas import SentimentReport

        return SentimentReport(code=candidate.code, name=candidate.name, status="unavailable", error=reason)

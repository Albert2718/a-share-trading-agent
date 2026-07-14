from __future__ import annotations

from typing import Any, Dict, List

from ..schemas import AnalysisContext, DiscussionEvent, SentimentReport, StockCandidate
from src.tools.market_data import AkshareMarketData
from src.tools.utils import clamp, normalize_a_share_code, safe_float


POSITIVE_TERMS = ["看多", "抄底", "增持", "突破", "涨停", "业绩好", "利好"]
NEGATIVE_TERMS = ["看空", "割肉", "减持", "暴雷", "亏损", "退市", "利空", "监管"]


class SentimentAnalyst:
    def __init__(self, akshare_tools: AkshareMarketData | None = None):
        self.akshare_tools = akshare_tools or AkshareMarketData()

    def analyze(self, candidate: StockCandidate, context: AnalysisContext) -> SentimentReport:
        try:
            vote_rows = self._safe_rows(self.akshare_tools.baidu_vote, candidate.code)
            hot_candidates = self._safe_hot()
            return self._build_report(candidate, vote_rows, hot_candidates)
        except Exception as exc:
            return SentimentReport(code=candidate.code, name=candidate.name, status="error", error=str(exc))

    def _safe_rows(self, func, *args) -> List[Dict[str, Any]]:
        try:
            return func(*args) or []
        except Exception:
            return []

    def _safe_hot(self) -> List[Dict[str, str]]:
        try:
            return self.akshare_tools.hot_candidates(top=100)
        except Exception:
            return []

    def _build_report(
        self,
        candidate: StockCandidate,
        vote_rows: List[Dict[str, Any]],
        hot_candidates: List[Dict[str, str]],
    ) -> SentimentReport:
        norm = normalize_a_share_code(candidate.code)
        hot_rank = next(
            (
                idx + 1
                for idx, item in enumerate(hot_candidates)
                if normalize_a_share_code(item.get("code", "")) == norm
            ),
            None,
        )
        attention_score = 0
        heat_sources = []
        if hot_rank is not None:
            attention_score = int(round(clamp(100 - hot_rank, 0, 100)))
            heat_sources.append(f"eastmoney hot rank #{hot_rank}")

        vote_score = self._vote_score(vote_rows)
        score = int(round(clamp(vote_score, -100, 100)))
        crowding_risk = "high" if attention_score >= 80 and score >= 30 else "medium" if attention_score >= 60 else "low"
        events = []
        if vote_rows:
            sentiment = "positive" if score > 20 else "negative" if score < -20 else "neutral"
            events.append(
                DiscussionEvent(
                    topic="retail voting",
                    sentiment=sentiment,
                    heat="high" if attention_score >= 70 else "medium",
                    summary=f"Baidu vote-derived sentiment score {score}",
                    source="baidu_vote",
                )
            )
        if not events and hot_rank is not None:
            events.append(
                DiscussionEvent(
                    topic="attention",
                    sentiment="neutral",
                    heat="high" if attention_score >= 70 else "medium",
                    summary=f"Stock appears in hot ranking at #{hot_rank}",
                    source="eastmoney_hot_rank",
                )
            )

        status = "ok" if vote_rows or hot_rank is not None else "unavailable"
        error = None if status == "ok" else "sentiment sources unavailable"
        return SentimentReport(
            code=candidate.code,
            name=candidate.name,
            status=status,
            sentiment_score=score,
            attention_score=attention_score,
            crowding_risk=crowding_risk,
            dominant_emotions=self._emotions(score, attention_score),
            discussion_events=events[:5],
            heat_sources=heat_sources,
            error=error,
        )

    def _vote_score(self, rows: List[Dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        row = rows[-1]
        bullish = self._first_number(row, ["看涨", "看涨比例", "看多", "up"])
        bearish = self._first_number(row, ["看跌", "看跌比例", "看空", "down"])
        if bullish is None or bearish is None:
            text = " ".join(str(value) for value in row.values())
            pos_hits = sum(1 for term in POSITIVE_TERMS if term in text)
            neg_hits = sum(1 for term in NEGATIVE_TERMS if term in text)
            return (pos_hits - neg_hits) * 20
        total = bullish + bearish
        if total <= 0:
            return 0.0
        return (bullish - bearish) / total * 100

    def _first_number(self, row: Dict[str, Any], keys: List[str]):
        for key in keys:
            if key in row:
                value = safe_float(row.get(key))
                if value is not None:
                    return value
        return None

    def _emotions(self, sentiment_score: int, attention_score: int) -> List[str]:
        emotions = []
        if sentiment_score > 30:
            emotions.append("optimistic")
        elif sentiment_score < -30:
            emotions.append("pessimistic")
        else:
            emotions.append("divided")
        if attention_score >= 80:
            emotions.append("crowded")
        return emotions

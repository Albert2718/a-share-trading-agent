from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from ..prompts import NEWS_ANALYST_SYSTEM
from ..schemas import AnalysisContext, EventCard, NewsReport, StockCandidate
from src.core import DataAccessLayer, LLMClient, load_config
from src.tools.market_data import AkshareMarketData
from src.tools.news_search import NewsSearchTool
from src.tools.utils import dedupe_keep_order


POSITIVE_TERMS = ["增持", "中标", "回购", "盈利增长", "业绩增长", "上调评级", "突破", "合作", "并购"]
NEGATIVE_TERMS = ["减持", "亏损", "处罚", "立案", "监管", "诉讼", "暴雷", "下滑", "风险", "退市", "问询"]
HIGH_SEVERITY_TERMS = ["立案", "处罚", "退市", "重大诉讼", "业绩预亏", "暴雷", "监管"]
CRITICAL_SEVERITY_TERMS = ["证监会立案", "立案调查", "财务造假", "退市风险", "暂停上市", "重大违法"]

class NewsAnalyst:
    def __init__(
        self,
        data_access: DataAccessLayer | None = None,
        akshare_tools: AkshareMarketData | None = None,
        news_search: NewsSearchTool | None = None,
        llm_client: LLMClient | None = None,
        tavily_api_key: Optional[str] = None,
        max_results: int = 8,
        max_event_cards: int = 5,
        timeout: int = 20,
    ):
        config = load_config()
        self.data_access = data_access or DataAccessLayer()
        self.akshare_tools = akshare_tools or AkshareMarketData(self.data_access)
        self.tavily_api_key = tavily_api_key or config.tavily_api_key
        self.news_agent_model = config.news_agent_model
        self.max_results = max_results
        self.max_event_cards = max_event_cards
        self.timeout = timeout
        self.news_search = news_search or NewsSearchTool(
            self.data_access,
            api_key=self.tavily_api_key,
            max_results=max_results,
            timeout=timeout,
        )
        self.llm_client = llm_client

    def analyze(self, candidate: StockCandidate, context: AnalysisContext) -> NewsReport:
        try:
            raw_items = []
            source_errors = []
            try:
                raw_items.extend(self._akshare_news(candidate))
            except Exception as exc:
                source_errors.append(f"akshare: {self._sanitize_text(str(exc))}")
            if self.tavily_api_key:
                try:
                    raw_items.extend(self._tavily_search(candidate))
                except Exception as exc:
                    source_errors.append(f"tavily: {self._sanitize_text(str(exc))}")
            raw_items, cutoff_warnings = self._filter_by_cutoff(
                raw_items,
                context.cutoff_at,
            )
            source_errors.extend(cutoff_warnings)
            events = self._compress_to_events(candidate, raw_items, use_llm=context.use_llm)
            events, event_warnings = self._filter_events_by_cutoff(
                events,
                context.cutoff_at,
            )
            source_errors.extend(event_warnings)
            score = self._score_events(events)
            sentiment = "positive" if score > 20 else "negative" if score < -20 else "neutral"
            confidence = "high" if len(events) >= 3 else "medium" if events else "low"
            status = "ok" if raw_items else "unavailable"
            error = "; ".join(source_errors) if source_errors else None
            if status != "ok" and not error:
                error = "news sources unavailable"
            return NewsReport(
                code=candidate.code,
                name=candidate.name,
                status=status,
                news_score=score,
                sentiment=sentiment,
                confidence=confidence,
                events=events,
                raw_count=len(raw_items),
                compressed_count=len(events),
                error=error,
            )
        except Exception as exc:
            return NewsReport(code=candidate.code, name=candidate.name, status="error", error=str(exc))

    def _filter_by_cutoff(
        self,
        raw_items: List[Dict],
        cutoff_at: str,
    ) -> tuple[List[Dict], List[str]]:
        if not cutoff_at:
            return raw_items, []
        cutoff = self._parse_timestamp(cutoff_at)
        if cutoff is None:
            raise ValueError("cutoff_at must be an ISO datetime with timezone")

        accepted = []
        counts = {
            "news_after_cutoff": 0,
            "news_timestamp_blank": 0,
            "news_timestamp_unparseable": 0,
        }
        for item in raw_items:
            raw_timestamp = item.get("published_date") or item.get("published_at")
            if raw_timestamp is None or not str(raw_timestamp).strip():
                counts["news_timestamp_blank"] += 1
                continue
            timestamp = self._parse_timestamp(str(raw_timestamp))
            if timestamp is None:
                counts["news_timestamp_unparseable"] += 1
                continue
            if timestamp > cutoff:
                counts["news_after_cutoff"] += 1
                continue
            accepted.append(item)
        warnings = [f"{name}={count}" for name, count in counts.items() if count]
        return accepted, warnings

    def _filter_events_by_cutoff(
        self,
        events: List[EventCard],
        cutoff_at: str,
    ) -> tuple[List[EventCard], List[str]]:
        if not cutoff_at:
            return events, []
        cutoff = self._parse_timestamp(cutoff_at)
        if cutoff is None:
            raise ValueError("cutoff_at must be an ISO datetime with timezone")
        accepted = []
        blank = unparseable = future = 0
        for event in events:
            if not event.published_at.strip():
                blank += 1
                continue
            timestamp = self._parse_timestamp(event.published_at)
            if timestamp is None:
                unparseable += 1
                continue
            if timestamp > cutoff:
                future += 1
                continue
            accepted.append(event)
        warnings = []
        if future:
            warnings.append(f"news_after_cutoff={future}")
        if blank:
            warnings.append(f"news_timestamp_blank={blank}")
        if unparseable:
            warnings.append(f"news_timestamp_unparseable={unparseable}")
        return accepted, warnings

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None

    def _akshare_news(self, candidate: StockCandidate) -> List[Dict]:
        rows = self.akshare_tools.stock_news(candidate.code)
        items = []
        for row in rows[: self.max_results]:
            title = self._value(row, ["新闻标题", "标题", "title"])
            content = self._value(row, ["新闻内容", "内容", "摘要", "content"]) or title
            url = self._value(row, ["新闻链接", "链接", "url"])
            published_at = self._value(row, ["发布时间", "日期", "published_at"])
            if title or content:
                items.append(
                    {
                        "title": str(title or ""),
                        "content": str(content or ""),
                        "url": str(url or "akshare_stock_news"),
                        "published_at": str(published_at or ""),
                    }
                )
        return items

    def _tavily_search(self, candidate: StockCandidate) -> List[Dict]:
        return self.news_search.search(candidate.code, candidate.name)

    def _compress_to_events(
        self,
        candidate: StockCandidate,
        raw_items: List[Dict],
        use_llm: bool,
    ) -> List[EventCard]:
        compact_items = []
        seen_keys = set()
        for item in raw_items:
            title = self._sanitize_text(str(item.get("title") or "").strip())
            content = self._sanitize_text(str(item.get("content") or "").strip())
            url = self._sanitize_url(str(item.get("url") or "").strip())
            published_at = str(item.get("published_date") or item.get("published_at") or "").strip()
            text = self._trim_text(f"{title}. {content}", limit=1200)
            dedupe_key = re.sub(r"\W+", "", title.lower())[:80] or url
            if not text or dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            compact_items.append({"title": title, "text": text, "url": url, "published_at": published_at})

        if use_llm:
            llm_events = self._try_llm_compress(candidate, compact_items)
            if llm_events is not None:
                return llm_events[: self.max_event_cards]

        events = [self._heuristic_event(item) for item in compact_items]
        events = [event for event in events if event.summary]
        events.sort(key=self._event_priority, reverse=True)
        return events[: self.max_event_cards]

    def _try_llm_compress(self, candidate: StockCandidate, compact_items: List[Dict]) -> Optional[List[EventCard]]:
        if not compact_items:
            return None
        schema = {
            "name": "news_events",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "events": {
                        "type": "array",
                        "maxItems": self.max_event_cards,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "event_type": {"type": "string"},
                                "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                                "summary": {"type": "string"},
                                "published_at": {"type": "string"},
                                "source": {"type": "string"},
                            },
                            "required": ["event_type", "sentiment", "severity", "summary", "published_at", "source"],
                        },
                    },
                },
                "required": ["events"],
            },
        }
        try:
            llm = self.llm_client or LLMClient(model=self.news_agent_model)
            payload = llm.structured(
                system_prompt=NEWS_ANALYST_SYSTEM,
                user_payload={"stock": {"code": candidate.code, "name": candidate.name}, "news": compact_items},
                schema=schema,
                max_tokens=900,
            )
        except Exception:
            payload = None
        if payload is None:
            return None
        return [
            EventCard(
                event_type=str(item.get("event_type", "other")),
                sentiment=str(item.get("sentiment", "neutral")),
                severity=str(item.get("severity", "low")),
                summary=self._trim_text(str(item.get("summary", "")), 140),
                published_at=str(item.get("published_at", "")),
                source=str(item.get("source", "")),
            )
            for item in payload.get("events", [])
            if item.get("summary")
        ]

    def _heuristic_event(self, item: Dict) -> EventCard:
        text = item["text"]
        pos_hits = [term for term in POSITIVE_TERMS if term in text]
        neg_hits = [term for term in NEGATIVE_TERMS if term in text]
        sentiment = "positive" if len(pos_hits) > len(neg_hits) else "negative" if neg_hits else "neutral"
        if any(term in text for term in CRITICAL_SEVERITY_TERMS):
            severity = "critical"
        elif any(term in text for term in HIGH_SEVERITY_TERMS):
            severity = "high"
        else:
            severity = "medium" if pos_hits or neg_hits else "low"
        keywords = dedupe_keep_order(pos_hits + neg_hits)[:3]
        prefix = f"{' / '.join(keywords)}: " if keywords else ""
        summary = self._trim_text(prefix + (item.get("title") or text), 120)
        return EventCard(
            event_type=self._event_type(text),
            sentiment=sentiment,
            severity=severity,
            summary=summary,
            published_at=item.get("published_at", ""),
            source=item.get("url", ""),
        )

    def _score_events(self, events: List[EventCard]) -> int:
        total = 0
        for event in events:
            base = 50 if event.severity == "critical" else 35 if event.severity == "high" else 20 if event.severity == "medium" else 8
            if event.sentiment == "positive":
                total += base
            elif event.sentiment == "negative":
                total -= base
        return int(max(-100, min(100, total)))

    def _event_priority(self, event: EventCard) -> int:
        severity = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(event.severity, 1)
        sentiment = 2 if event.sentiment != "neutral" else 0
        return severity * 10 + sentiment

    def _event_type(self, text: str) -> str:
        mapping = {
            "earnings": ["业绩", "盈利", "亏损", "预告", "财报"],
            "regulation": ["监管", "处罚", "问询", "立案"],
            "litigation": ["诉讼", "仲裁"],
            "reduction": ["减持"],
            "contract": ["中标", "合同", "订单"],
            "policy": ["政策", "行业", "税"],
            "rumor": ["传闻", "消息称"],
        }
        for event_type, terms in mapping.items():
            if any(term in text for term in terms):
                return event_type
        return "other"

    def _trim_text(self, text: str, limit: int) -> str:
        return re.sub(r"\s+", " ", text).strip()[:limit]

    @staticmethod
    def _sanitize_text(value: str) -> str:
        text = re.sub(
            r"authorization\s*:\s*(?:bearer|basic)\s+[^\s;]+",
            "Authorization: [REDACTED]",
            value,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b((?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|password|secret))\s*=\s*[^\s&;]+",
            lambda match: f"{match.group(1)}=[REDACTED]",
            text,
            flags=re.IGNORECASE,
        )
        return re.sub(
            r"https?://[^\s;]+",
            lambda match: NewsAnalyst._sanitize_url(match.group(0)),
            text,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _sanitize_url(value: str) -> str:
        if not value:
            return ""
        try:
            parsed = urlsplit(value)
        except ValueError:
            return "[REDACTED_URL]"
        if not parsed.hostname:
            return NewsAnalyst._sanitize_text(value)
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))

    def _value(self, row: Dict, names: List[str]):
        for name in names:
            if name in row and row[name] not in (None, ""):
                return row[name]
        return None

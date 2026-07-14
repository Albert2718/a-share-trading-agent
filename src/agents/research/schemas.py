from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StockCandidate:
    code: str
    name: str = ""
    market: str = "A"


@dataclass
class AnalysisContext:
    depth: str = "standard"
    risk_profile: str = "balanced"
    use_llm: bool = True
    as_of: str = ""
    cutoff_at: str = ""
    include_model_signal: bool = True
    cache_policy: str = "default"
    history_days: int = 160


@dataclass
class QuantReport:
    code: str
    name: str = ""
    status: str = "ok"
    quant_score: int = 50
    trend: str = "neutral"
    model_expected_return: Optional[float] = None
    latest_close: Optional[float] = None
    return_5d: Optional[float] = None
    return_20d: Optional[float] = None
    volatility_20d: Optional[float] = None
    volume_ratio: Optional[float] = None
    rsi_14: Optional[float] = None
    macd_hist: Optional[float] = None
    key_factors: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class FundamentalReport:
    code: str
    name: str = ""
    status: str = "ok"
    fundamental_score: int = 50
    valuation_level: str = "unknown"
    profitability_level: str = "unknown"
    growth_level: str = "unknown"
    leverage_risk: str = "unknown"
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    peg: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_profit_growth: Optional[float] = None
    debt_ratio: Optional[float] = None
    key_factors: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class EventCard:
    event_type: str = "other"
    sentiment: str = "neutral"
    severity: str = "low"
    summary: str = ""
    published_at: str = ""
    source: str = ""


@dataclass
class NewsReport:
    code: str
    name: str = ""
    status: str = "ok"
    news_score: int = 0
    sentiment: str = "neutral"
    confidence: str = "low"
    events: List[EventCard] = field(default_factory=list)
    raw_count: int = 0
    compressed_count: int = 0
    error: Optional[str] = None


@dataclass
class DiscussionEvent:
    topic: str = ""
    sentiment: str = "neutral"
    heat: str = "low"
    summary: str = ""
    source: str = ""


@dataclass
class SentimentReport:
    code: str
    name: str = ""
    status: str = "ok"
    sentiment_score: int = 0
    attention_score: int = 0
    crowding_risk: str = "low"
    dominant_emotions: List[str] = field(default_factory=list)
    discussion_events: List[DiscussionEvent] = field(default_factory=list)
    heat_sources: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class StockDecision:
    code: str
    name: str = ""
    action: str = "watch"
    confidence: float = 0.0
    rank_score: int = 50
    position_bias: str = "0%"
    reason: str = ""
    top_reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    invalidation_conditions: List[str] = field(default_factory=list)
    quant: Dict[str, Any] = field(default_factory=dict)
    fundamental: Dict[str, Any] = field(default_factory=dict)
    news: Dict[str, Any] = field(default_factory=dict)
    sentiment: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalReport:
    generated_at: str
    mode: str
    top_picks: List[StockDecision] = field(default_factory=list)
    avoid_list: List[StockDecision] = field(default_factory=list)
    all_decisions: List[StockDecision] = field(default_factory=list)
    summary: str = ""


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value

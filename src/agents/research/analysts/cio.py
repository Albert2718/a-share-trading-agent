from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from ..prompts import CIO_AGENT_SYSTEM
from ..schemas import (
    FinalReport,
    FundamentalReport,
    NewsReport,
    QuantReport,
    SentimentReport,
    StockDecision,
    to_dict,
)
from ..utils import now_display, redact_recursive
from src.core import LLMClient, load_config
from src.tools.utils import clamp


class CIOAgent:
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_client: LLMClient | None = None,
    ):
        config = load_config()
        self.openai_api_key = openai_api_key or config.openai_api_key
        self.model = model or config.news_agent_model
        self.llm_client = llm_client

    def decide_one(
        self,
        quant: QuantReport,
        fundamental: FundamentalReport,
        news: NewsReport,
        sentiment: SentimentReport,
        risk_profile: str = "balanced",
        use_llm: bool = True,
    ) -> StockDecision:
        rule_decision = self._rule_decide(quant, fundamental, news, sentiment, risk_profile)
        if not use_llm or not self.openai_api_key:
            return rule_decision
        llm_decision = self._try_llm_decide(quant, fundamental, news, sentiment, risk_profile, rule_decision)
        if llm_decision is None:
            return rule_decision
        return self._enforce_hard_rules(llm_decision, news, fundamental, quant, sentiment)

    def _rule_decide(
        self,
        quant: QuantReport,
        fundamental: FundamentalReport,
        news: NewsReport,
        sentiment: SentimentReport,
        risk_profile: str,
    ) -> StockDecision:
        score = 0.45 * quant.quant_score + 0.30 * fundamental.fundamental_score
        score += 0.15 * (50 + news.news_score / 2)
        score += 0.10 * (50 + sentiment.sentiment_score / 2)

        reasons = []
        risks = []
        invalidations = []

        if quant.status == "ok":
            reasons.append(f"Quant {quant.quant_score}/100, trend={quant.trend}")
            reasons.extend(quant.key_factors[:2])
            risks.extend(quant.risk_flags[:3])
        else:
            score -= 10
            risks.append(f"quant unavailable: {quant.error or quant.status}")

        if fundamental.status == "ok":
            reasons.append(f"Fundamental {fundamental.fundamental_score}/100")
            reasons.extend(fundamental.key_factors[:2])
            risks.extend(fundamental.risk_flags[:3])
        else:
            score -= 8
            risks.append(f"fundamental unavailable: {fundamental.error or fundamental.status}")

        if news.status == "ok":
            reasons.append(f"News {news.news_score:+d}, sentiment={news.sentiment}")
            reasons.extend(event.summary for event in news.events[:2])
        else:
            score -= 5
            risks.append(f"news unavailable: {news.error or news.status}")

        if sentiment.status == "ok":
            reasons.append(f"Sentiment {sentiment.sentiment_score:+d}, attention={sentiment.attention_score}")
            if sentiment.crowding_risk == "high":
                score -= 8
                risks.append("high retail crowding risk")
        else:
            score -= 3
            risks.append(f"sentiment unavailable: {sentiment.error or sentiment.status}")

        severe_negative = self._severe_negative_events(news)
        hard_fundamental_risk = self._hard_fundamental_risk(fundamental)
        if severe_negative:
            score = min(score, 42)
            risks.append("high/critical negative news overrides bullish signals")
            invalidations.append("wait until the negative event is clarified")
        if hard_fundamental_risk:
            score = min(score, 55)
            invalidations.append("fundamental risk must improve before upgrading")

        score += self._risk_adjustment(risk_profile)
        rank_score = int(round(clamp(score, 0, 100)))
        action = self._action(rank_score, severe_negative, hard_fundamental_risk)
        confidence = self._confidence(rank_score, quant, fundamental, news, sentiment, severe_negative)
        position_bias = self._position_bias(action, rank_score, risk_profile)

        if not invalidations:
            invalidations = [
                "downgrade if high-severity negative news appears",
                "downgrade if price breaks recent trend support with high volume",
            ]

        return StockDecision(
            code=quant.code,
            name=quant.name,
            action=action,
            confidence=confidence,
            rank_score=rank_score,
            position_bias=position_bias,
            reason=redact_recursive("; ".join(reasons[:8])),
            top_reasons=redact_recursive(reasons[:6]),
            risk_flags=redact_recursive(risks[:8]),
            invalidation_conditions=redact_recursive(invalidations[:4]),
            quant=redact_recursive(asdict(quant)),
            fundamental=redact_recursive(asdict(fundamental)),
            news=redact_recursive(asdict(news)),
            sentiment=redact_recursive(asdict(sentiment)),
        )

    def _try_llm_decide(
        self,
        quant: QuantReport,
        fundamental: FundamentalReport,
        news: NewsReport,
        sentiment: SentimentReport,
        risk_profile: str,
        rule_decision: StockDecision,
    ) -> Optional[StockDecision]:
        try:
            schema = {
                "name": "cio_decision",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string", "enum": ["buy", "watch", "avoid"]},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "position_bias": {"type": "string"},
                        "top_reasons": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
                        "risk_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
                        "invalidation_conditions": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                    },
                    "required": [
                        "action",
                        "confidence",
                        "position_bias",
                        "top_reasons",
                        "risk_flags",
                        "invalidation_conditions",
                    ],
                },
            }
            payload = redact_recursive({
                "risk_profile": risk_profile,
                "reports": {
                    "quant": to_dict(quant),
                    "fundamental": to_dict(fundamental),
                    "news": to_dict(news),
                    "sentiment": to_dict(sentiment),
                },
                "rule_baseline": to_dict(rule_decision),
                "instruction": "Use the four reports to make the final CIO decision. Do not invent facts not present in the reports.",
            })
            llm = self.llm_client or LLMClient(model=self.model)
            data = llm.structured(
                system_prompt=CIO_AGENT_SYSTEM,
                user_payload=payload,
                schema=schema,
                temperature=0,
                max_tokens=800,
            )
            if data is None:
                return None
            rank_score = self._score_from_action(data.get("action", rule_decision.action), data.get("confidence", rule_decision.confidence))
            return StockDecision(
                code=quant.code,
                name=quant.name,
                action=str(data.get("action", rule_decision.action)),
                confidence=float(clamp(float(data.get("confidence", rule_decision.confidence)), 0.0, 1.0)),
                rank_score=rank_score,
                position_bias=str(data.get("position_bias", rule_decision.position_bias)),
                reason="; ".join(data.get("top_reasons", [])),
                top_reasons=[str(item) for item in data.get("top_reasons", [])][:3],
                risk_flags=[str(item) for item in data.get("risk_flags", [])][:5],
                invalidation_conditions=[str(item) for item in data.get("invalidation_conditions", [])][:4],
                quant=redact_recursive(asdict(quant)),
                fundamental=redact_recursive(asdict(fundamental)),
                news=redact_recursive(asdict(news)),
                sentiment=redact_recursive(asdict(sentiment)),
            )
        except Exception:
            return None

    def _enforce_hard_rules(
        self,
        decision: StockDecision,
        news: NewsReport,
        fundamental: FundamentalReport,
        quant: QuantReport,
        sentiment: SentimentReport,
    ) -> StockDecision:
        severe_negative = self._severe_negative_events(news)
        if severe_negative and decision.action == "buy":
            decision.action = "avoid" if any(event.severity == "critical" for event in severe_negative) else "watch"
            decision.position_bias = "0%" if decision.action == "avoid" else "5%"
            decision.rank_score = min(decision.rank_score, 42)
            decision.risk_flags.append("hard override: high/critical negative news")
        if self._hard_fundamental_risk(fundamental) and decision.action == "buy":
            decision.action = "watch"
            decision.position_bias = "5%"
            decision.rank_score = min(decision.rank_score, 55)
            decision.risk_flags.append("hard override: fundamental risk")
        if quant.status != "ok" and decision.action == "buy":
            decision.action = "watch"
            decision.position_bias = "5%"
            decision.rank_score = min(decision.rank_score, 60)
            decision.confidence = min(decision.confidence, 0.45)
            decision.risk_flags.append(f"hard override: quant unavailable ({quant.error or quant.status})")
        return decision

    def build_report(self, decisions: List[StockDecision], mode: str) -> FinalReport:
        ordered = sorted(decisions, key=lambda item: item.rank_score, reverse=True)
        top_picks = [item for item in ordered if item.action in {"buy", "watch"}][:5]
        avoid_list = [item for item in ordered if item.action == "avoid"]
        return FinalReport(
            generated_at=now_display(),
            mode=mode,
            top_picks=top_picks,
            avoid_list=avoid_list,
            all_decisions=ordered,
            summary=self._summary(ordered),
        )

    def _severe_negative_events(self, news: NewsReport) -> List:
        return [
            event
            for event in news.events
            if event.sentiment == "negative" and event.severity in {"high", "critical"}
        ]

    def _hard_fundamental_risk(self, fundamental: FundamentalReport) -> bool:
        return any(
            "negative PE" in flag or "high debt" in flag or "net profit decline" in flag
            for flag in fundamental.risk_flags
        )

    def _risk_adjustment(self, risk_profile: str) -> float:
        return {"conservative": -5.0, "balanced": 0.0, "aggressive": 5.0}.get(risk_profile, 0.0)

    def _action(self, score: int, severe_negative: List, hard_fundamental_risk: bool) -> str:
        if severe_negative or score < 45:
            return "avoid"
        if score >= 70 and not hard_fundamental_risk:
            return "buy"
        return "watch"

    def _confidence(
        self,
        score: int,
        quant: QuantReport,
        fundamental: FundamentalReport,
        news: NewsReport,
        sentiment: SentimentReport,
        severe_negative: List,
    ) -> float:
        if severe_negative:
            return 0.9
        ok_count = sum(report.status == "ok" for report in [quant, fundamental, news, sentiment])
        if ok_count <= 2:
            return 0.35
        if score >= 75 or score <= 35:
            return 0.8
        return 0.6

    def _position_bias(self, action: str, score: int, risk_profile: str) -> str:
        if action == "avoid":
            return "0%"
        if action == "watch":
            return "5%"
        if risk_profile == "conservative":
            return "10%" if score >= 80 else "5%"
        if risk_profile == "aggressive":
            return "20%" if score >= 78 else "10%"
        return "10%" if score < 82 else "20%"

    def _score_from_action(self, action: str, confidence: float) -> int:
        conf = float(clamp(float(confidence), 0.0, 1.0))
        if action == "buy":
            return int(round(70 + conf * 25))
        if action == "avoid":
            return int(round(40 - conf * 25))
        return int(round(45 + conf * 20))

    def _summary(self, decisions: List[StockDecision]) -> str:
        if not decisions:
            return "No analyzable stocks."
        buys = sum(1 for item in decisions if item.action == "buy")
        watches = sum(1 for item in decisions if item.action == "watch")
        avoids = sum(1 for item in decisions if item.action == "avoid")
        best = decisions[0]
        return (
            f"Analyzed {len(decisions)} stocks: buy={buys}, watch={watches}, avoid={avoids}. "
            f"Top ranked: {best.code} {best.name} score={best.rank_score}."
        )

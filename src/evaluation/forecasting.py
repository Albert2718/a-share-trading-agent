from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.agents.research.orchestrator import ResearchOrchestrator
from src.agents.research.schemas import AnalysisContext, StockCandidate, StockDecision
from src.core import LLMClient, load_config
from src.tools.lstm import LSTMPredictor

from .market import EvaluationMarketData
from .models import EvidenceItem, ModelForecast, PredictionRecord, StockPoolEntry
from .prompts import FORECAST_SCHEMA, FORECAST_SYSTEM_PROMPT


@dataclass(frozen=True)
class ResearchDraft:
    expected_return: float
    interval_low_return: float
    interval_high_return: float
    confidence: float
    company_trend: str = ""
    industry_trend: str = ""
    core_thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


def blend_forecast(
    draft: ResearchDraft,
    lstm_return: float | None,
    current_close: float,
    volatility: float,
    horizon_days: int,
    code: str,
) -> ModelForecast:
    """Fuse research and LSTM returns, then apply deterministic price bounds."""
    if not math.isfinite(current_close) or current_close <= 0:
        raise ValueError("current_close must be a positive finite number")
    if not math.isfinite(volatility) or volatility < 0:
        raise ValueError("volatility must be a non-negative finite number")
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least one")

    expected_return = float(draft.expected_return)
    if lstm_return is not None:
        if not math.isfinite(float(lstm_return)):
            raise ValueError("lstm_return must be finite when available")
        expected_return = 0.85 * expected_return + 0.15 * float(lstm_return)

    cap = _return_cap(code, volatility, horizon_days)
    expected_return = _clamp(expected_return, -cap, cap)
    low_return = _clamp(float(draft.interval_low_return), -cap, cap)
    high_return = _clamp(float(draft.interval_high_return), -cap, cap)
    low_return, high_return = sorted((low_return, high_return))
    low_return = min(low_return, expected_return)
    high_return = max(high_return, expected_return)

    predicted_close = current_close * (1.0 + expected_return)
    interval_low = current_close * (1.0 + low_return)
    interval_high = current_close * (1.0 + high_return)
    return ModelForecast(
        direction="up" if expected_return >= 0 else "down",
        expected_return=expected_return,
        predicted_close=predicted_close,
        interval_low=min(interval_low, predicted_close),
        interval_high=max(interval_high, predicted_close),
        confidence=_clamp(float(draft.confidence), 0.0, 1.0),
    )


class EvaluationForecaster:
    def __init__(
        self,
        *,
        orchestrator: ResearchOrchestrator | None = None,
        llm_client: LLMClient | None = None,
        market_data: EvaluationMarketData | None = None,
        lstm_predictor: LSTMPredictor | None = None,
        model_id: str | None = None,
        provider: str | None = None,
    ) -> None:
        config = load_config()
        self.model_id = model_id or config.news_agent_model
        self.orchestrator = orchestrator or ResearchOrchestrator()
        self.llm_client = llm_client or LLMClient(model=self.model_id)
        self.market_data = market_data or EvaluationMarketData()
        self.lstm_predictor = lstm_predictor or LSTMPredictor()
        self.provider = provider or _provider_name(self.llm_client)

    def forecast(
        self,
        entry: StockPoolEntry,
        as_of: date,
        target: date,
        kind: str,
        *,
        generated_at: datetime | str | None = None,
    ) -> PredictionRecord:
        if kind not in {"next_day", "stage"}:
            raise ValueError("kind must be 'next_day' or 'stage'")
        if target <= as_of:
            raise ValueError("target must be later than as_of")

        generated = _coerce_cutoff(generated_at)
        history, current_close, volatility = self._load_history(entry.code, as_of)
        decision = self._run_research(entry, as_of)
        reports, warnings = _cutoff_safe_reports(decision, generated)
        llm_reports = _reports_for_llm(reports)
        horizon_days = 1 if kind == "next_day" else max(1, (target - as_of).days)
        payload = {
            "stock": {
                "code": entry.code,
                "name": entry.name,
                "industry": entry.industry,
            },
            "kind": kind,
            "as_of_trade_date": as_of.isoformat(),
            "target_trade_date": target.isoformat(),
            "generated_at": generated.isoformat(),
            "horizon_days": horizon_days,
            "current_close": current_close,
            "realized_volatility": volatility,
            "reports": llm_reports,
            "warnings": list(warnings),
        }
        response = self.llm_client.structured(
            system_prompt=FORECAST_SYSTEM_PROMPT,
            user_payload=payload,
            schema=FORECAST_SCHEMA,
            temperature=0,
            max_tokens=1200,
        )
        draft = _parse_research_draft(response)

        closes = history["close"].to_numpy(dtype=float)
        lstm_return = self.lstm_predictor.predict_return(closes[-14:])
        if not _is_finite_number(lstm_return):
            lstm_return = None
            warnings.append("lstm_unavailable")

        agent_forecast = blend_forecast(
            draft=draft,
            lstm_return=lstm_return,
            current_close=current_close,
            volatility=volatility,
            horizon_days=horizon_days,
            code=entry.code,
        )
        lstm_forecast = _lstm_forecast(
            lstm_return=lstm_return,
            current_close=current_close,
            volatility=volatility,
            horizon_days=horizon_days,
            code=entry.code,
        )
        evidence = _research_evidence(reports, decision, generated)
        stage = kind == "stage"
        return PredictionRecord(
            prediction_id=f"{kind}:{as_of.isoformat()}:{entry.code}",
            kind=kind,
            rule_version=entry.rule_version or "1.0",
            generated_at=generated,
            as_of_trade_date=as_of,
            target_trade_date=target,
            code=entry.code,
            name=entry.name,
            industry=entry.industry,
            current_close=current_close,
            agent=agent_forecast,
            lstm=lstm_forecast,
            evidence=evidence,
            warnings=tuple(_unique(warnings)),
            model_id=self.model_id,
            provider=self.provider,
            lstm_checkpoint=_checkpoint_identifier(self.lstm_predictor),
            stage_direction=agent_forecast.direction if stage else None,
            stage_target_price=agent_forecast.predicted_close if stage else None,
            stage_interval_low=agent_forecast.interval_low if stage else None,
            stage_interval_high=agent_forecast.interval_high if stage else None,
            stage_confidence=agent_forecast.confidence if stage else None,
            stage_thesis=_stage_thesis(draft) if stage else None,
            catalysts=draft.catalysts,
            risks=draft.risks,
        )

    def _load_history(
        self, code: str, as_of: date
    ) -> tuple[pd.DataFrame, float, float]:
        history = self.market_data.raw_history(code, days=250, end_date=as_of)
        if not isinstance(history, pd.DataFrame) or history.empty:
            raise RuntimeError("quant history is missing")
        if not {"date", "close"}.issubset(history.columns):
            raise RuntimeError("quant history has an invalid schema")

        parsed_dates = pd.to_datetime(history["date"], errors="coerce")
        if parsed_dates.isna().any():
            raise RuntimeError("quant history contains an invalid date")
        if parsed_dates.iloc[-1].date() != as_of:
            raise RuntimeError("quant history latest date does not match as_of")

        clean = history.copy()
        clean["date"] = parsed_dates
        clean["close"] = pd.to_numeric(clean["close"], errors="coerce")
        closes = clean["close"]
        if closes.isna().any() or len(closes) < 2:
            raise RuntimeError("quant history has insufficient close values")
        current_close = float(closes.iloc[-1])
        if not math.isfinite(current_close) or current_close <= 0:
            raise RuntimeError("quant history latest close is invalid")
        returns = closes.pct_change(fill_method=None).dropna().tail(20)
        volatility = float(returns.std(ddof=0)) if not returns.empty else 0.0
        if not math.isfinite(volatility):
            raise RuntimeError("quant history volatility is invalid")
        return clean, current_close, volatility

    def _run_research(self, entry: StockPoolEntry, as_of: date) -> StockDecision:
        report = self.orchestrator.analyze(
            [StockCandidate(code=entry.code, name=entry.name)],
            AnalysisContext(
                depth="full",
                risk_profile="balanced",
                use_llm=True,
                as_of=as_of.isoformat(),
                history_days=250,
            ),
            mode="single",
        )
        decisions = list(getattr(report, "all_decisions", ()) or ())
        decision = next((item for item in decisions if item.code == entry.code), None)
        if decision is None:
            raise RuntimeError("deep research returned no decision for stock")
        return decision


def _return_cap(code: str, volatility: float, horizon_days: int) -> float:
    if horizon_days == 1:
        board_limit = 0.20 if code.startswith(("300", "688")) else 0.10
        return min(board_limit, max(0.02, 2.5 * volatility))
    return min(0.30, max(0.05, 2.5 * volatility * math.sqrt(horizon_days)))


def _cutoff_safe_reports(
    decision: StockDecision, generated_at: datetime
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    reports = {
        "quant": _json_safe(deepcopy(decision.quant)),
        "fundamental": _json_safe(deepcopy(decision.fundamental)),
        "news": _json_safe(deepcopy(decision.news)),
        "sentiment": _json_safe(deepcopy(decision.sentiment)),
    }
    warnings: list[str] = []
    events = reports["news"].get("events", [])
    if not isinstance(events, list):
        events = []
        warnings.append("news_timestamp_unverifiable")
    accepted = []
    for event in events:
        if not isinstance(event, dict):
            warnings.append("news_timestamp_unverifiable")
            continue
        published_at = _parse_evidence_time(event.get("published_at"))
        if published_at is None:
            warnings.append("news_timestamp_unverifiable")
            continue
        if published_at > generated_at:
            warnings.append("news_after_cutoff")
            continue
        accepted.append(event)
    reports["news"]["events"] = accepted
    return reports, _unique(warnings)


def _reports_for_llm(reports: Mapping[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    llm_reports = deepcopy(dict(reports))
    quant = llm_reports["quant"]
    quant.pop("model_expected_return", None)
    factors = quant.get("key_factors")
    if isinstance(factors, list):
        quant["key_factors"] = [
            factor
            for factor in factors
            if not (isinstance(factor, str) and "lstm" in factor.casefold())
        ]
    return llm_reports


def _parse_research_draft(response: Any) -> ResearchDraft:
    required = set(FORECAST_SCHEMA["schema"]["required"])
    if not isinstance(response, dict) or set(response) != required:
        raise RuntimeError("malformed structured forecast")
    numeric_fields = (
        "expected_return",
        "interval_low_return",
        "interval_high_return",
        "confidence",
    )
    if not all(_is_finite_number(response.get(field)) for field in numeric_fields):
        raise RuntimeError("malformed structured forecast")
    confidence = float(response["confidence"])
    low = float(response["interval_low_return"])
    high = float(response["interval_high_return"])
    if not 0.0 <= confidence <= 1.0 or low > high:
        raise RuntimeError("malformed structured forecast")
    if not all(isinstance(response[field], str) for field in ("company_trend", "industry_trend")):
        raise RuntimeError("malformed structured forecast")

    lists: dict[str, tuple[str, ...]] = {}
    for field in ("core_thesis", "catalysts", "risks"):
        value = response[field]
        if (
            not isinstance(value, list)
            or len(value) > 5
            or any(not isinstance(item, str) for item in value)
        ):
            raise RuntimeError("malformed structured forecast")
        lists[field] = tuple(value)
    return ResearchDraft(
        expected_return=float(response["expected_return"]),
        interval_low_return=low,
        interval_high_return=high,
        confidence=confidence,
        company_trend=response["company_trend"],
        industry_trend=response["industry_trend"],
        core_thesis=lists["core_thesis"],
        catalysts=lists["catalysts"],
        risks=lists["risks"],
    )


def _lstm_forecast(
    *,
    lstm_return: float | None,
    current_close: float,
    volatility: float,
    horizon_days: int,
    code: str,
) -> ModelForecast:
    expected = float(lstm_return) if lstm_return is not None else 0.0
    spread = max(volatility * math.sqrt(horizon_days), 0.005)
    return blend_forecast(
        ResearchDraft(
            expected_return=expected,
            interval_low_return=expected - spread,
            interval_high_return=expected + spread,
            confidence=0.5 if lstm_return is not None else 0.0,
        ),
        None,
        current_close=current_close,
        volatility=volatility,
        horizon_days=horizon_days,
        code=code,
    )


def _research_evidence(
    reports: Mapping[str, dict[str, Any]],
    decision: StockDecision,
    generated_at: datetime,
) -> tuple[EvidenceItem, ...]:
    evidence = [
        EvidenceItem(
            source=f"research:{name}",
            summary=_report_summary(name, report),
            retrieved_at=generated_at,
            evidence_type="analyst_report",
            metadata={"report": report},
        )
        for name, report in reports.items()
    ]
    decision_snapshot = _json_safe(asdict(decision))
    for name, report in reports.items():
        decision_snapshot[name] = report
    evidence.append(
        EvidenceItem(
            source="research:cio",
            summary=decision.reason,
            retrieved_at=generated_at,
            evidence_type="cio_decision",
            metadata={"decision": decision_snapshot},
        )
    )
    return tuple(evidence)


def _report_summary(name: str, report: Mapping[str, Any]) -> str:
    status = str(report.get("status", "unknown"))
    if name == "news":
        return f"status={status}; events={len(report.get('events', []))}"
    return f"status={status}"


def _stage_thesis(draft: ResearchDraft) -> str:
    parts = [
        f"公司趋势：{draft.company_trend}",
        f"行业趋势：{draft.industry_trend}",
    ]
    if draft.core_thesis:
        parts.append(f"核心逻辑：{'；'.join(draft.core_thesis)}")
    return "；".join(parts)


def _checkpoint_identifier(predictor: Any) -> str:
    model_path = Path(getattr(predictor, "model_path", ""))
    path_text = str(model_path)
    if model_path.is_file():
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    else:
        digest = "missing"
    return f"{path_text}|sha256:{digest}"


def _provider_name(llm_client: Any) -> str:
    base_url = getattr(llm_client, "base_url", None)
    return str(base_url) if base_url else "openai-compatible"


def _coerce_cutoff(value: datetime | str | None) -> datetime:
    if value is None:
        result = datetime.now().astimezone()
    elif isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("generated_at must be an ISO datetime") from exc
    else:
        raise TypeError("generated_at must be a datetime, ISO string, or None")
    return result.astimezone() if result.tzinfo is None else result


def _parse_evidence_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float, np.integer, np.floating))
        and not isinstance(value, (bool, np.bool_))
        and math.isfinite(float(value))
    )


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

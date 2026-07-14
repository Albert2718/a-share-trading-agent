from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from collections.abc import Mapping
from typing import Any


def _freeze_metadata(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        raise TypeError("metadata set and frozenset values are not JSON-compatible")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("metadata mapping keys must be strings")
        return MappingProxyType(
            {key: _freeze_metadata(value[key]) for key in sorted(value)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata floats must be finite")
        return value
    raise TypeError(f"unsupported metadata value type: {type(value).__name__}")


def _thaw_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_metadata(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_metadata(item) for item in value]
    return value


@dataclass(frozen=True)
class StockPoolEntry:
    code: str
    name: str
    industry: str = ""
    liquidity: float = 0.0
    source_date: date | None = None
    selected_at: datetime | None = None
    selection_reason: str = ""
    rule_version: str = ""


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    summary: str = ""
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    evidence_type: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible snapshot.

        Metadata dicts and scalar values retain their JSON types. Input lists
        and tuples are frozen as tuples internally and emitted as JSON arrays,
        preserving nested values and order.
        """
        return {
            "source": self.source,
            "summary": self.summary,
            "published_at": (
                self.published_at.isoformat() if self.published_at else None
            ),
            "retrieved_at": (
                self.retrieved_at.isoformat() if self.retrieved_at else None
            ),
            "evidence_type": self.evidence_type,
            "metadata": _thaw_metadata(self.metadata),
        }


@dataclass(frozen=True)
class ModelForecast:
    direction: str
    expected_return: float
    predicted_close: float
    interval_low: float
    interval_high: float
    confidence: float

    def __post_init__(self) -> None:
        if self.direction not in {"up", "down"}:
            raise ValueError("direction must be 'up' or 'down'")


@dataclass(frozen=True)
class ModelError:
    error: float
    absolute_error: float
    absolute_percentage_error: float
    direction_hit: bool | None
    tolerance_hit: bool
    interval_hit: bool

    @classmethod
    def from_forecast(
        cls,
        forecast: ModelForecast,
        actual_close: float,
        actual_direction: str,
    ) -> "ModelError":
        error = forecast.predicted_close - actual_close
        percentage_error = abs(error) / abs(actual_close) if actual_close else None
        if percentage_error is None:
            raise ValueError("actual_close must be non-zero")
        return cls(
            error=error,
            absolute_error=abs(error),
            absolute_percentage_error=percentage_error,
            direction_hit=(
                None
                if actual_direction == "flat"
                else forecast.direction == actual_direction
            ),
            tolerance_hit=percentage_error <= 0.01,
            interval_hit=forecast.interval_low <= actual_close <= forecast.interval_high,
        )


@dataclass(frozen=True)
class PredictionRecord:
    prediction_id: str
    kind: str
    rule_version: str
    generated_at: datetime
    as_of_trade_date: date
    target_trade_date: date
    code: str
    name: str
    industry: str
    current_close: float
    agent: ModelForecast
    lstm: ModelForecast
    evidence: tuple[EvidenceItem, ...] = ()
    warnings: tuple[str, ...] = ()
    model_id: str = ""
    provider: str = ""
    lstm_checkpoint: str = ""
    stage_direction: str | None = None
    stage_target_price: float | None = None
    stage_interval_low: float | None = None
    stage_interval_high: float | None = None
    stage_confidence: float | None = None
    stage_thesis: str | None = None
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutcomeRecord:
    prediction_id: str
    target_trade_date: date
    previous_close: float
    actual_open: float
    actual_high: float
    actual_low: float
    actual_close: float
    actual_return: float
    actual_direction: str
    corporate_action: bool = False
    agent_error: ModelError | None = None
    lstm_error: ModelError | None = None

    def __post_init__(self) -> None:
        if self.actual_direction not in {"up", "down", "flat"}:
            raise ValueError("actual_direction must be 'up', 'down', or 'flat'")


@dataclass(frozen=True)
class BatchSummary:
    batch_id: str
    trade_date: date
    pool_size: int
    successful_predictions: int
    coverage_rate: float | None = None
    complete: bool = True
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        coverage_rate = self.successful_predictions / self.pool_size if self.pool_size else None
        object.__setattr__(self, "coverage_rate", coverage_rate)


@dataclass(frozen=True)
class MetricSummary:
    model: str
    direction_hits: int = 0
    direction_samples: int = 0
    direction_accuracy: float | None = None
    price_samples: int = 0
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    tolerance_hits: int = 0
    tolerance_rate: float | None = None
    interval_hits: int = 0
    interval_coverage: float | None = None
    max_absolute_error: float | None = None
    max_absolute_percentage_error: float | None = None

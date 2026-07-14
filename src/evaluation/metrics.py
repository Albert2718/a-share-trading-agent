from __future__ import annotations

from math import sqrt
from typing import Sequence

from .models import MetricSummary, ModelError, OutcomeRecord


def settle_direction(previous_close: float, actual_close: float) -> str:
    if actual_close > previous_close:
        return "up"
    if actual_close < previous_close:
        return "down"
    return "flat"


def _error_for(outcome: OutcomeRecord, model: str) -> ModelError:
    try:
        error = getattr(outcome, f"{model}_error")
    except AttributeError as exc:
        raise ValueError(f"unsupported model: {model}") from exc
    if error is None:
        raise ValueError(f"outcome has no {model} error")
    return error


def summarize_metrics(
    outcomes: Sequence[OutcomeRecord], model: str
) -> MetricSummary:
    if model not in {"agent", "lstm"}:
        raise ValueError(f"unsupported model: {model}")
    errors = [_error_for(outcome, model) for outcome in outcomes]
    direction_errors = [error for error in errors if error.direction_hit is not None]
    price_samples = len(errors)

    direction_hits = sum(error.direction_hit is True for error in direction_errors)
    tolerance_hits = sum(error.tolerance_hit for error in errors)
    interval_hits = sum(error.interval_hit for error in errors)

    return MetricSummary(
        model=model,
        direction_hits=direction_hits,
        direction_samples=len(direction_errors),
        direction_accuracy=(
            direction_hits / len(direction_errors) if direction_errors else None
        ),
        price_samples=price_samples,
        mae=(
            sum(error.absolute_error for error in errors) / price_samples
            if price_samples
            else None
        ),
        rmse=(
            sqrt(sum(error.error * error.error for error in errors) / price_samples)
            if price_samples
            else None
        ),
        mape=(
            sum(error.absolute_percentage_error for error in errors) / price_samples
            if price_samples
            else None
        ),
        tolerance_hits=tolerance_hits,
        tolerance_rate=tolerance_hits / price_samples if price_samples else None,
        interval_hits=interval_hits,
        interval_coverage=interval_hits / price_samples if price_samples else None,
        max_absolute_error=(
            max(error.absolute_error for error in errors) if errors else None
        ),
        max_absolute_percentage_error=(
            max(error.absolute_percentage_error for error in errors) if errors else None
        ),
    )

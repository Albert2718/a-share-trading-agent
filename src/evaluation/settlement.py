from __future__ import annotations

from datetime import date
import json
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

import pandas as pd

from .metrics import settle_direction
from .models import ModelError, OutcomeRecord, PredictionRecord
from .storage import EvaluationStorage


class SettlementMarketData(Protocol):
    def raw_history(self, code: str, days: int, end_date: date) -> pd.DataFrame: ...


class SettlementService:
    """Append one verified outcome for each prediction that has become due."""

    def __init__(self, storage: EvaluationStorage, market_data: SettlementMarketData):
        self.storage = storage
        self.market_data = market_data
        self.pending_reasons: dict[str, str] = {}
        self.settlement_warnings: dict[str, tuple[str, ...]] = {}

    def settle_due(self, latest_trade_date: date) -> list[OutcomeRecord]:
        self.pending_reasons = {}
        self.settlement_warnings = {}
        predictions = self.storage.load_predictions()
        settled_ids = {outcome.prediction_id for outcome in self.storage.load_outcomes()}
        metadata = self._load_metadata()
        pending = dict(metadata["pending"])
        warnings = dict(metadata["warnings"])
        for prediction_id in settled_ids:
            pending.pop(prediction_id, None)
            warnings.pop(prediction_id, None)
        outcomes: list[OutcomeRecord] = []
        for prediction in predictions:
            if prediction.target_trade_date > latest_trade_date or prediction.prediction_id in settled_ids:
                continue
            warnings.pop(prediction.prediction_id, None)
            outcome = self._settle(prediction)
            if outcome is None:
                pending[prediction.prediction_id] = self.pending_reasons[prediction.prediction_id]
                continue
            self.storage.append_outcome(outcome)
            pending.pop(prediction.prediction_id, None)
            if prediction.prediction_id in self.settlement_warnings:
                warnings[prediction.prediction_id] = list(
                    self.settlement_warnings[prediction.prediction_id]
                )
            outcomes.append(outcome)
        self._write_metadata(pending, warnings)
        return outcomes

    def _settle(self, prediction: PredictionRecord) -> OutcomeRecord | None:
        history = self.market_data.raw_history(
            prediction.code, days=10, end_date=prediction.target_trade_date
        )
        target, previous = self._target_and_previous_bar(history, prediction.target_trade_date)
        if target is None:
            self.pending_reasons[prediction.prediction_id] = "missing_target_bar"
            return None
        if previous is None:
            self.pending_reasons[prediction.prediction_id] = "missing_previous_bar"
            return None

        previous_close = self._number(previous, "close")
        actual_open = self._number(target, "open")
        actual_high = self._number(target, "high")
        actual_low = self._number(target, "low")
        actual_close = self._number(target, "close")
        if previous_close is None or previous_close <= 0:
            self.pending_reasons[prediction.prediction_id] = "invalid_target_bar"
            return None
        if (
            None in (actual_open, actual_high, actual_low, actual_close)
            or actual_open <= 0
            or actual_high <= 0
            or actual_low <= 0
            or actual_close <= 0
            or actual_low > actual_high
            or actual_open < actual_low
            or actual_open > actual_high
            or actual_close < actual_low
            or actual_close > actual_high
        ):
            self.pending_reasons[prediction.prediction_id] = "invalid_target_ohlc"
            return None
        actual_direction = settle_direction(previous_close, actual_close)
        actual_return = (actual_close - previous_close) / previous_close
        corporate_action, warning = self._corporate_action_status(
            prediction, previous, target, actual_return
        )
        if warning is not None:
            self.settlement_warnings[prediction.prediction_id] = (warning,)
        return OutcomeRecord(
            prediction_id=prediction.prediction_id,
            target_trade_date=prediction.target_trade_date,
            previous_close=previous_close,
            actual_open=actual_open,
            actual_high=actual_high,
            actual_low=actual_low,
            actual_close=actual_close,
            actual_return=actual_return,
            actual_direction=actual_direction,
            corporate_action=corporate_action,
            agent_error=ModelError.from_forecast(
                prediction.agent, actual_close, actual_direction
            ),
            lstm_error=ModelError.from_forecast(
                prediction.lstm, actual_close, actual_direction
            ),
        )

    @staticmethod
    def _target_and_previous_bar(
        history: pd.DataFrame, target_date: date,
    ) -> tuple[pd.Series | None, pd.Series | None]:
        if not isinstance(history, pd.DataFrame) or history.empty or "date" not in history:
            return None, None
        data = history.copy()
        data["_settlement_date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
        data = data.dropna(subset=["_settlement_date"]).sort_values("_settlement_date")
        matching = data[data["_settlement_date"] == target_date]
        if len(matching) != 1:
            return None, None
        target = matching.iloc[0]
        earlier = data[data["_settlement_date"] < target_date]
        return target, earlier.iloc[-1] if not earlier.empty else None

    @staticmethod
    def _number(bar: pd.Series, column: str) -> float | None:
        value = pd.to_numeric(bar.get(column), errors="coerce")
        number = float(value) if pd.notna(value) else None
        return number if number is not None and isfinite(number) else None

    def _corporate_action_status(
        self,
        prediction: PredictionRecord,
        previous: pd.Series,
        target: pd.Series,
        raw_return: float,
    ) -> tuple[bool, str | None]:
        for column in ("corporate_action", "is_adjusted", "adjusted"):
            value = target.get(column)
            if isinstance(value, bool) and value:
                return True, None
        for column in ("adjustment_factor", "adj_factor", "factor"):
            value = self._number(target, column)
            if value is not None and value != 1.0:
                return True, None

        qfq_history = getattr(self.market_data, "qfq_history", None)
        if not callable(qfq_history):
            return False, "corporate_action_qfq_unavailable"
        try:
            qfq = qfq_history(prediction.code, days=10, end_date=prediction.target_trade_date)
        except Exception:
            return False, "corporate_action_qfq_unavailable"
        qfq_target, qfq_previous = self._target_and_previous_bar(
            qfq, prediction.target_trade_date
        )
        if qfq_target is None or qfq_previous is None:
            return False, "corporate_action_qfq_unavailable"
        qfq_close = self._number(qfq_target, "close")
        qfq_previous_close = self._number(qfq_previous, "close")
        if qfq_close is None or not qfq_previous_close:
            return False, "corporate_action_qfq_unavailable"
        qfq_return = (qfq_close - qfq_previous_close) / qfq_previous_close
        return abs(raw_return - qfq_return) >= 0.05, None

    def _metadata_path(self) -> Path:
        return self.storage.root / "settlement_pending.json"

    def _load_metadata(self) -> dict[str, dict[str, object]]:
        path = self._metadata_path()
        if not path.exists():
            return {"pending": {}, "warnings": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pending = payload.get("pending", {})
            warnings = payload.get("warnings", {})
            if not isinstance(pending, dict) or not isinstance(warnings, dict):
                raise ValueError
            return {"pending": pending, "warnings": warnings}
        except (OSError, ValueError, json.JSONDecodeError):
            return {"pending": {}, "warnings": {}}

    def _write_metadata(self, pending: dict[str, object], warnings: dict[str, object]) -> None:
        path = self._metadata_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pending": pending, "warnings": warnings}
        with NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

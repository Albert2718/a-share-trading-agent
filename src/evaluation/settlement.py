from __future__ import annotations

from datetime import date
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

    def settle_due(self, latest_trade_date: date) -> list[OutcomeRecord]:
        self.pending_reasons = {}
        predictions = self.storage.load_predictions()
        settled_ids = {outcome.prediction_id for outcome in self.storage.load_outcomes()}
        outcomes: list[OutcomeRecord] = []
        for prediction in predictions:
            if prediction.target_trade_date > latest_trade_date or prediction.prediction_id in settled_ids:
                continue
            outcome = self._settle(prediction)
            if outcome is None:
                continue
            self.storage.append_outcome(outcome)
            outcomes.append(outcome)
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
        actual_close = self._number(target, "close")
        if previous_close is None or actual_close is None or previous_close == 0:
            self.pending_reasons[prediction.prediction_id] = "invalid_target_bar"
            return None
        actual_direction = settle_direction(previous_close, actual_close)
        actual_return = (actual_close - previous_close) / previous_close
        return OutcomeRecord(
            prediction_id=prediction.prediction_id,
            target_trade_date=prediction.target_trade_date,
            previous_close=previous_close,
            actual_open=self._number(target, "open") or actual_close,
            actual_high=self._number(target, "high") or actual_close,
            actual_low=self._number(target, "low") or actual_close,
            actual_close=actual_close,
            actual_return=actual_return,
            actual_direction=actual_direction,
            corporate_action=self._has_corporate_action(
                prediction, previous, target, actual_return
            ),
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
        return float(value) if pd.notna(value) else None

    def _has_corporate_action(
        self,
        prediction: PredictionRecord,
        previous: pd.Series,
        target: pd.Series,
        raw_return: float,
    ) -> bool:
        for column in ("corporate_action", "is_adjusted", "adjusted"):
            value = target.get(column)
            if isinstance(value, bool) and value:
                return True
        for column in ("adjustment_factor", "adj_factor", "factor"):
            value = self._number(target, column)
            if value is not None and value != 1.0:
                return True

        qfq_history = getattr(self.market_data, "qfq_history", None)
        if not callable(qfq_history):
            return False
        qfq = qfq_history(prediction.code, days=10, end_date=prediction.target_trade_date)
        qfq_target, qfq_previous = self._target_and_previous_bar(
            qfq, prediction.target_trade_date
        )
        if qfq_target is None or qfq_previous is None:
            return False
        qfq_close = self._number(qfq_target, "close")
        qfq_previous_close = self._number(qfq_previous, "close")
        if qfq_close is None or not qfq_previous_close:
            return False
        qfq_return = (qfq_close - qfq_previous_close) / qfq_previous_close
        return abs(raw_return - qfq_return) >= 0.05

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .calendar import next_trade_date
from .forecasting import EvaluationForecaster
from .market import EvaluationMarketData
from .models import BatchSummary, PredictionRecord, StockPoolEntry
from .reporting import ReportBuilder
from .settlement import SettlementService
from .stock_pool import StockPoolManager
from .storage import EvaluationStorage


HONG_KONG = ZoneInfo("Asia/Hong_Kong")
MARKET_CLOSE = time(15, 30)
POOL_SIZE = 20


class EvaluationRunner:
    """Run a resumable fixed-pool evaluation batch after the market closes."""

    def __init__(
        self,
        *,
        root: Path = Path("evaluation"),
        storage: EvaluationStorage | None = None,
        market_data: EvaluationMarketData | None = None,
        pool_manager: StockPoolManager | None = None,
        settlement: SettlementService | None = None,
        forecaster: EvaluationForecaster | None = None,
        report_builder: ReportBuilder | None = None,
    ) -> None:
        self.root = Path(root)
        self.storage = storage or EvaluationStorage(self.root)
        self.market_data = market_data or EvaluationMarketData()
        self.pool_manager = pool_manager or StockPoolManager(self.market_data)
        self.settlement = settlement or SettlementService(self.storage, self.market_data)
        self.forecaster = forecaster or EvaluationForecaster(market_data=self.market_data)
        self.report_builder = report_builder or ReportBuilder(
            self.storage, self.root / "reports", pool_size=POOL_SIZE
        )

    def run_daily(self, now: datetime) -> BatchSummary:
        local_now = self._require_after_close(now)
        as_of = local_now.date()
        latest_trade_date = self._require_latest_complete_date(as_of)
        self._require_valid_chains()

        entries = self.pool_manager.freeze(self.root / "pools" / f"{as_of.isoformat()}.json", local_now)
        if len(entries) != POOL_SIZE:
            raise RuntimeError(f"frozen stock pool must contain {POOL_SIZE} entries")
        self._require_provider_data_complete(as_of, entries)

        self.settlement.settle_due(latest_trade_date)
        target = next_trade_date(self.market_data.trade_dates(), as_of)

        errors: list[str] = []
        for kind in ("stage", "next_day"):
            records, kind_errors = self._forecast_missing_kind(entries, as_of, target, kind, local_now)
            errors.extend(kind_errors)
            # Storage appends must remain ordered and single-threaded for its hash chain.
            for record in sorted(records, key=lambda item: item.prediction_id):
                self.storage.append_prediction(record)

        successful = self._successful_next_day_count(entries, as_of)
        summary = self._batch_summary(as_of, successful, errors)
        self._write_batch_summary(summary)
        self.build_report()
        return summary

    def build_report(self) -> tuple[Path, Path]:
        return self.report_builder.build()

    def _require_after_close(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            raise RuntimeError("evaluation time must include a timezone")
        local_now = now.astimezone(HONG_KONG)
        if local_now.timetz().replace(tzinfo=None) < MARKET_CLOSE:
            raise RuntimeError("market has not closed")
        return local_now

    def _require_latest_complete_date(self, as_of: date) -> date:
        trade_dates = self.market_data.trade_dates()
        completed = [value for value in trade_dates if value <= as_of]
        if not completed or max(completed) != as_of:
            raise RuntimeError("market provider latest complete date does not equal today")
        return as_of

    def _require_provider_data_complete(self, as_of: date, entries: list[StockPoolEntry]) -> None:
        latest_complete = self._provider_latest_complete_date()
        if latest_complete is not None:
            if latest_complete != as_of:
                raise RuntimeError("provider data for today is not complete")
            return

        for entry in entries:
            try:
                history = self.market_data.raw_history(entry.code, days=5, end_date=as_of)
                latest_history_date = self._latest_history_date(history)
            except Exception as exc:
                raise RuntimeError("provider data for today is not complete") from exc
            if latest_history_date != as_of:
                raise RuntimeError("provider data for today is not complete")

    def _provider_latest_complete_date(self) -> date | None:
        provider_method = getattr(self.market_data, "latest_complete_date", None)
        if not callable(provider_method):
            return None
        value = provider_method()
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise RuntimeError("provider data for today is not complete") from exc
        if value is None:
            return None
        raise RuntimeError("provider data for today is not complete")

    @staticmethod
    def _latest_history_date(history: pd.DataFrame) -> date:
        if not isinstance(history, pd.DataFrame) or history.empty or "date" not in history:
            raise RuntimeError("provider history is missing")
        dates = pd.to_datetime(history["date"], errors="coerce").dropna()
        if dates.empty:
            raise RuntimeError("provider history is missing")
        return max(value.date() for value in dates)

    def _require_valid_chains(self) -> None:
        verification = self.storage.verify_chain()
        if not verification.get("ok"):
            raise RuntimeError(f"evaluation storage chain is invalid: {verification.get('error', '')}")

    def _forecast_missing_kind(
        self,
        entries: list[StockPoolEntry],
        as_of: date,
        target: date,
        kind: str,
        generated_at: datetime,
    ) -> tuple[list[PredictionRecord], list[str]]:
        jobs: list[tuple[StockPoolEntry, str]] = []
        for entry in entries:
            prediction_id = self._prediction_id(kind, as_of, entry.code)
            if not self.storage.prediction_exists(prediction_id):
                jobs.append((entry, kind))

        records: list[PredictionRecord] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self._forecast_one, entry, as_of, target, kind, generated_at
                ): (entry.code, kind)
                for entry, kind in jobs
            }
            for future in as_completed(futures):
                record, error = future.result()
                if record is not None:
                    records.append(record)
                if error is not None:
                    errors.append(error)
        return records, sorted(errors)

    def _successful_next_day_count(self, entries: list[StockPoolEntry], as_of: date) -> int:
        return sum(
            1
            for entry in entries
            if self.storage.prediction_exists(self._prediction_id("next_day", as_of, entry.code))
        )

    @staticmethod
    def _prediction_id(kind: str, as_of: date, code: str) -> str:
        return f"{kind}:{as_of.isoformat()}:{code}"

    def _forecast_one(
        self,
        entry: StockPoolEntry,
        as_of: date,
        target: date,
        kind: str,
        generated_at: datetime,
    ) -> tuple[PredictionRecord | None, str | None]:
        try:
            return (
                self.forecaster.forecast(
                    entry, as_of, target, kind, generated_at=generated_at
                ),
                None,
            )
        except Exception as exc:
            return None, f"{kind}:{entry.code}:{type(exc).__name__}"

    @staticmethod
    def _batch_summary(as_of: date, successful: int, errors: list[str]) -> BatchSummary:
        status = "complete" if successful == POOL_SIZE else "partial" if successful >= 18 else "incomplete"
        return BatchSummary(
            batch_id=f"daily:{as_of.isoformat()}",
            trade_date=as_of,
            pool_size=POOL_SIZE,
            successful_predictions=successful,
            complete=status == "complete",
            warnings=tuple([status, *errors]),
        )

    def _write_batch_summary(self, summary: BatchSummary) -> Path:
        path = self.root / "batches" / f"{summary.trade_date.isoformat()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "batch_id": summary.batch_id,
            "trade_date": summary.trade_date.isoformat(),
            "pool_size": summary.pool_size,
            "successful_predictions": summary.successful_predictions,
            "coverage_rate": summary.coverage_rate,
            "complete": summary.complete,
            "status": summary.warnings[0],
            "warnings": list(summary.warnings[1:]),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return path

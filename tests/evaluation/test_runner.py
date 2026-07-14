from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd

from src.evaluation.models import BatchSummary, ModelForecast, PredictionRecord, StockPoolEntry
from src.evaluation.runner import EvaluationRunner


HONG_KONG = ZoneInfo("Asia/Hong_Kong")
FIXED_AFTER_CLOSE = datetime(2026, 7, 14, 15, 30, tzinfo=HONG_KONG)


def prediction(entry: StockPoolEntry, kind: str, target: date) -> PredictionRecord:
    forecast = ModelForecast("up", 0.01, 101.0, 99.0, 103.0, 0.6)
    return PredictionRecord(
        prediction_id=f"{kind}:2026-07-14:{entry.code}",
        kind=kind,
        rule_version="1.0",
        generated_at=FIXED_AFTER_CLOSE,
        as_of_trade_date=date(2026, 7, 14),
        target_trade_date=target,
        code=entry.code,
        name=entry.name,
        industry=entry.industry,
        current_close=100.0,
        agent=forecast,
        lstm=forecast,
    )


def make_runner(
    *,
    existing_ids: set[str] | None = None,
    latest_date: date | None = None,
    history_latest_date: date | None = None,
    failing_codes: set[str] | None = None,
    latest_complete_date: date | None = None,
):
    calls: list[str] = []
    entries = [
        StockPoolEntry(code=f"{600000 + index:06d}", name=str(index), industry="test")
        for index in range(20)
    ]
    entries[0] = StockPoolEntry(code="600519", name="Moutai", industry="test")
    storage = Mock()
    existing_ids = existing_ids or set()
    storage.verify_chain.return_value = {"ok": True}
    storage.prediction_exists.side_effect = lambda prediction_id: prediction_id in existing_ids

    def append_prediction(record):
        calls.append(f"append:{record.kind}:{record.code}")
        existing_ids.add(record.prediction_id)

    storage.append_prediction.side_effect = append_prediction
    market = Mock()
    market.trade_dates.return_value = [date(2026, 7, 13), latest_date or date(2026, 7, 14), date(2026, 7, 15)]
    if latest_complete_date is not None:
        market.latest_complete_date.return_value = latest_complete_date
    else:
        del market.latest_complete_date

    def raw_history(code, days, end_date):
        return pd.DataFrame(
            [
                {"date": pd.Timestamp(history_latest_date or end_date), "close": 100.0, "volume": 1000.0},
            ]
        )

    market.raw_history.side_effect = raw_history
    pool = Mock()
    pool.freeze.return_value = entries
    settlement = Mock()
    settlement.settle_due.side_effect = lambda _: calls.append("settle") or []
    forecaster = Mock()
    failing_codes = failing_codes or set()

    def forecast(entry, as_of, target, kind, generated_at):
        if entry.code in failing_codes:
            raise RuntimeError("forecast failed")
        return prediction(entry, kind, target)

    forecaster.forecast.side_effect = forecast
    reports = Mock()
    reports.build.return_value = (Path("summary.json"), Path("summary.md"))
    runner = EvaluationRunner(
        storage=storage,
        market_data=market,
        pool_manager=pool,
        settlement=settlement,
        forecaster=forecaster,
        report_builder=reports,
        root=Path(tempfile.gettempdir()) / "evaluation-runner-tests",
    )
    return runner, calls


class RunnerTests(unittest.TestCase):
    @staticmethod
    def existing_id(kind: str, code: str) -> str:
        return f"{kind}:2026-07-14:{code}"

    def test_daily_settles_before_forecasting_and_counts_resumed_next_day_predictions(self):
        runner, calls = make_runner(existing_ids={self.existing_id("next_day", "600519")})

        summary = runner.run_daily(FIXED_AFTER_CLOSE)

        self.assertEqual(calls[0], "settle")
        self.assertNotIn("append:next_day:600519", calls)
        self.assertEqual(summary.pool_size, 20)
        self.assertEqual(summary.successful_predictions, 20)
        self.assertTrue(summary.complete)
        self.assertAlmostEqual(summary.coverage_rate, 1.0)

    def test_full_rerun_resume_reports_complete_without_appending_predictions(self):
        existing_ids = {
            self.existing_id(kind, f"{600000 + index:06d}")
            for kind in ("stage", "next_day")
            for index in range(20)
        }
        existing_ids.add(self.existing_id("stage", "600519"))
        existing_ids.add(self.existing_id("next_day", "600519"))
        runner, calls = make_runner(existing_ids=existing_ids)

        summary = runner.run_daily(FIXED_AFTER_CLOSE)

        self.assertEqual(calls, ["settle"])
        self.assertEqual(summary.successful_predictions, 20)
        self.assertTrue(summary.complete)

    def test_resumption_is_distinct_per_prediction_kind(self):
        runner, calls = make_runner(existing_ids={self.existing_id("stage", "600519")})

        summary = runner.run_daily(FIXED_AFTER_CLOSE)

        self.assertNotIn("append:stage:600519", calls)
        self.assertIn("append:next_day:600519", calls)
        self.assertEqual(summary.successful_predictions, 20)
        self.assertTrue(summary.complete)

    def test_stage_records_are_appended_before_next_day_records(self):
        runner, calls = make_runner()

        runner.run_daily(FIXED_AFTER_CLOSE)

        stage_positions = [index for index, call in enumerate(calls) if call.startswith("append:stage:")]
        next_day_positions = [index for index, call in enumerate(calls) if call.startswith("append:next_day:")]
        self.assertEqual(len(stage_positions), 20)
        self.assertEqual(len(next_day_positions), 20)
        self.assertLess(max(stage_positions), min(next_day_positions))

    def test_before_close_is_rejected(self):
        runner, _ = make_runner()

        with self.assertRaisesRegex(RuntimeError, "market has not closed"):
            runner.run_daily(datetime(2026, 7, 14, 14, 59, tzinfo=HONG_KONG))

    def test_stale_market_date_is_rejected(self):
        runner, _ = make_runner(latest_date=date(2026, 7, 13))

        with self.assertRaisesRegex(RuntimeError, "latest complete date"):
            runner.run_daily(FIXED_AFTER_CLOSE)

    def test_stale_provider_history_for_today_is_rejected(self):
        runner, _ = make_runner(history_latest_date=date(2026, 7, 13))

        with self.assertRaisesRegex(RuntimeError, "provider data for today"):
            runner.run_daily(FIXED_AFTER_CLOSE)

    def test_stale_provider_latest_complete_date_is_rejected(self):
        runner, _ = make_runner(latest_complete_date=date(2026, 7, 13))

        with self.assertRaisesRegex(RuntimeError, "provider data for today"):
            runner.run_daily(FIXED_AFTER_CLOSE)

    def test_twenty_predictions_is_complete(self):
        runner, _ = make_runner()

        summary = runner.run_daily(FIXED_AFTER_CLOSE)

        self.assertEqual(summary.successful_predictions, 20)
        self.assertTrue(summary.complete)
        self.assertIn("complete", summary.warnings)

    def test_eighteen_predictions_is_partial(self):
        runner, _ = make_runner(failing_codes={"600018", "600019"})

        summary = runner.run_daily(FIXED_AFTER_CLOSE)

        self.assertEqual(summary.successful_predictions, 18)
        self.assertFalse(summary.complete)
        self.assertIn("partial", summary.warnings)

    def test_batch_is_incomplete_below_eighteen_predictions(self):
        runner, _ = make_runner(failing_codes={"600017", "600018", "600019"})

        summary = runner.run_daily(FIXED_AFTER_CLOSE)

        self.assertEqual(summary.successful_predictions, 17)
        self.assertFalse(summary.complete)
        self.assertIn("incomplete", summary.warnings)


if __name__ == "__main__":
    unittest.main()

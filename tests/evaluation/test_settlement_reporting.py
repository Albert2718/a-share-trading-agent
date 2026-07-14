from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.evaluation.models import ModelForecast, PredictionRecord
from src.evaluation.reporting import ReportBuilder
from src.evaluation.settlement import SettlementService
from src.evaluation.storage import EvaluationStorage


def prediction(
    prediction_id: str = "p1",
    *,
    kind: str = "next_day",
    target: date = date(2026, 7, 15),
    code: str = "600519",
    current_close: float = 100.0,
) -> PredictionRecord:
    agent = ModelForecast("up", 0.02, 102.0, 100.0, 104.0, 0.8)
    lstm = ModelForecast("down", -0.01, 99.0, 97.0, 101.0, 0.5)
    return PredictionRecord(
        prediction_id=prediction_id,
        kind=kind,
        rule_version="1.0",
        generated_at=datetime(2026, 7, 14, 15, 30),
        as_of_trade_date=date(2026, 7, 14),
        target_trade_date=target,
        code=code,
        name="贵州茅台",
        industry="白酒",
        current_close=current_close,
        agent=agent,
        lstm=lstm,
        stage_thesis="经营稳健",
        catalysts=("需求恢复",),
        risks=("估值偏高",),
    )


class FakeMarket:
    def __init__(self, actual_close: float | None = 102.0, *, corporate_action: bool = False):
        self.actual_close = actual_close
        self.corporate_action = corporate_action

    def raw_history(self, code: str, days: int, end_date: date) -> pd.DataFrame:
        if self.actual_close is None:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])
        return pd.DataFrame(
            [
                {"date": "2026-07-14", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
                {"date": "2026-07-15", "open": 101.0, "high": 103.0, "low": 100.0, "close": self.actual_close,
                 "adjustment_factor": 2.0 if self.corporate_action else 1.0},
            ]
        )


class QfqGapMarket(FakeMarket):
    def qfq_history(self, code: str, days: int, end_date: date) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"date": "2026-07-14", "close": 100.0},
                {"date": "2026-07-15", "close": 100.0},
            ]
        )


def make_service(actual_close: float | None = 102.0, *, corporate_action: bool = False):
    root = TemporaryDirectory(dir=Path.cwd())
    storage = EvaluationStorage(Path(root.name))
    storage.append_prediction(prediction())
    return SettlementService(storage, FakeMarket(actual_close, corporate_action=corporate_action)), storage, root


class SettlementReportingTests(unittest.TestCase):
    def test_due_prediction_is_settled_once(self):
        service, storage, root = make_service(actual_close=102.0)
        self.addCleanup(root.cleanup)

        first = service.settle_due(date(2026, 7, 15))
        second = service.settle_due(date(2026, 7, 15))

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertTrue(first[0].agent_error.direction_hit)
        self.assertEqual(len(storage.load_outcomes()), 1)

    def test_flat_actual_excludes_direction_metric(self):
        service, _, root = make_service(actual_close=100.0)
        self.addCleanup(root.cleanup)

        outcome = service.settle_due(date(2026, 7, 15))[0]

        self.assertEqual(outcome.actual_direction, "flat")
        self.assertIsNone(outcome.agent_error.direction_hit)

    def test_missing_target_bar_stays_pending_with_reason(self):
        service, _, root = make_service(actual_close=None)
        self.addCleanup(root.cleanup)

        self.assertEqual(service.settle_due(date(2026, 7, 15)), [])
        self.assertEqual(service.pending_reasons, {"p1": "missing_target_bar"})

    def test_explicit_adjustment_metadata_marks_corporate_action(self):
        service, _, root = make_service(actual_close=102.0, corporate_action=True)
        self.addCleanup(root.cleanup)

        self.assertTrue(service.settle_due(date(2026, 7, 15))[0].corporate_action)

    def test_provider_without_qfq_history_settles_and_records_warning(self):
        service, storage, root = make_service(actual_close=102.0)
        self.addCleanup(root.cleanup)

        outcome = service.settle_due(date(2026, 7, 15))[0]

        self.assertFalse(outcome.corporate_action)
        metadata = json.loads((Path(root.name) / "settlement_pending.json").read_text(encoding="utf-8"))
        self.assertIn("corporate_action_qfq_unavailable", metadata["warnings"]["p1"])

    def test_qfq_return_gap_marks_corporate_action(self):
        service, storage, root = make_service(actual_close=110.0)
        self.addCleanup(root.cleanup)
        service.market_data = QfqGapMarket(actual_close=110.0)

        self.assertTrue(service.settle_due(date(2026, 7, 15))[0].corporate_action)

    def test_invalid_target_ohlc_stays_pending_without_fabricated_values(self):
        service, storage, root = make_service(actual_close=102.0)
        self.addCleanup(root.cleanup)
        original = service.market_data.raw_history

        def raw_history(code: str, days: int, end_date: date) -> pd.DataFrame:
            history = original(code, days, end_date)
            history.loc[history["date"] == "2026-07-15", "high"] = float("nan")
            return history

        service.market_data.raw_history = raw_history
        self.assertEqual(service.settle_due(date(2026, 7, 15)), [])
        self.assertEqual(service.pending_reasons, {"p1": "invalid_target_ohlc"})
        self.assertEqual(storage.load_outcomes(), [])

    def test_pending_reason_is_persisted_for_later_report_builds(self):
        service, storage, root = make_service(actual_close=None)
        self.addCleanup(root.cleanup)
        service.settle_due(date(2026, 7, 15))

        json_path, _ = ReportBuilder(storage, Path(root.name) / "reports", pool_size=20).build()
        payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["pending_predictions"][0]["reason"], "missing_target_bar")

    def test_report_is_reproducible_utf8_and_contains_required_sections(self):
        service, storage, root = make_service(actual_close=102.0)
        self.addCleanup(root.cleanup)
        service.settle_due(date(2026, 7, 15))
        reports = Path(root.name) / "reports"

        first_json, first_markdown = ReportBuilder(storage, reports, pool_size=20).build()
        first_json_text = first_json.read_text(encoding="utf-8")
        first_markdown_text = first_markdown.read_text(encoding="utf-8")
        second_json, second_markdown = ReportBuilder(storage, reports, pool_size=20).build()

        self.assertEqual(first_json_text, second_json.read_text(encoding="utf-8"))
        self.assertEqual(first_markdown_text, second_markdown.read_text(encoding="utf-8"))
        self.assertEqual(first_json.name, "summary.json")
        self.assertEqual(first_markdown.name, "summary.md")
        self.assertIn("完整 Agent", first_markdown_text)
        self.assertIn("LSTM", first_markdown_text)
        self.assertIn("预测覆盖率", first_markdown_text)
        self.assertNotIn("最大回撤", first_markdown_text)
        self.assertEqual(json.loads(first_json_text)["coverage"]["pool_size"], 20)

    def test_report_contains_pending_stage_and_breakdowns(self):
        with TemporaryDirectory(dir=Path.cwd()) as root:
            storage = EvaluationStorage(Path(root) / "data")
            storage.append_prediction(prediction("stage", kind="stage", target=date(2026, 7, 23)))
            report = ReportBuilder(storage, Path(root) / "reports", pool_size=20)

            _, markdown_path = report.build()
            markdown = markdown_path.read_text(encoding="utf-8")

            for heading in ("5 日滚动", "20 日滚动", "股票", "行业", "置信度", "待结算预测", "阶段趋势"):
                self.assertIn(heading, markdown)
            self.assertIn("2026-07-14", markdown)
            self.assertIn("经营稳健", markdown)

    def test_report_has_no_trading_metrics_when_no_outcomes_exist(self):
        with TemporaryDirectory(dir=Path.cwd()) as root:
            storage = EvaluationStorage(Path(root) / "data")
            storage.append_prediction(prediction())

            json_path, _ = ReportBuilder(storage, Path(root) / "reports", pool_size=20).build()
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["samples"], 0)
            self.assertIsNone(payload["metrics"]["agent"]["mae"])
            self.assertEqual(payload["pending_predictions"][0]["reason"], "not_due_or_missing_bar")

    def test_failed_stocks_identifies_lstm_only_direction_miss(self):
        service, storage, root = make_service(actual_close=102.0)
        self.addCleanup(root.cleanup)
        service.settle_due(date(2026, 7, 15))

        json_path, _ = ReportBuilder(storage, Path(root.name) / "reports", pool_size=20).build()
        failures = json.loads(json_path.read_text(encoding="utf-8"))["failed_stocks"]

        self.assertEqual(failures, [{
            "prediction_id": "p1", "code": "600519", "name": "贵州茅台",
            "actual_direction": "up", "failed_models": ["lstm"],
        }])


if __name__ == "__main__":
    unittest.main()

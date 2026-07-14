from __future__ import annotations

import unittest
from datetime import date, datetime
import json

from src.evaluation.calendar import next_trade_date
from src.evaluation.metrics import settle_direction, summarize_metrics
from src.evaluation.models import (
    BatchSummary,
    EvidenceItem,
    ModelError,
    ModelForecast,
    OutcomeRecord,
)


def make_forecast(
    predicted_close: float,
    low: float = 0.0,
    high: float = 100.0,
    direction: str = "up",
) -> ModelForecast:
    return ModelForecast(
        direction=direction,
        expected_return=0.0,
        predicted_close=predicted_close,
        interval_low=low,
        interval_high=high,
        confidence=0.8,
    )


def make_outcome(
    previous_close: float,
    actual_close: float,
    agent_price: float,
    low: float = 0.0,
    high: float = 100.0,
) -> OutcomeRecord:
    actual_direction = settle_direction(previous_close, actual_close)
    return OutcomeRecord(
        prediction_id=f"p-{previous_close}-{actual_close}-{agent_price}",
        target_trade_date=date(2026, 7, 20),
        previous_close=previous_close,
        actual_open=actual_close,
        actual_high=actual_close,
        actual_low=actual_close,
        actual_close=actual_close,
        actual_return=(actual_close - previous_close) / previous_close,
        actual_direction=actual_direction,
        corporate_action=False,
        agent_error=ModelError.from_forecast(
            make_forecast(agent_price, low, high), actual_close, actual_direction
        ),
        lstm_error=ModelError.from_forecast(
            make_forecast(agent_price, low, high), actual_close, actual_direction
        ),
    )


class CalendarMetricTests(unittest.TestCase):
    def test_model_forecast_rejects_invalid_direction(self):
        with self.assertRaisesRegex(ValueError, "direction must be 'up' or 'down'"):
            make_forecast(10.0, direction="flat")

    def test_outcome_record_rejects_invalid_actual_direction(self):
        with self.assertRaisesRegex(
            ValueError, "actual_direction must be 'up', 'down', or 'flat'"
        ):
            OutcomeRecord(
                prediction_id="p-1",
                target_trade_date=date(2026, 7, 20),
                previous_close=10.0,
                actual_open=10.0,
                actual_high=10.0,
                actual_low=10.0,
                actual_close=10.0,
                actual_return=0.0,
                actual_direction="sideways",
            )

    def test_evidence_metadata_is_snapshot_and_json_serializable(self):
        metadata = {"tags": ["market"], "nested": {"source_id": "a1"}}
        evidence = EvidenceItem(source="report", metadata=metadata)

        metadata["tags"].append("news")
        metadata["nested"]["source_id"] = "changed"

        with self.assertRaises(TypeError):
            evidence.metadata["new"] = "value"
        with self.assertRaises(TypeError):
            evidence.metadata["nested"]["source_id"] = "changed-again"
        self.assertEqual(evidence.metadata["tags"], ("market",))
        self.assertEqual(evidence.metadata["nested"]["source_id"], "a1")
        self.assertEqual(json.loads(json.dumps(evidence.to_dict()))["metadata"], {
            "tags": ["market"],
            "nested": {"source_id": "a1"},
        })

    def test_evidence_timestamps_serialize_as_iso_strings(self):
        evidence = EvidenceItem(
            source="report",
            published_at=datetime(2026, 7, 17, 9, 30),
            retrieved_at=datetime(2026, 7, 17, 10, 15, 30),
        )

        try:
            serialized = json.loads(json.dumps(evidence.to_dict()))
        except TypeError as exc:
            self.fail(f"EvidenceItem.to_dict() is not JSON-compatible: {exc}")

        self.assertEqual(serialized["published_at"], "2026-07-17T09:30:00")
        self.assertEqual(serialized["retrieved_at"], "2026-07-17T10:15:30")

    def test_evidence_metadata_rejects_sets_recursively(self):
        for value in ({"market"}, frozenset({"market"})):
            with self.subTest(value=value), self.assertRaisesRegex(
                TypeError, "set and frozenset"
            ):
                EvidenceItem(source="report", metadata={"nested": [value]})

    def test_evidence_metadata_preserves_json_compatible_nested_values(self):
        evidence = EvidenceItem(
            source="report",
            metadata={
                "dict": {"enabled": True, "missing": None},
                "list": [1, 2.5, "three"],
                "tuple": ("first", {"second": 2}),
            },
        )

        serialized = json.loads(json.dumps(evidence.to_dict(), sort_keys=True))

        self.assertEqual(serialized["metadata"], {
            "dict": {"enabled": True, "missing": None},
            "list": [1, 2.5, "three"],
            "tuple": ["first", {"second": 2}],
        })

    def test_evidence_metadata_serialization_is_deterministic(self):
        first = EvidenceItem(
            source="report",
            metadata={"z": 1, "a": {"y": 2, "b": 3}},
        )
        second = EvidenceItem(
            source="report",
            metadata={"a": {"b": 3, "y": 2}, "z": 1},
        )

        self.assertEqual(
            json.dumps(first.to_dict(), ensure_ascii=False),
            json.dumps(second.to_dict(), ensure_ascii=False),
        )

    def test_next_trade_date_skips_weekend(self):
        dates = [date(2026, 7, 17), date(2026, 7, 20)]
        self.assertEqual(next_trade_date(dates, date(2026, 7, 17)), date(2026, 7, 20))

    def test_settle_direction_uses_flat_only_for_equal_closes(self):
        self.assertEqual(settle_direction(10.0, 10.1), "up")
        self.assertEqual(settle_direction(10.0, 9.9), "down")
        self.assertEqual(settle_direction(10.0, 10.0), "flat")

    def test_flat_sample_has_no_direction_hit(self):
        outcome = make_outcome(previous_close=10.0, actual_close=10.0, agent_price=10.1)
        summary = summarize_metrics([outcome], model="agent")
        self.assertEqual(summary.direction_samples, 0)
        self.assertEqual(summary.price_samples, 1)
        self.assertIsNone(summary.direction_accuracy)

    def test_price_metrics_and_interval_coverage(self):
        outcomes = [
            make_outcome(10.0, 10.2, agent_price=10.1, low=10.0, high=10.3),
            make_outcome(10.0, 9.8, agent_price=10.0, low=9.9, high=10.1),
        ]
        summary = summarize_metrics(outcomes, model="agent")
        self.assertAlmostEqual(summary.mae, 0.15)
        self.assertAlmostEqual(summary.rmse, 0.158113883, places=7)
        self.assertAlmostEqual(summary.mape, (0.1 / 10.2 + 0.2 / 9.8) / 2)
        self.assertEqual(summary.direction_hits, 1)
        self.assertEqual(summary.direction_samples, 2)
        self.assertEqual(summary.tolerance_hits, 1)
        self.assertEqual(summary.interval_hits, 1)

    def test_empty_metric_denominators_return_none(self):
        summary = summarize_metrics([], model="lstm")
        self.assertIsNone(summary.direction_accuracy)
        self.assertIsNone(summary.mae)
        self.assertIsNone(summary.rmse)
        self.assertIsNone(summary.mape)

    def test_batch_summary_derives_coverage_rate(self):
        summary = BatchSummary(
            batch_id="batch-1",
            trade_date=date(2026, 7, 17),
            pool_size=20,
            successful_predictions=18,
        )
        self.assertEqual(summary.coverage_rate, 0.9)


if __name__ == "__main__":
    unittest.main()

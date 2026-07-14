from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.evaluation import storage as storage_module
from src.evaluation.models import EvidenceItem, ModelForecast, OutcomeRecord, PredictionRecord
from src.evaluation.storage import EvaluationStorage


def sample_prediction(
    prediction_id: str,
    *,
    code: str = "600519",
    kind: str = "next_day",
) -> PredictionRecord:
    forecast = ModelForecast(
        direction="up",
        expected_return=0.03,
        predicted_close=123.45,
        interval_low=118.0,
        interval_high=128.0,
        confidence=0.8,
    )
    return PredictionRecord(
        prediction_id=prediction_id,
        kind=kind,
        rule_version="v1",
        generated_at=datetime(2026, 7, 14, 8, 30),
        as_of_trade_date=date(2026, 7, 14),
        target_trade_date=date(2026, 7, 15),
        code=code,
        name="贵州茅台",
        industry="白酒",
        current_close=120.0,
        agent=forecast,
        lstm=forecast,
        evidence=(
            EvidenceItem(
                source="公告",
                summary="经营情况稳定",
                published_at=datetime(2026, 7, 13, 9, 0),
                metadata={"标签": ["市场", "公告"]},
            ),
        ),
        warnings=("注意波动",),
        catalysts=("需求恢复",),
        risks=("估值偏高",),
    )


def sample_outcome(prediction_id: str) -> OutcomeRecord:
    return OutcomeRecord(
        prediction_id=prediction_id,
        target_trade_date=date(2026, 7, 15),
        previous_close=120.0,
        actual_open=121.0,
        actual_high=124.0,
        actual_low=119.5,
        actual_close=123.0,
        actual_return=0.025,
        actual_direction="up",
    )


class StorageTests(unittest.TestCase):
    def test_new_record_fsync_precedes_parent_directory_sync(self):
        events: list[object] = []
        with TemporaryDirectory() as root:
            path = Path(root) / "predictions" / "2026-07-14" / "600519-next_day.json"
            with (
                patch.object(
                    storage_module.os,
                    "fsync",
                    side_effect=lambda _fd: events.append("file_fsync"),
                ),
                patch.object(
                    storage_module,
                    "_sync_directory",
                    side_effect=lambda directory: events.append(
                        ("directory_sync", directory)
                    ),
                    create=True,
                ),
            ):
                storage_module._write_new_json(path, {"prediction_id": "p1"})

        self.assertEqual(events, ["file_fsync", ("directory_sync", path.parent)])

    def test_manifest_replace_precedes_parent_directory_sync(self):
        events: list[object] = []
        real_replace = storage_module.os.replace
        with TemporaryDirectory() as root:
            path = Path(root) / "predictions" / "manifest.json"

            def replace(source: Path, destination: Path) -> None:
                events.append(("replace", destination))
                real_replace(source, destination)

            with (
                patch.object(
                    storage_module.os,
                    "fsync",
                    side_effect=lambda _fd: events.append("file_fsync"),
                ),
                patch.object(storage_module.os, "replace", side_effect=replace),
                patch.object(
                    storage_module,
                    "_sync_directory",
                    side_effect=lambda directory: events.append(
                        ("directory_sync", directory)
                    ),
                    create=True,
                ),
            ):
                storage_module._write_json_atomic(
                    path, {"count": 1, "final_hash": "abc"}
                )

        self.assertEqual(events, [
            "file_fsync",
            ("replace", path),
            ("directory_sync", path.parent),
        ])

    def test_prediction_cannot_be_overwritten(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            record = sample_prediction("next_day:2026-07-14:600519")
            storage.append_prediction(record)
            with self.assertRaises(FileExistsError):
                storage.append_prediction(record)

    def test_prediction_round_trips_utf8_and_nested_dataclasses(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            record = sample_prediction("p1")
            storage.append_prediction(record)

            loaded = storage.load_predictions()

            self.assertEqual(loaded, [record])
            self.assertEqual(
                json.loads(
                    (Path(root) / "predictions" / "2026-07-14" / "600519-next_day.json")
                    .read_text(encoding="utf-8")
                )["evidence"][0]["summary"],
                "经营情况稳定",
            )

    def test_hash_chain_links_records(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            first = storage.append_prediction(sample_prediction("p1"))
            second = storage.append_prediction(sample_prediction("p2", code="000001"))
            first_data = json.loads(first.read_text(encoding="utf-8"))
            second_data = json.loads(second.read_text(encoding="utf-8"))

            self.assertEqual(first_data["sequence"], 1)
            self.assertEqual(second_data["sequence"], 2)
            self.assertEqual(second_data["previous_hash"], first_data["content_hash"])
            self.assertEqual(
                [record.prediction_id for record in storage.load_predictions()],
                ["p1", "p2"],
            )
            self.assertTrue(storage.verify_chain()["ok"])

    def test_manifest_detects_deleted_tail_record(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            storage.append_prediction(sample_prediction("p1"))
            tail = storage.append_prediction(sample_prediction("p2", code="000001"))
            manifest_path = Path(root) / "predictions" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tail_payload = json.loads(tail.read_text(encoding="utf-8"))

            self.assertEqual(manifest, {
                "count": 2,
                "final_hash": tail_payload["content_hash"],
            })
            tail.unlink()

            verification = storage.verify_chain()
            self.assertFalse(verification["ok"])
            self.assertEqual(verification["chain"], "predictions")

    def test_prediction_path_rejects_unsafe_code_and_kind(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            base = sample_prediction("p1")

            for code in ("12345", "1234567", "123/45", "../001", "１２３４５６"):
                with self.subTest(code=code), self.assertRaises(ValueError):
                    storage.append_prediction(replace(base, code=code))
            for kind in ("next/day", "../stage", "..", "next_day_extra"):
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    storage.append_prediction(replace(base, kind=kind))

            self.assertFalse((Path(root) / "predictions").exists())

    def test_prediction_path_resolves_inside_prediction_root(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))

            path = storage.append_prediction(sample_prediction("p1", kind="stage"))

            self.assertTrue(
                path.resolve().is_relative_to((Path(root) / "predictions").resolve())
            )

    def test_tampered_record_breaks_chain_and_is_rejected(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            path = storage.append_prediction(sample_prediction("p1"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["name"] = "被篡改"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            verification = storage.verify_chain()

            self.assertFalse(verification["ok"])
            with self.assertRaises(ValueError):
                storage.load_predictions()

    def test_prediction_operations_reject_a_broken_prediction_chain(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            path = storage.append_prediction(sample_prediction("p1"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["name"] = "被篡改"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ValueError):
                storage.append_prediction(sample_prediction("p2", code="000001"))
            with self.assertRaises(ValueError):
                storage.append_outcome(sample_outcome("p1"))
            with self.assertRaises(ValueError):
                storage.prediction_exists("p1")

    def test_outcome_operations_reject_a_broken_outcome_chain(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            storage.append_prediction(sample_prediction("p1"))
            path = storage.append_outcome(sample_outcome("p1"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["actual_close"] = 1.0
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ValueError):
                storage.append_outcome(sample_outcome("p2"))
            with self.assertRaises(ValueError):
                storage.load_outcomes()

    def test_prediction_exists_and_outcomes_use_a_separate_chain(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            storage.append_prediction(sample_prediction("p1"))
            outcome_path = storage.append_outcome(sample_outcome("p1"))

            self.assertTrue(storage.prediction_exists("p1"))
            self.assertFalse(storage.prediction_exists("missing"))
            self.assertEqual(
                json.loads(outcome_path.read_text(encoding="utf-8"))["previous_hash"],
                "",
            )
            self.assertEqual(storage.load_outcomes(), [sample_outcome("p1")])


if __name__ == "__main__":
    unittest.main()

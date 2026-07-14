from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from .metrics import summarize_metrics
from .models import OutcomeRecord, PredictionRecord
from .storage import EvaluationStorage


class ReportBuilder:
    def __init__(self, storage: EvaluationStorage, reports_root: Path, pool_size: int = 20):
        self.storage = storage
        self.reports_root = Path(reports_root)
        self.pool_size = pool_size

    def build(self) -> tuple[Path, Path]:
        predictions = self.storage.load_predictions()
        outcomes = self.storage.load_outcomes()
        payload = self._payload(predictions, outcomes)
        json_path = self.reports_root / "summary.json"
        markdown_path = self.reports_root / "summary.md"
        self._replace(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self._replace(markdown_path, self._markdown(payload))
        return json_path, markdown_path

    def _payload(
        self, predictions: list[PredictionRecord], outcomes: list[OutcomeRecord]
    ) -> dict:
        by_id = {record.prediction_id: record for record in predictions}
        settlement_metadata = self._settlement_metadata()
        verified = [outcome for outcome in outcomes if outcome.prediction_id in by_id]
        settled_ids = {outcome.prediction_id for outcome in verified}
        pending = [
            {
                "prediction_id": item.prediction_id,
                "target_trade_date": item.target_trade_date.isoformat(),
                "code": item.code,
                "name": item.name,
                "kind": item.kind,
                "reason": settlement_metadata["pending"].get(
                    item.prediction_id, "not_due_or_missing_bar"
                ),
            }
            for item in sorted(predictions, key=lambda item: item.prediction_id)
            if item.prediction_id not in settled_ids
        ]
        inclusive = self._metrics(verified)
        exclusive_outcomes = [item for item in verified if not item.corporate_action]
        stage_rows = self._stage_rows(predictions, {item.prediction_id: item for item in verified})
        return {
            "samples": len(verified),
            "coverage": {
                "pool_size": self.pool_size,
                "predictions": len(predictions),
                "settled": len(verified),
                "prediction_rate": len(predictions) / self.pool_size if self.pool_size else None,
                "settlement_rate": len(verified) / len(predictions) if predictions else None,
            },
            "metrics": inclusive,
            "corporate_action_inclusive_metrics": inclusive,
            "corporate_action_exclusive_metrics": self._metrics(exclusive_outcomes),
            "rolling": {"5_days": self._rolling(verified, 5), "20_days": self._rolling(verified, 20)},
            "by_stock": self._breakdown(verified, by_id, "code"),
            "by_industry": self._breakdown(verified, by_id, "industry"),
            "by_confidence": self._confidence_breakdown(verified, by_id),
            "maximum_errors": self._maximum_errors(verified, by_id),
            "failed_stocks": self._failed_stocks(verified, by_id),
            "pending_predictions": pending,
            "settlement_warnings": settlement_metadata["warnings"],
            "stage_trend": stage_rows,
        }

    @staticmethod
    def _metrics(outcomes: Iterable[OutcomeRecord]) -> dict:
        values = list(outcomes)
        return {model: asdict(summarize_metrics(values, model)) for model in ("agent", "lstm")}

    def _rolling(self, outcomes: list[OutcomeRecord], count: int) -> dict:
        dates = sorted({item.target_trade_date for item in outcomes})[-count:]
        selected = [item for item in outcomes if item.target_trade_date in dates]
        return {"dates": [item.isoformat() for item in dates], "samples": len(selected), "metrics": self._metrics(selected)}

    def _breakdown(self, outcomes, by_id, field: str) -> list[dict]:
        groups: dict[str, list[OutcomeRecord]] = {}
        for outcome in outcomes:
            key = str(getattr(by_id[outcome.prediction_id], field))
            groups.setdefault(key, []).append(outcome)
        return [
            {field: key, "samples": len(groups[key]), "metrics": self._metrics(groups[key])}
            for key in sorted(groups)
        ]

    def _confidence_breakdown(self, outcomes, by_id) -> list[dict]:
        groups: dict[str, list[OutcomeRecord]] = {"low": [], "medium": [], "high": []}
        for outcome in outcomes:
            confidence = by_id[outcome.prediction_id].agent.confidence
            label = "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"
            groups[label].append(outcome)
        return [{"confidence": key, "samples": len(groups[key]), "metrics": self._metrics(groups[key])} for key in ("low", "medium", "high")]

    @staticmethod
    def _maximum_errors(outcomes, by_id) -> dict:
        result = {}
        for model in ("agent", "lstm"):
            candidates = [(getattr(item, f"{model}_error").absolute_error, item) for item in outcomes]
            if not candidates:
                result[model] = None
                continue
            _, outcome = max(candidates, key=lambda item: (item[0], item[1].prediction_id))
            result[model] = {"prediction_id": outcome.prediction_id, "code": by_id[outcome.prediction_id].code, "absolute_error": getattr(outcome, f"{model}_error").absolute_error}
        return result

    @staticmethod
    def _failed_stocks(outcomes, by_id) -> list[dict]:
        failures = []
        for item in sorted(outcomes, key=lambda item: item.prediction_id):
            failed_models = [
                model for model in ("agent", "lstm")
                if getattr(item, f"{model}_error").direction_hit is False
            ]
            if failed_models:
                failures.append({
                    "prediction_id": item.prediction_id,
                    "code": by_id[item.prediction_id].code,
                    "name": by_id[item.prediction_id].name,
                    "actual_direction": item.actual_direction,
                    "failed_models": failed_models,
                })
        return failures

    def _settlement_metadata(self) -> dict[str, dict]:
        path = self.storage.root / "settlement_pending.json"
        if not path.exists():
            return {"pending": {}, "warnings": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pending = payload.get("pending", {})
            warnings = payload.get("warnings", {})
            if isinstance(pending, dict) and isinstance(warnings, dict):
                return {"pending": pending, "warnings": warnings}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return {"pending": {}, "warnings": {}}

    @staticmethod
    def _stage_rows(predictions, outcomes_by_id) -> list[dict]:
        rows = []
        for item in sorted(predictions, key=lambda value: value.prediction_id):
            if item.kind != "stage":
                continue
            outcome = outcomes_by_id.get(item.prediction_id)
            rows.append({
                "prediction_id": item.prediction_id, "code": item.code, "name": item.name,
                "start_date": item.as_of_trade_date.isoformat(), "start_close": item.current_close,
                "target_date": item.target_trade_date.isoformat(), "target_close": outcome.actual_close if outcome else None,
                "thesis": item.stage_thesis, "catalysts": list(item.catalysts), "risks": list(item.risks),
            })
        return rows

    @staticmethod
    def _replace(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _markdown(payload: dict) -> str:
        agent = payload["metrics"]["agent"]
        lstm = payload["metrics"]["lstm"]
        lines = [
            "# 现实性评测汇总", "", "## 覆盖与样本", "",
            f"- 预测覆盖率：{payload['coverage']['prediction_rate']!s}",
            f"- 已结算样本：{payload['samples']}", "", "## 模型对比", "",
            "| 模型 | 样本 | MAE | 方向准确率 |", "| --- | ---: | ---: | ---: |",
            f"| 完整 Agent | {agent['price_samples']} | {agent['mae']} | {agent['direction_accuracy']} |",
            f"| LSTM | {lstm['price_samples']} | {lstm['mae']} | {lstm['direction_accuracy']} |", "",
            "## 5 日滚动", "", json.dumps(payload["rolling"]["5_days"], ensure_ascii=False, sort_keys=True), "",
            "## 20 日滚动", "", json.dumps(payload["rolling"]["20_days"], ensure_ascii=False, sort_keys=True), "",
            "## 股票、行业与置信度", "", "### 股票", json.dumps(payload["by_stock"], ensure_ascii=False, sort_keys=True), "",
            "### 行业", json.dumps(payload["by_industry"], ensure_ascii=False, sort_keys=True), "",
            "### 置信度", json.dumps(payload["by_confidence"], ensure_ascii=False, sort_keys=True), "",
            "## 最大误差与除权视图", "", json.dumps({"maximum_errors": payload["maximum_errors"], "corporate_action_inclusive_metrics": payload["corporate_action_inclusive_metrics"], "corporate_action_exclusive_metrics": payload["corporate_action_exclusive_metrics"]}, ensure_ascii=False, sort_keys=True), "",
            "## 失败股票", "", json.dumps(payload["failed_stocks"], ensure_ascii=False, sort_keys=True), "",
            "## 待结算预测", "", json.dumps(payload["pending_predictions"], ensure_ascii=False, sort_keys=True), "",
            "## 阶段趋势", "", "| 起点 | 终点 | 代码 | 论点 | 催化剂 | 风险 |", "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in payload["stage_trend"]:
            lines.append(f"| {row['start_date']} {row['start_close']} | {row['target_date']} {row['target_close']} | {row['code']} | {row['thesis'] or ''} | {'；'.join(row['catalysts'])} | {'；'.join(row['risks'])} |")
        return "\n".join(lines) + "\n"

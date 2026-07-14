from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import EvidenceItem, ModelError, ModelForecast, OutcomeRecord, PredictionRecord


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _json_value(value: Any) -> Any:
    if isinstance(value, EvidenceItem):
        return value.to_dict()
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, PredictionRecord):
        # EvidenceItem contains an immutable mapping proxy, so use its public
        # conversion helper instead of asking asdict to deepcopy it.
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _record_payload(record: PredictionRecord | OutcomeRecord) -> dict[str, Any]:
    return _json_value(record)


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _forecast_from_dict(payload: dict[str, Any]) -> ModelForecast:
    return ModelForecast(**payload)


def _error_from_dict(payload: dict[str, Any] | None) -> ModelError | None:
    return ModelError(**payload) if payload is not None else None


def _prediction_from_dict(payload: dict[str, Any]) -> PredictionRecord:
    payload.pop("previous_hash", None)
    payload.pop("content_hash", None)
    evidence = tuple(
        EvidenceItem(
            source=item["source"],
            summary=item.get("summary", ""),
            published_at=_parse_datetime(item.get("published_at")),
            retrieved_at=_parse_datetime(item.get("retrieved_at")),
            evidence_type=item.get("evidence_type", ""),
            metadata=item.get("metadata", {}),
        )
        for item in payload.pop("evidence", [])
    )
    payload["evidence"] = evidence
    payload["generated_at"] = datetime.fromisoformat(payload["generated_at"])
    payload["as_of_trade_date"] = date.fromisoformat(payload["as_of_trade_date"])
    payload["target_trade_date"] = date.fromisoformat(payload["target_trade_date"])
    payload["agent"] = _forecast_from_dict(payload["agent"])
    payload["lstm"] = _forecast_from_dict(payload["lstm"])
    for key in ("warnings", "catalysts", "risks"):
        payload[key] = tuple(payload.get(key, ()))
    return PredictionRecord(**payload)


def _outcome_from_dict(payload: dict[str, Any]) -> OutcomeRecord:
    payload.pop("previous_hash", None)
    payload.pop("content_hash", None)
    payload["target_trade_date"] = date.fromisoformat(payload["target_trade_date"])
    payload["agent_error"] = _error_from_dict(payload.get("agent_error"))
    payload["lstm_error"] = _error_from_dict(payload.get("lstm_error"))
    return OutcomeRecord(**payload)


class EvaluationStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def append_prediction(self, record: PredictionRecord) -> Path:
        return self._append(
            "predictions",
            self.root / "predictions" / record.as_of_trade_date.isoformat() / f"{record.code}-{record.kind}.json",
            record,
        )

    def append_outcome(self, record: OutcomeRecord) -> Path:
        prediction_hash = hashlib.sha256(record.prediction_id.encode("utf-8")).hexdigest()
        return self._append(
            "outcomes",
            self.root / "outcomes" / record.target_trade_date.isoformat() / f"{prediction_hash}.json",
            record,
        )

    def _append(self, chain: str, path: Path, record: PredictionRecord | OutcomeRecord) -> Path:
        payload = _record_payload(record)
        payload["previous_hash"] = self._chain_head(chain)
        payload["content_hash"] = _hash_payload(payload)
        _write_new_json(path, payload)
        return path

    def _chain_files(self, chain: str) -> list[Path]:
        directory = self.root / chain
        return sorted(directory.glob("*/*.json")) if directory.exists() else []

    def _chain_head(self, chain: str) -> str:
        files = self._chain_files(chain)
        if not files:
            return ""
        payload = json.loads(files[-1].read_text(encoding="utf-8"))
        return payload.get("content_hash", "")

    def verify_chain(self) -> dict[str, Any]:
        results: dict[str, Any] = {"ok": True}
        for chain in ("predictions", "outcomes"):
            previous_hash = ""
            for path in self._chain_files(chain):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    content_hash = payload["content_hash"]
                    actual_hash = _hash_payload(
                        {key: value for key, value in payload.items() if key != "content_hash"}
                    )
                    if payload.get("previous_hash", "") != previous_hash or content_hash != actual_hash:
                        raise ValueError(f"broken {chain} chain at {path}")
                    previous_hash = content_hash
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    results.update({"ok": False, "chain": chain, "path": str(path), "error": str(exc)})
                    return results
        return results

    def prediction_exists(self, prediction_id: str) -> bool:
        for path in self._chain_files("predictions"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("prediction_id") == prediction_id:
                return True
        return False

    def load_predictions(self) -> list[PredictionRecord]:
        self._require_valid_chain("predictions")
        return [
            _prediction_from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in self._chain_files("predictions")
        ]

    def load_outcomes(self) -> list[OutcomeRecord]:
        self._require_valid_chain("outcomes")
        return [
            _outcome_from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in self._chain_files("outcomes")
        ]

    def _require_valid_chain(self, chain: str) -> None:
        verification = self.verify_chain()
        if not verification["ok"] or verification.get("chain") == chain:
            if not verification["ok"]:
                raise ValueError(verification["error"])

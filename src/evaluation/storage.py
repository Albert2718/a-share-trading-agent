from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import EvidenceItem, ModelError, ModelForecast, OutcomeRecord, PredictionRecord


SUPPORTED_PREDICTION_KINDS = frozenset({"next_day", "stage"})
_STOCK_CODE_PATTERN = re.compile(r"[0-9]{6}")
_MANIFEST_NAME = "manifest.json"
_EMPTY_HASH = ""

ChainEntry = tuple[int, Path, dict[str, Any]]


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_json(handle: Any, payload: dict[str, Any]) -> None:
    json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        _write_json(handle, payload)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            _write_json(handle, payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_value(value: Any) -> Any:
    if isinstance(value, EvidenceItem):
        return value.to_dict()
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, PredictionRecord):
        # EvidenceItem contains an immutable mapping proxy, so use its public
        # conversion helper instead of asking asdict to deepcopy it.
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
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
    payload = dict(payload)
    payload.pop("sequence", None)
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
    payload = dict(payload)
    payload.pop("sequence", None)
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
        path = self._prediction_path(record)
        entries = self._require_valid_chain("predictions")
        return self._append("predictions", path, record, entries)

    def append_outcome(self, record: OutcomeRecord) -> Path:
        self._require_valid_chain("predictions")
        entries = self._require_valid_chain("outcomes")
        prediction_hash = hashlib.sha256(record.prediction_id.encode("utf-8")).hexdigest()
        path = (
            self.root
            / "outcomes"
            / record.target_trade_date.isoformat()
            / f"{prediction_hash}.json"
        )
        self._require_contained(path, self.root / "outcomes")
        return self._append("outcomes", path, record, entries)

    def _prediction_path(self, record: PredictionRecord) -> Path:
        if _STOCK_CODE_PATTERN.fullmatch(record.code) is None:
            raise ValueError("prediction code must contain exactly six ASCII digits")
        if record.kind not in SUPPORTED_PREDICTION_KINDS:
            supported = ", ".join(sorted(SUPPORTED_PREDICTION_KINDS))
            raise ValueError(f"unsupported prediction kind; expected one of: {supported}")
        path = (
            self.root
            / "predictions"
            / record.as_of_trade_date.isoformat()
            / f"{record.code}-{record.kind}.json"
        )
        self._require_contained(path, self.root / "predictions")
        return path

    @staticmethod
    def _require_contained(path: Path, directory: Path) -> None:
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError(f"storage path escapes {directory}")

    def _append(
        self,
        chain: str,
        path: Path,
        record: PredictionRecord | OutcomeRecord,
        entries: list[ChainEntry],
    ) -> Path:
        sequence = len(entries) + 1
        previous_hash = entries[-1][2]["content_hash"] if entries else _EMPTY_HASH
        payload = _record_payload(record)
        payload["sequence"] = sequence
        payload["previous_hash"] = previous_hash
        payload["content_hash"] = _hash_payload(payload)
        _write_new_json(path, payload)
        self._write_manifest(chain, sequence, payload["content_hash"])
        return path

    def _chain_directory(self, chain: str) -> Path:
        if chain not in {"predictions", "outcomes"}:
            raise ValueError(f"unknown storage chain: {chain}")
        return self.root / chain

    def _manifest_path(self, chain: str) -> Path:
        return self._chain_directory(chain) / _MANIFEST_NAME

    def _record_paths(self, chain: str) -> list[Path]:
        directory = self._chain_directory(chain)
        if not directory.exists():
            return []
        manifest = self._manifest_path(chain)
        return [path for path in directory.rglob("*.json") if path != manifest]

    def _write_manifest(self, chain: str, count: int, final_hash: str) -> None:
        _write_json_atomic(
            self._manifest_path(chain),
            {"count": count, "final_hash": final_hash},
        )

    def _inspect_chain(self, chain: str) -> tuple[dict[str, Any], list[ChainEntry]]:
        manifest_path = self._manifest_path(chain)
        record_paths = self._record_paths(chain)
        try:
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                count = manifest["count"]
                final_hash = manifest["final_hash"]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("manifest count must be a non-negative integer")
                if not isinstance(final_hash, str):
                    raise ValueError("manifest final_hash must be a string")
            elif record_paths:
                raise ValueError("chain manifest is missing")
            else:
                return {"ok": True}, []

            entries: list[ChainEntry] = []
            for path in record_paths:
                payload = json.loads(path.read_text(encoding="utf-8"))
                sequence = payload["sequence"]
                if (
                    isinstance(sequence, bool)
                    or not isinstance(sequence, int)
                    or sequence < 1
                ):
                    raise ValueError(f"invalid sequence at {path}")
                entries.append((sequence, path, payload))
            entries.sort(key=lambda entry: entry[0])

            if count != len(entries):
                raise ValueError(
                    f"manifest count {count} does not match {len(entries)} records"
                )

            previous_hash = _EMPTY_HASH
            for expected_sequence, (sequence, path, payload) in enumerate(entries, 1):
                if sequence != expected_sequence:
                    raise ValueError(
                        f"expected sequence {expected_sequence}, found {sequence} at {path}"
                    )
                content_hash = payload["content_hash"]
                actual_hash = _hash_payload(
                    {
                        key: value
                        for key, value in payload.items()
                        if key != "content_hash"
                    }
                )
                if payload.get("previous_hash") != previous_hash:
                    raise ValueError(f"broken previous hash at {path}")
                if content_hash != actual_hash:
                    raise ValueError(f"broken content hash at {path}")
                previous_hash = content_hash

            if final_hash != previous_hash:
                raise ValueError("manifest final_hash does not match chain head")
            return {"ok": True}, entries
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return (
                {
                    "ok": False,
                    "chain": chain,
                    "path": str(manifest_path),
                    "error": str(exc),
                },
                [],
            )

    def verify_chain(self) -> dict[str, Any]:
        for chain in ("predictions", "outcomes"):
            verification, _ = self._inspect_chain(chain)
            if not verification["ok"]:
                return verification
        return {"ok": True}

    def _require_valid_chain(self, chain: str) -> list[ChainEntry]:
        verification, entries = self._inspect_chain(chain)
        if not verification["ok"]:
            raise ValueError(verification["error"])
        return entries

    def prediction_exists(self, prediction_id: str) -> bool:
        entries = self._require_valid_chain("predictions")
        return any(
            payload.get("prediction_id") == prediction_id
            for _, _, payload in entries
        )

    def load_predictions(self) -> list[PredictionRecord]:
        entries = self._require_valid_chain("predictions")
        return [_prediction_from_dict(payload) for _, _, payload in entries]

    def load_outcomes(self) -> list[OutcomeRecord]:
        entries = self._require_valid_chain("outcomes")
        return [_outcome_from_dict(payload) for _, _, payload in entries]

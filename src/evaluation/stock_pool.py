from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from .models import StockPoolEntry


RULE_VERSION = "1.0"
POOL_SIZE = 20
MIN_VALID_ROWS = 250
RAW_HISTORY_DAYS = 760
LIQUIDITY_DAYS = 60


class PoolMarketData(Protocol):
    def csi300_constituents(self) -> list[dict[str, Any]]: ...

    def industry_map(self) -> dict[str, str]: ...

    def trade_dates(self) -> list[date]: ...

    def raw_history(self, code: str, days: int, end_date: date) -> pd.DataFrame: ...


class StockPoolManager:
    def __init__(self, provider: PoolMarketData) -> None:
        self.provider = provider
        self._liquidity_sources: dict[str, str] = {}
        self._source_date: date | None = None

    def select(self, selected_at: datetime) -> list[StockPoolEntry]:
        constituents = self.provider.csi300_constituents()
        industries = self.provider.industry_map()
        if not constituents:
            raise RuntimeError("CSI 300 constituent list is empty")

        end_date = selected_at.date()
        expected_trade_date = self._latest_trade_date(
            self.provider.trade_dates(), end_date
        )
        candidates = []
        source_dates = [
            source_date
            for row in constituents
            if (source_date := self._parse_date(row.get("source_date"))) is not None
        ]
        self._source_date = max(source_dates, default=end_date)
        for row in constituents:
            code = str(row.get("code", "")).zfill(6)
            name = str(row.get("name", "")).strip()
            industry = str(industries.get(code, "")).strip()
            if not code.isascii() or not code.isdigit() or len(code) != 6:
                continue
            if self._excluded_name(name) or not industry:
                continue
            history = self.provider.raw_history(code, RAW_HISTORY_DAYS, end_date)
            candidate = self._candidate_from_history(
                code,
                name,
                industry,
                history,
                selected_at,
                expected_trade_date,
            )
            if candidate is not None:
                candidates.append(candidate)

        ordered = sorted(candidates, key=lambda entry: (-entry.liquidity, entry.code))
        winners = self._industry_winners(ordered)
        selected = winners[:POOL_SIZE]
        counts = Counter(entry.industry for entry in selected)
        if len(selected) < POOL_SIZE:
            selected_codes = {entry.code for entry in selected}
            for entry in ordered:
                if entry.code in selected_codes or counts[entry.industry] >= 2:
                    continue
                selected.append(entry)
                selected_codes.add(entry.code)
                counts[entry.industry] += 1
                if len(selected) == POOL_SIZE:
                    break
        result = sorted(selected, key=lambda entry: (-entry.liquidity, entry.code))
        self._require_complete_pool(result)
        return result

    def freeze(self, path: Path, selected_at: datetime) -> list[StockPoolEntry]:
        path = Path(path)
        if path.exists():
            return self.load(path)
        entries = self.select(selected_at)
        payload = {
            "rule_version": RULE_VERSION,
            "constituent_source_date": self._source_date.isoformat() if self._source_date else selected_at.date().isoformat(),
            "selected_at": selected_at.isoformat(),
            "criteria": {
                "target_size": POOL_SIZE,
                "minimum_valid_rows": MIN_VALID_ROWS,
                "minimum_listing_years": 2,
                "liquidity_days": LIQUIDITY_DAYS,
                "maximum_per_industry_after_fill": 2,
            },
            "entries": [
                {
                    **self._entry_payload(entry),
                    "liquidity_source": self._liquidity_sources.get(entry.code, "amount"),
                }
                for entry in entries
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        except FileExistsError:
            return self.load(path)
        return entries

    def load(self, path: Path) -> list[StockPoolEntry]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload.get("rule_version") != RULE_VERSION:
                raise ValueError("unsupported stock pool rule version")
            selected_at = datetime.fromisoformat(payload["selected_at"])
            source_date = date.fromisoformat(payload["constituent_source_date"])
            rows = payload["entries"]
            if not isinstance(rows, list):
                raise ValueError("stock pool entries must be a list")
            self._require_complete_pool_rows(rows)
            entries = [
                StockPoolEntry(
                    code=str(row["code"]),
                    name=str(row["name"]),
                    industry=str(row["industry"]),
                    liquidity=float(row["liquidity"]),
                    source_date=date.fromisoformat(row.get("source_date") or source_date.isoformat()),
                    selected_at=datetime.fromisoformat(row.get("selected_at") or selected_at.isoformat()),
                    selection_reason=str(row.get("selection_reason", "")),
                    rule_version=str(row.get("rule_version") or RULE_VERSION),
                )
                for row in rows
            ]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid frozen stock pool: {path}") from exc
        return entries

    def _candidate_from_history(
        self,
        code: str,
        name: str,
        industry: str,
        history: pd.DataFrame,
        selected_at: datetime,
        expected_trade_date: date,
    ) -> StockPoolEntry | None:
        if not isinstance(history, pd.DataFrame) or history.empty:
            return None
        required = {"date", "close", "volume"}
        if not required.issubset(history.columns):
            return None
        frame = history.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        for column in ("close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        last_row = frame.iloc[-1]
        last_close = last_row["close"]
        if (
            pd.isna(last_row["date"])
            or pd.isna(last_close)
            or not math.isfinite(float(last_close))
            or float(last_close) <= 0
            or last_row["date"].date() != expected_trade_date
        ):
            return None
        valid = frame.dropna(subset=["date", "close", "volume"])
        if len(valid) < MIN_VALID_ROWS or valid.empty:
            return None
        listing_cutoff = self._two_years_before(selected_at.date())
        if valid["date"].min().date() > listing_cutoff:
            return None
        recent = valid.tail(LIQUIDITY_DAYS)
        if recent.empty or recent["close"].iloc[-1] <= 0 or recent["volume"].sum() <= 0:
            return None
        if "amount" in recent:
            amount = pd.to_numeric(recent["amount"], errors="coerce")
            if amount.isna().any():
                return None
            liquidity = float(amount.mean())
            source = "amount"
        else:
            liquidity = float((recent["close"] * recent["volume"]).mean())
            source = "close_x_volume"
        if not math.isfinite(liquidity) or liquidity <= 0:
            return None
        self._liquidity_sources[code] = source
        return StockPoolEntry(
            code=code,
            name=name,
            industry=industry,
            liquidity=liquidity,
            source_date=self._source_date,
            selected_at=selected_at,
            selection_reason="industry_liquidity_winner",
            rule_version=RULE_VERSION,
        )

    @staticmethod
    def _industry_winners(entries: list[StockPoolEntry]) -> list[StockPoolEntry]:
        winners: list[StockPoolEntry] = []
        seen: set[str] = set()
        for entry in entries:
            if entry.industry in seen:
                continue
            seen.add(entry.industry)
            winners.append(entry)
        return winners

    @staticmethod
    def _excluded_name(name: str) -> bool:
        normalized = name.upper().lstrip("*")
        return normalized.startswith("ST") or "退市" in name

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value:
            try:
                return date.fromisoformat(str(value))
            except ValueError:
                return None
        return None

    @staticmethod
    def _two_years_before(value: date) -> date:
        try:
            return value.replace(year=value.year - 2)
        except ValueError:
            return value.replace(year=value.year - 2, day=28)

    @classmethod
    def _latest_trade_date(cls, values: list[date], as_of: date) -> date:
        eligible = [
            parsed
            for value in values
            if (parsed := cls._parse_date(value)) is not None and parsed <= as_of
        ]
        if not eligible:
            raise RuntimeError(f"no trade date on or before {as_of.isoformat()}")
        return max(eligible)

    @staticmethod
    def _entry_payload(entry: StockPoolEntry) -> dict[str, Any]:
        payload = asdict(entry)
        payload["source_date"] = entry.source_date.isoformat() if entry.source_date else None
        payload["selected_at"] = entry.selected_at.isoformat() if entry.selected_at else None
        return payload

    @staticmethod
    def _require_complete_pool(entries: list[StockPoolEntry]) -> None:
        codes = [entry.code for entry in entries]
        if len(entries) != POOL_SIZE or len(set(codes)) != POOL_SIZE:
            raise RuntimeError("stock pool must contain exactly 20 unique stocks")

    @staticmethod
    def _require_complete_pool_rows(rows: list[Any]) -> None:
        if len(rows) != POOL_SIZE or not all(isinstance(row, dict) for row in rows):
            raise ValueError("stock pool must contain exactly 20 unique stocks")
        codes = [str(row.get("code", "")) for row in rows]
        if (
            len(set(codes)) != POOL_SIZE
            or any(len(code) != 6 or not code.isascii() or not code.isdigit() for code in codes)
        ):
            raise ValueError("stock pool must contain exactly 20 unique stocks")

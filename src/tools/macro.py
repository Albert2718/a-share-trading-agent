from __future__ import annotations

import re
from typing import Any, Dict, List

import pandas as pd

from src.core import DataAccessLayer


def _records(df: pd.DataFrame | None) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.copy().where(pd.notnull(df), None)
    return [{str(k): (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in clean.to_dict(orient="records")]


def _fetch(endpoint: str, ttl: int, loader):
    return DataAccessLayer().fetch("akshare", endpoint, "all", ttl, 2.0, loader)


def _error(source: str, exc: Exception | str) -> Dict[str, Any]:
    return {"ok": False, "source": source, "error": str(exc), "items": []}


def _latest_rows(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    def sort_key(row: Dict[str, Any]):
        text = str(row.get("日期") or row.get("月份") or row.get("季度") or "")
        nums = [int(item) for item in re.findall(r"\d+", text)]
        if not nums:
            return (0, 0, 0)
        year = nums[0]
        period = nums[-1] if len(nums) > 1 else 0
        return (year, period, len(nums))

    return sorted(rows, key=sort_key, reverse=True)[:limit]


def get_macro_gdp(limit: int = 8) -> Dict[str, Any]:
    """Return China GDP data."""
    limit = max(1, min(int(limit or 8), 40))
    try:
        def loader():
            import akshare as ak  # type: ignore

            return _records(ak.macro_china_gdp())

        rows = _fetch("macro_china_gdp", 86400, loader)
    except Exception as exc:
        return _error("akshare_macro_china_gdp", exc)
    return {"ok": bool(rows), "items": _latest_rows(rows, limit), "source": "akshare_macro_china_gdp"}


def get_macro_cpi(limit: int = 12) -> Dict[str, Any]:
    """Return China CPI data."""
    limit = max(1, min(int(limit or 12), 60))
    try:
        def loader():
            import akshare as ak  # type: ignore

            return _records(ak.macro_china_cpi())

        rows = _fetch("macro_china_cpi", 86400, loader)
    except Exception as exc:
        return _error("akshare_macro_china_cpi", exc)
    return {"ok": bool(rows), "items": _latest_rows(rows, limit), "source": "akshare_macro_china_cpi"}


def get_macro_m2(limit: int = 12) -> Dict[str, Any]:
    """Return China money supply data including M2 if provided by source."""
    limit = max(1, min(int(limit or 12), 60))
    try:
        def loader():
            import akshare as ak  # type: ignore

            return _records(ak.macro_china_money_supply())

        rows = _fetch("macro_china_money_supply", 86400, loader)
    except Exception as exc:
        return _error("akshare_macro_china_money_supply", exc)
    return {"ok": bool(rows), "items": _latest_rows(rows, limit), "source": "akshare_macro_china_money_supply"}


def get_macro_interest_rate(limit: int = 20) -> Dict[str, Any]:
    """Return China SHIBOR/interbank rate data."""
    limit = max(1, min(int(limit or 20), 80))
    try:
        def loader():
            import akshare as ak  # type: ignore

            return _records(ak.macro_china_shibor_all())

        rows = _fetch("macro_china_shibor_all", 86400, loader)
    except Exception as exc:
        return _error("akshare_macro_china_shibor_all", exc)
    return {"ok": bool(rows), "items": _latest_rows(rows, limit), "source": "akshare_macro_china_shibor_all"}

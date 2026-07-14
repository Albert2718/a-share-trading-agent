from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd

from src.core import DataAccessLayer
from src.tools.deep_research.tools import AkshareTools
from src.tools.deep_research.utils import normalize_a_share_code, safe_float


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        key: (value.item() if hasattr(value, "item") else value)
        for key, value in row.items()
    }


def get_realtime_price(code: str) -> Dict[str, Any]:
    """Return the latest available A-share price from cached daily data."""
    tools = AkshareTools()
    norm = normalize_a_share_code(code)
    candidate = tools.candidates_from_codes([norm])[0]
    history = tools.history(norm, days=8)
    if history.empty:
        return {"ok": False, "code": norm, "error": "no market data"}
    latest = _row_to_dict(history.iloc[-1])
    previous_close = safe_float(history.iloc[-2]["close"]) if len(history) >= 2 else None
    latest_close = safe_float(latest.get("close"))
    change = latest_close - previous_close if latest_close is not None and previous_close is not None else None
    change_pct = change / previous_close if change is not None and previous_close not in (None, 0) else None
    return {
        "ok": True,
        "code": norm,
        "name": candidate.name,
        "date": str(latest.get("date", "")),
        "latest_close": latest_close,
        "open": safe_float(latest.get("open")),
        "high": safe_float(latest.get("high")),
        "low": safe_float(latest.get("low")),
        "volume": safe_float(latest.get("volume")),
        "change": change,
        "change_pct": change_pct,
        "source": "akshare_daily_latest",
    }


def get_daily_price(code: str, days: int = 7) -> Dict[str, Any]:
    """Return recent daily OHLCV records."""
    tools = AkshareTools()
    norm = normalize_a_share_code(code)
    days = max(1, min(int(days or 7), 120))
    history = tools.history(norm, days=days)
    records: List[Dict[str, Any]] = []
    for _, row in history.iterrows():
        records.append(
            {
                "date": str(row["date"]),
                "open": safe_float(row["open"]),
                "high": safe_float(row["high"]),
                "low": safe_float(row["low"]),
                "close": safe_float(row["close"]),
                "volume": safe_float(row["volume"]),
            }
        )
    return {"ok": bool(records), "code": norm, "days": days, "records": records, "source": "akshare_history"}


def get_market_index(index_code: str = "000001", days: int = 5) -> Dict[str, Any]:
    """Return recent index data for common China A-share indices."""
    code = normalize_a_share_code(index_code or "000001")
    days = max(1, min(int(days or 5), 60))
    data_access = DataAccessLayer()
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days * 3)).strftime("%Y%m%d")

    def loader():
        import akshare as ak  # type: ignore

        df = ak.index_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end)
        if df is None or df.empty:
            return []
        clean = df.where(pd.notnull(df), None)
        return [{str(k): v for k, v in row.items()} for row in clean.to_dict(orient="records")]

    records = data_access.fetch("akshare", "index_zh_a_hist", f"{code}_{days}", 1800, 1.5, loader)
    normalized = []
    for row in records[-days:]:
        normalized.append(
            {
                "date": str(row.get("日期") or row.get("date") or ""),
                "open": safe_float(row.get("开盘") or row.get("open")),
                "high": safe_float(row.get("最高") or row.get("high")),
                "low": safe_float(row.get("最低") or row.get("low")),
                "close": safe_float(row.get("收盘") or row.get("close")),
                "volume": safe_float(row.get("成交量") or row.get("volume")),
            }
        )
    return {"ok": bool(normalized), "index_code": code, "days": days, "records": normalized, "source": "akshare_index"}

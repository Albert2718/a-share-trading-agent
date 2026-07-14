from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd

from src.core import DataAccessLayer
from src.tools.market_data import AkshareMarketData
from src.tools.utils import normalize_a_share_code, safe_float


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        key: (value.item() if hasattr(value, "item") else value)
        for key, value in row.items()
    }


def _regular_market_session(quote_time: str) -> str:
    try:
        quoted_at = datetime.fromisoformat(str(quote_time))
    except (TypeError, ValueError):
        return "unknown"
    minute_of_day = quoted_at.hour * 60 + quoted_at.minute
    in_morning = 9 * 60 + 30 <= minute_of_day <= 11 * 60 + 30
    in_afternoon = 13 * 60 <= minute_of_day <= 15 * 60
    if quoted_at.weekday() < 5 and (in_morning or in_afternoon):
        return "within_regular_trading_hours"
    return "outside_regular_trading_hours"


def get_realtime_price(code: str) -> Dict[str, Any]:
    """Return an A-share realtime quote, falling back to the latest daily close."""
    tools = AkshareMarketData()
    norm = normalize_a_share_code(code)
    try:
        quote = tools.realtime_quote(norm)
    except Exception:
        quote = {}
    latest_price = safe_float(quote.get("latest_price"))
    if latest_price is not None:
        quote_time = str(quote.get("quote_time") or "")
        return {
            "ok": True,
            "is_realtime": True,
            "code": norm,
            "name": str(quote.get("name") or ""),
            "quote_time": quote_time,
            "market_session": _regular_market_session(quote_time),
            "data_freshness": str(quote.get("data_freshness") or "live"),
            "quote_age_seconds": safe_float(quote.get("quote_age_seconds"), 0),
            "latest_price": latest_price,
            "latest_close": latest_price,
            "previous_close": safe_float(quote.get("previous_close")),
            "open": safe_float(quote.get("open")),
            "high": safe_float(quote.get("high")),
            "low": safe_float(quote.get("low")),
            "volume": safe_float(quote.get("volume")),
            "volume_unit": str(quote.get("volume_unit") or "shares"),
            "amount": safe_float(quote.get("amount")),
            "change": safe_float(quote.get("change")),
            "change_pct": safe_float(quote.get("change_pct")),
            "change_pct_unit": "percent",
            "source": str(quote.get("source") or "akshare_realtime"),
        }

    history = tools.history(norm, days=8)
    if history.empty:
        return {"ok": False, "is_realtime": False, "code": norm, "error": "no market data"}
    candidate = tools.candidates_from_codes([norm])[0]
    latest = _row_to_dict(history.iloc[-1])
    previous_close = safe_float(history.iloc[-2]["close"]) if len(history) >= 2 else None
    latest_close = safe_float(latest.get("close"))
    change = latest_close - previous_close if latest_close is not None and previous_close is not None else None
    change_pct = change / previous_close * 100 if change is not None and previous_close not in (None, 0) else None
    return {
        "ok": True,
        "is_realtime": False,
        "code": norm,
        "name": str(candidate.get("name") or ""),
        "date": str(latest.get("date", "")),
        "quote_time": str(latest.get("date", "")),
        "market_session": "historical_fallback",
        "data_freshness": "historical",
        "latest_price": latest_close,
        "latest_close": latest_close,
        "open": safe_float(latest.get("open")),
        "high": safe_float(latest.get("high")),
        "low": safe_float(latest.get("low")),
        "volume": safe_float(latest.get("volume")),
        "change": change,
        "change_pct": change_pct,
        "change_pct_unit": "percent",
        "source": "akshare_daily_fallback",
        "warning": "realtime quote unavailable; using latest daily close",
    }


def get_daily_price(code: str, days: int = 7) -> Dict[str, Any]:
    """Return recent daily OHLCV records."""
    tools = AkshareMarketData()
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

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd

from src.core import DataAccessLayer
from src.tools.financial import get_stock_basic, get_valuation
from src.tools.market_data import AkshareMarketData
from src.tools.utils import normalize_a_share_code, safe_float


def _records(df: pd.DataFrame | None) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.copy().where(pd.notnull(df), None)
    return [{str(k): (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in clean.to_dict(orient="records")]


def _pick(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _fetch(endpoint: str, key: str, ttl: int, min_interval: float, loader):
    return DataAccessLayer().fetch("akshare", endpoint, key, ttl, min_interval, loader)


def _market_snapshot() -> List[Dict[str, Any]]:
    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_zh_a_spot_em())

    return _fetch("stock_zh_a_spot_em", "all", 900, 2.0, loader)


def screen_stocks(
    pe_max: float | None = None,
    pe_min: float | None = None,
    pb_max: float | None = None,
    market_cap_min: float | None = None,
    industry_keyword: str | None = None,
    top: int = 20,
) -> Dict[str, Any]:
    """Screen A-share snapshot by valuation, market cap and industry/name keyword."""
    top = max(1, min(int(top or 20), 100))
    try:
        rows = _market_snapshot()
    except Exception as exc:
        fallback = _screen_by_name_detail(
            pe_max=pe_max,
            pe_min=pe_min,
            pb_max=pb_max,
            market_cap_min=market_cap_min,
            industry_keyword=industry_keyword,
            top=top,
        )
        if fallback.get("ok"):
            fallback["primary_error"] = str(exc)
            return fallback
        return {"ok": False, "source": "akshare_stock_zh_a_spot_em", "error": str(exc), "items": []}

    pe_max_v = safe_float(pe_max)
    pe_min_v = safe_float(pe_min)
    pb_max_v = safe_float(pb_max)
    cap_min_v = safe_float(market_cap_min)
    keyword = str(industry_keyword or "").strip()
    items = []
    for row in rows:
        code = _pick(row, ["代码", "股票代码"])
        name = str(_pick(row, ["名称", "股票名称"]) or "")
        pe = safe_float(_pick(row, ["市盈率-动态", "市盈率", "PE"]))
        pb = safe_float(_pick(row, ["市净率", "PB"]))
        market_cap = safe_float(_pick(row, ["总市值"]))
        if pe_max_v is not None and (pe is None or pe > pe_max_v):
            continue
        if pe_min_v is not None and (pe is None or pe < pe_min_v):
            continue
        if pb_max_v is not None and (pb is None or pb > pb_max_v):
            continue
        if cap_min_v is not None and (market_cap is None or market_cap < cap_min_v):
            continue
        if keyword and keyword not in name and keyword not in str(row):
            continue
        items.append(
            {
                "code": normalize_a_share_code(str(code)) if code else None,
                "name": name,
                "latest_price": safe_float(_pick(row, ["最新价"])),
                "change_pct": safe_float(_pick(row, ["涨跌幅"])),
                "pe": pe,
                "pb": pb,
                "market_cap": market_cap,
                "raw": row,
            }
        )
    items.sort(key=lambda item: (item.get("market_cap") is None, -(item.get("market_cap") or 0)))
    return {
        "ok": True,
        "filters": {
            "pe_min": pe_min_v,
            "pe_max": pe_max_v,
            "pb_max": pb_max_v,
            "market_cap_min": cap_min_v,
            "industry_keyword": keyword or None,
        },
        "count": len(items),
        "top": top,
        "items": items[:top],
        "source": "akshare_stock_zh_a_spot_em",
    }


def _screen_by_name_detail(
    pe_max: float | None,
    pe_min: float | None,
    pb_max: float | None,
    market_cap_min: float | None,
    industry_keyword: str | None,
    top: int,
) -> Dict[str, Any]:
    keyword = str(industry_keyword or "").strip()
    if not keyword:
        return {"ok": False, "source": "fallback_stock_detail", "error": "fallback requires industry_keyword", "items": []}
    try:
        names = AkshareMarketData().stock_names()
    except Exception as exc:
        return {"ok": False, "source": "fallback_stock_detail", "error": str(exc), "items": []}

    candidates = [(code, name) for code, name in names.items() if keyword in name]
    if not candidates:
        return {"ok": False, "source": "fallback_stock_detail", "error": "no keyword candidates", "items": []}

    pe_max_v = safe_float(pe_max)
    pe_min_v = safe_float(pe_min)
    pb_max_v = safe_float(pb_max)
    cap_min_v = safe_float(market_cap_min)
    items = []
    errors = []
    for code, name in candidates[:80]:
        try:
            valuation = get_valuation(code)
            basic = get_stock_basic(code)
        except Exception as exc:
            errors.append({"code": code, "error": str(exc)})
            continue
        pe = safe_float(valuation.get("pe_ttm"))
        pb = safe_float(valuation.get("pb"))
        market_cap = safe_float(basic.get("total_market_cap"))
        if market_cap is None:
            market_cap = safe_float((valuation.get("raw") or {}).get("总市值"))
        if pe_max_v is not None and (pe is None or pe > pe_max_v):
            continue
        if pe_min_v is not None and (pe is None or pe < pe_min_v):
            continue
        if pb_max_v is not None and (pb is None or pb > pb_max_v):
            continue
        if cap_min_v is not None and (market_cap is None or market_cap < cap_min_v):
            continue
        items.append(
            {
                "code": normalize_a_share_code(code),
                "name": name,
                "pe": pe,
                "pb": pb,
                "market_cap": market_cap,
                "industry": basic.get("industry") or keyword,
                "source_detail": {
                    "valuation_source": valuation.get("source"),
                    "basic_source": basic.get("source"),
                },
            }
        )

    items.sort(key=lambda item: (item.get("market_cap") is None, -(item.get("market_cap") or 0)))
    return {
        "ok": bool(items),
        "filters": {
            "pe_min": pe_min_v,
            "pe_max": pe_max_v,
            "pb_max": pb_max_v,
            "market_cap_min": cap_min_v,
            "industry_keyword": keyword,
        },
        "count": len(items),
        "top": top,
        "items": items[:top],
        "errors": errors[:5],
        "source": "fallback_stock_names+valuation+stock_individual_info",
        "error": None if items else "fallback found no matching stocks",
    }


def run_backtest(code: str, strategy: str = "macd", days: int = 250) -> Dict[str, Any]:
    """Run a simple daily-bar backtest for MACD or moving-average crossover."""
    norm = normalize_a_share_code(code)
    strategy = (strategy or "macd").lower()
    days = max(30, min(int(days or 250), 800))
    try:
        history = AkshareMarketData().history(norm, days=days)
    except Exception as exc:
        return {"ok": False, "code": norm, "strategy": strategy, "error": str(exc), "source": "akshare_history_calculated"}
    if history.empty or len(history) < 30:
        return {"ok": False, "code": norm, "strategy": strategy, "error": "not enough history", "source": "akshare_history_calculated"}

    df = history.copy()
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if strategy in {"macd", "macd_cross"}:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        signal = (dif > dea).astype(int)
        strategy_name = "macd_cross"
    elif strategy in {"ma", "ma_cross", "sma"}:
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        signal = (ma5 > ma20).astype(int)
        strategy_name = "ma_cross"
    else:
        return {"ok": False, "code": norm, "strategy": strategy, "error": "supported strategies: macd, ma_cross"}

    daily_ret = close.pct_change().fillna(0)
    position = signal.shift(1).fillna(0)
    strategy_ret = position * daily_ret
    equity = (1 + strategy_ret).cumprod()
    benchmark = (1 + daily_ret).cumprod()
    drawdown = equity / equity.cummax() - 1
    trades = int((signal.diff().abs() == 1).sum())
    last_date = str(df.iloc[-1]["date"])
    first_date = str(df.iloc[max(0, len(df) - len(close))]["date"])
    return {
        "ok": True,
        "code": norm,
        "strategy": strategy_name,
        "start_date": first_date,
        "end_date": last_date,
        "days": len(close),
        "total_return": float(equity.iloc[-1] - 1),
        "benchmark_return": float(benchmark.iloc[-1] - 1),
        "max_drawdown": float(drawdown.min()),
        "trades": trades,
        "latest_signal": "hold" if int(signal.iloc[-1]) == 1 else "cash",
        "source": "akshare_history_calculated",
        "note": "Simple educational backtest without transaction costs or slippage.",
    }

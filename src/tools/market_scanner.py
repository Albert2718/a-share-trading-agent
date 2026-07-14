from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd

from src.core import DataAccessLayer
from src.tools.utils import normalize_a_share_code, safe_float


def _records(df: pd.DataFrame | None) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.copy().where(pd.notnull(df), None)
    return [{str(key): _json_safe(value) for key, value in row.items()} for row in clean.to_dict(orient="records")]


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _pick(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _recent_trade_dates(start: str | None = None, count: int = 5) -> List[str]:
    current = datetime.strptime(start or _today_yyyymmdd(), "%Y%m%d")
    dates = []
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y%m%d"))
        current -= timedelta(days=1)
    return dates


def _fetch(function_name: str, cache_key: str, ttl: int, min_interval: float, loader):
    return DataAccessLayer().fetch("akshare", function_name, cache_key, ttl, min_interval, loader)


def _source_error(source: str, error: Exception | str, **extra) -> Dict[str, Any]:
    payload = {"ok": False, "source": source, "error": str(error)}
    payload.update(extra)
    return payload


def get_hot_stocks(top: int = 10) -> Dict[str, Any]:
    """Return Eastmoney A-share hot ranking."""
    top = max(1, min(int(top or 10), 50))

    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_hot_rank_em())

    try:
        rows = _fetch("stock_hot_rank_em", "all", 1800, 2.0, loader)
    except Exception as exc:
        return _source_error("akshare_stock_hot_rank_em", exc, top=top, items=[])
    items = []
    for index, row in enumerate(rows[:top], start=1):
        code = _pick(row, ["代码", "股票代码", "证券代码", "code"])
        items.append(
            {
                "rank": safe_float(_pick(row, ["当前排名", "排名", "rank"])) or index,
                "code": normalize_a_share_code(str(code)) if code else None,
                "name": _pick(row, ["股票名称", "名称", "证券简称", "name"]),
                "latest_price": safe_float(_pick(row, ["最新价", "最新价格", "price"])),
                "change_pct": safe_float(_pick(row, ["涨跌幅", "涨跌幅%", "change_pct"])),
                "raw": row,
            }
        )
    return {"ok": bool(items), "top": top, "items": items, "source": "akshare_stock_hot_rank_em"}


def get_limit_up_stocks(date: str | None = None, top: int = 30) -> Dict[str, Any]:
    """Return daily limit-up pool and related fields if the data source provides them."""
    top = max(1, min(int(top or 30), 100))
    errors = []
    for trade_date in _recent_trade_dates(date, count=5):
        try:
            def loader(trade_date=trade_date):
                import akshare as ak  # type: ignore

                return _records(ak.stock_zt_pool_em(date=trade_date))

            rows = _fetch("stock_zt_pool_em", trade_date, 900, 2.0, loader)
        except Exception as exc:
            errors.append(f"{trade_date}: {exc}")
            continue
        if not rows:
            errors.append(f"{trade_date}: empty")
            continue

        items = []
        for row in rows[:top]:
            code = _pick(row, ["代码", "股票代码", "证券代码"])
            items.append(
                {
                    "code": normalize_a_share_code(str(code)) if code else None,
                    "name": _pick(row, ["名称", "股票名称", "证券简称"]),
                    "latest_price": safe_float(_pick(row, ["最新价", "收盘价"])),
                    "change_pct": safe_float(_pick(row, ["涨跌幅", "涨幅"])),
                    "turnover_rate": safe_float(_pick(row, ["换手率"])),
                    "amount": safe_float(_pick(row, ["成交额"])),
                    "industry": _pick(row, ["所属行业", "行业"]),
                    "limit_up_stats": _pick(row, ["涨停统计", "连板数"]),
                    "reason": _pick(row, ["涨停原因", "原因", "涨停解析"]),
                    "raw": row,
                }
            )
        return {
            "ok": True,
            "date": trade_date,
            "requested_date": date,
            "count": len(rows),
            "top": top,
            "items": items,
            "source": "akshare_stock_zt_pool_em",
        }

    return {
        "ok": False,
        "date": date,
        "items": [],
        "source": "akshare_stock_zt_pool_em",
        "error": "limit-up data unavailable",
        "source_errors": errors[-5:],
    }


def get_earnings_forecasts(date: str | None = None, top: int = 30, forecast_type: str | None = None) -> Dict[str, Any]:
    """Return recent performance forecast announcements from CNINFO ranking endpoint."""
    top = max(1, min(int(top or 30), 100))
    errors = []
    keyword = str(forecast_type or "").strip()
    for trade_date in _recent_trade_dates(date, count=7):
        try:
            def loader(trade_date=trade_date):
                import akshare as ak  # type: ignore

                return _records(ak.stock_rank_forecast_cninfo(date=trade_date))

            rows = _fetch("stock_rank_forecast_cninfo", trade_date, 3600, 2.0, loader)
        except Exception as exc:
            errors.append(f"{trade_date}: {exc}")
            continue
        if keyword:
            rows = [row for row in rows if keyword in str(row)]
        if not rows:
            errors.append(f"{trade_date}: empty")
            continue

        items = []
        for row in rows[:top]:
            code = _pick(row, ["代码", "股票代码", "证券代码", "ts_code"])
            items.append(
                {
                    "code": normalize_a_share_code(str(code)) if code else None,
                    "name": _pick(row, ["简称", "名称", "股票简称", "证券简称"]),
                    "forecast_type": _pick(row, ["业绩预告类型", "预告类型", "类型"]),
                    "summary": _pick(row, ["摘要", "公告标题", "标题", "内容"]),
                    "publish_date": _pick(row, ["公告日期", "发布日期", "date"]),
                    "raw": row,
                }
            )
        return {
            "ok": True,
            "date": trade_date,
            "requested_date": date,
            "forecast_type_filter": keyword or None,
            "count": len(rows),
            "top": top,
            "items": items,
            "source": "akshare_stock_rank_forecast_cninfo",
        }

    return {
        "ok": False,
        "date": date,
        "items": [],
        "source": "akshare_stock_rank_forecast_cninfo",
        "error": "earnings forecast data unavailable",
        "source_errors": errors[-7:],
    }


def get_moneyflow_rank(indicator: str = "今日", top: int = 20) -> Dict[str, Any]:
    """Return A-share individual stock fund-flow ranking."""
    top = max(1, min(int(top or 20), 100))
    indicator = indicator or "今日"

    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_individual_fund_flow_rank(indicator=indicator))

    try:
        rows = _fetch("stock_individual_fund_flow_rank", indicator, 900, 2.0, loader)
    except Exception as exc:
        return _source_error("akshare_stock_individual_fund_flow_rank", exc, indicator=indicator, top=top, items=[])
    items = []
    for row in rows[:top]:
        code = _pick(row, ["代码", "股票代码", "证券代码"])
        items.append(
            {
                "code": normalize_a_share_code(str(code)) if code else None,
                "name": _pick(row, ["名称", "股票名称", "证券简称"]),
                "latest_price": safe_float(_pick(row, ["最新价"])),
                "change_pct": safe_float(_pick(row, ["今日涨跌幅", "涨跌幅"])),
                "net_inflow": safe_float(_pick(row, ["主力净流入-净额", "净额", "主力净流入"])),
                "net_inflow_pct": safe_float(_pick(row, ["主力净流入-净占比", "净占比"])),
                "raw": row,
            }
        )
    return {
        "ok": bool(items),
        "indicator": indicator,
        "top": top,
        "items": items,
        "source": "akshare_stock_individual_fund_flow_rank",
    }


def get_stock_moneyflow(code: str) -> Dict[str, Any]:
    """Return recent individual stock fund-flow history."""
    norm = normalize_a_share_code(code)
    market = "sh" if norm.startswith(("6", "9")) else "bj" if norm.startswith(("8", "4")) else "sz"

    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_individual_fund_flow(stock=norm, market=market))

    try:
        rows = _fetch("stock_individual_fund_flow", norm, 1800, 2.0, loader)
    except Exception as exc:
        return _source_error("akshare_stock_individual_fund_flow", exc, code=norm, records=[])
    return {
        "ok": bool(rows),
        "code": norm,
        "market": market,
        "records": rows[-10:],
        "source": "akshare_stock_individual_fund_flow",
        "error": None if rows else "stock moneyflow data unavailable",
    }


def get_northbound_fund_flow() -> Dict[str, Any]:
    """Return northbound fund-flow summary."""
    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_hsgt_fund_flow_summary_em())

    try:
        rows = _fetch("stock_hsgt_fund_flow_summary_em", "all", 900, 2.0, loader)
    except Exception as exc:
        return _source_error("akshare_stock_hsgt_fund_flow_summary_em", exc, items=[])
    return {"ok": bool(rows), "items": rows, "source": "akshare_stock_hsgt_fund_flow_summary_em"}


def get_concept_boards(top: int = 30) -> Dict[str, Any]:
    """Return Eastmoney concept-board snapshot."""
    top = max(1, min(int(top or 30), 100))

    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_board_concept_name_em())

    try:
        rows = _fetch("stock_board_concept_name_em", "all", 1800, 2.0, loader)
    except Exception as exc:
        return _source_error("akshare_stock_board_concept_name_em", exc, top=top, items=[])
    return {"ok": bool(rows), "top": top, "items": rows[:top], "source": "akshare_stock_board_concept_name_em"}


def get_concept_stocks(concept_name: str, top: int = 50) -> Dict[str, Any]:
    """Return constituents of a concept board."""
    top = max(1, min(int(top or 50), 100))
    concept_name = str(concept_name or "").strip()

    def loader():
        import akshare as ak  # type: ignore

        return _records(ak.stock_board_concept_cons_em(symbol=concept_name))

    try:
        rows = _fetch("stock_board_concept_cons_em", concept_name, 1800, 2.0, loader)
    except Exception as exc:
        return _source_error("akshare_stock_board_concept_cons_em", exc, concept_name=concept_name, top=top, items=[])
    return {
        "ok": bool(rows),
        "concept_name": concept_name,
        "top": top,
        "items": rows[:top],
        "source": "akshare_stock_board_concept_cons_em",
        "error": None if rows else "concept constituents unavailable",
    }

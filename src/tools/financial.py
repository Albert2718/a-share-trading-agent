from __future__ import annotations

from typing import Any, Dict, List

from src.core import DataAccessLayer
from src.tools.deep_research.tools import AkshareTools
from src.tools.deep_research.utils import normalize_a_share_code, safe_float


def _pick_number(row: Dict[str, Any], names: List[str]):
    for name in names:
        if name in row:
            value = safe_float(row.get(name))
            if value is not None:
                return value
    return None


def get_stock_basic(code_or_name: str) -> Dict[str, Any]:
    """Return stock code and name from the A-share code-name table."""
    tools = AkshareTools()
    raw = str(code_or_name or "").strip()
    names = tools.stock_names()
    norm = normalize_a_share_code(raw)
    if norm in names:
        detail = _stock_detail(norm)
        return {
            "ok": True,
            "code": norm,
            "name": names[norm],
            "industry": detail.get("industry"),
            "listing_date": detail.get("listing_date"),
            "total_market_cap": detail.get("total_market_cap"),
            "detail": detail,
            "source": "akshare_stock_info_a_code_name+stock_individual_info_em",
        }
    matches = [{"code": code, "name": name} for code, name in names.items() if raw and raw in name]
    return {
        "ok": bool(matches),
        "query": raw,
        "matches": matches[:10],
        "source": "akshare_stock_info_a_code_name",
        "error": None if matches else "stock not found",
    }


def _stock_detail(code: str) -> Dict[str, Any]:
    norm = normalize_a_share_code(code)

    def loader():
        import akshare as ak  # type: ignore

        df = ak.stock_individual_info_em(symbol=norm)
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            key = str(row.get("item") or row.get("项目") or "")
            value = row.get("value") if "value" in row else row.get("值")
            if key:
                result[key] = value.item() if hasattr(value, "item") else value
        return result

    try:
        raw = DataAccessLayer().fetch("akshare", "stock_individual_info_em", norm, 86400, 1.5, loader)
    except Exception:
        raw = {}
    return {
        "industry": _first(raw, ["行业", "所属行业"]),
        "listing_date": _first(raw, ["上市时间", "上市日期"]),
        "total_market_cap": safe_float(_first(raw, ["总市值"])),
        "raw": raw,
    }


def _first(row: Dict[str, Any], names: List[str]):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def get_valuation(code: str) -> Dict[str, Any]:
    """Return latest valuation metrics."""
    tools = AkshareTools()
    norm = normalize_a_share_code(code)
    rows = tools.valuation(norm)
    latest = rows[-1] if rows else {}
    return {
        "ok": bool(latest),
        "code": norm,
        "pe_ttm": _pick_number(latest, ["市盈率(TTM)", "PE(TTM)", "市盈率"]),
        "pb": _pick_number(latest, ["市净率", "PB"]),
        "peg": _pick_number(latest, ["PEG"]),
        "raw": latest,
        "source": "akshare_stock_value_em",
        "error": None if latest else "valuation data unavailable",
    }


def get_financial_indicators(code: str) -> Dict[str, Any]:
    """Return latest financial indicators."""
    tools = AkshareTools()
    norm = normalize_a_share_code(code)
    rows = tools.financial_indicators(norm)
    latest = rows[-1] if rows else {}
    return {
        "ok": bool(latest),
        "code": norm,
        "roe": _pick_number(latest, ["净资产收益率", "净资产收益率(%)", "ROE"]),
        "revenue_growth": _pick_number(latest, ["主营业务收入增长率", "营业收入同比增长率", "营业总收入同比增长率"]),
        "net_profit_growth": _pick_number(latest, ["净利润增长率", "净利润同比增长率"]),
        "debt_ratio": _pick_number(latest, ["资产负债率", "资产负债率(%)"]),
        "raw": latest,
        "source": "akshare_stock_financial_analysis_indicator",
        "error": None if latest else "financial indicators unavailable",
    }

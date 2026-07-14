from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..schemas import AnalysisContext, FundamentalReport, StockCandidate
from ..tools import AkshareTools
from ..utils import clamp, safe_float


class FundamentalAnalyst:
    def __init__(self, akshare_tools: AkshareTools | None = None):
        self.akshare_tools = akshare_tools or AkshareTools()

    def analyze(self, candidate: StockCandidate, context: AnalysisContext) -> FundamentalReport:
        try:
            valuation_rows = self._safe_rows(self.akshare_tools.valuation, candidate.code)
            indicator_rows = self._safe_rows(self.akshare_tools.financial_indicators, candidate.code)
            if not valuation_rows and not indicator_rows:
                return FundamentalReport(
                    code=candidate.code,
                    name=candidate.name,
                    status="unavailable",
                    error="fundamental data unavailable",
                )
            return self._build_report(candidate, valuation_rows, indicator_rows)
        except Exception as exc:
            return FundamentalReport(code=candidate.code, name=candidate.name, status="error", error=str(exc))

    def _safe_rows(self, func, *args) -> List[Dict[str, Any]]:
        try:
            return func(*args) or []
        except Exception:
            return []

    def _build_report(
        self,
        candidate: StockCandidate,
        valuation_rows: List[Dict[str, Any]],
        indicator_rows: List[Dict[str, Any]],
    ) -> FundamentalReport:
        latest_valuation = valuation_rows[-1] if valuation_rows else {}
        latest_indicator = indicator_rows[-1] if indicator_rows else {}

        pe_ttm = self._first_number(latest_valuation, ["市盈率(TTM)", "PE(TTM)", "市盈率"])
        pb = self._first_number(latest_valuation, ["市净率", "PB"])
        peg = self._first_number(latest_valuation, ["PEG"])
        roe = self._first_number(latest_indicator, ["净资产收益率", "净资产收益率(%)", "ROE"])
        revenue_growth = self._first_number(latest_indicator, ["主营业务收入增长率", "营业收入同比增长率", "营业总收入同比增长率"])
        net_profit_growth = self._first_number(latest_indicator, ["净利润增长率", "净利润同比增长率"])
        debt_ratio = self._first_number(latest_indicator, ["资产负债率", "资产负债率(%)"])

        score = 50.0
        factors = []
        risks = []

        if pe_ttm is not None:
            if 0 < pe_ttm <= 25:
                score += 10
                factors.append(f"reasonable PE {pe_ttm:.2f}")
            elif pe_ttm > 60:
                score -= 12
                risks.append(f"high PE {pe_ttm:.2f}")
            elif pe_ttm <= 0:
                score -= 15
                risks.append("negative PE")
        if pb is not None:
            if 0 < pb <= 3:
                score += 5
            elif pb > 8:
                score -= 8
                risks.append(f"high PB {pb:.2f}")
        if roe is not None:
            if roe >= 15:
                score += 12
                factors.append(f"strong ROE {roe:.2f}%")
            elif roe < 5:
                score -= 8
                risks.append(f"weak ROE {roe:.2f}%")
        if revenue_growth is not None:
            if revenue_growth > 10:
                score += 6
                factors.append(f"revenue growth {revenue_growth:.2f}%")
            elif revenue_growth < -5:
                score -= 8
                risks.append(f"revenue decline {revenue_growth:.2f}%")
        if net_profit_growth is not None:
            if net_profit_growth > 10:
                score += 8
                factors.append(f"net profit growth {net_profit_growth:.2f}%")
            elif net_profit_growth < -10:
                score -= 12
                risks.append(f"net profit decline {net_profit_growth:.2f}%")
        if debt_ratio is not None:
            if debt_ratio > 70:
                score -= 10
                risks.append(f"high debt ratio {debt_ratio:.2f}%")
            elif debt_ratio < 45:
                score += 4

        final_score = int(round(clamp(score, 0, 100)))
        return FundamentalReport(
            code=candidate.code,
            name=candidate.name,
            fundamental_score=final_score,
            valuation_level=self._valuation_level(pe_ttm, pb),
            profitability_level="strong" if roe is not None and roe >= 15 else "weak" if roe is not None and roe < 5 else "neutral",
            growth_level=self._growth_level(revenue_growth, net_profit_growth),
            leverage_risk="high" if debt_ratio is not None and debt_ratio > 70 else "low" if debt_ratio is not None and debt_ratio < 45 else "medium",
            pe_ttm=pe_ttm,
            pb=pb,
            peg=peg,
            roe=roe,
            revenue_growth=revenue_growth,
            net_profit_growth=net_profit_growth,
            debt_ratio=debt_ratio,
            key_factors=factors[:8],
            risk_flags=risks,
        )

    def _first_number(self, row: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for key in keys:
            if key in row:
                value = safe_float(row.get(key))
                if value is not None:
                    return value
        return None

    def _valuation_level(self, pe_ttm: Optional[float], pb: Optional[float]) -> str:
        if pe_ttm is not None and pe_ttm > 60:
            return "expensive"
        if pb is not None and pb > 8:
            return "expensive"
        if pe_ttm is not None and 0 < pe_ttm <= 25:
            return "reasonable"
        return "unknown"

    def _growth_level(self, revenue_growth: Optional[float], net_profit_growth: Optional[float]) -> str:
        values = [item for item in [revenue_growth, net_profit_growth] if item is not None]
        if not values:
            return "unknown"
        avg = sum(values) / len(values)
        if avg > 10:
            return "strong"
        if avg < -5:
            return "weak"
        return "neutral"

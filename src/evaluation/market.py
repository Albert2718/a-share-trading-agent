from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

import pandas as pd

from src.core import DataAccessLayer
from src.tools.market_data import AkshareMarketData
from src.tools.utils import normalize_a_share_code


class EvaluationMarketData:
    """AKShare-backed market inputs used while creating an evaluation pool."""

    def __init__(
        self,
        data_access: DataAccessLayer | None = None,
        now_fn: Callable[[], datetime] | None = None,
        market_data: AkshareMarketData | None = None,
    ) -> None:
        self.data_access = data_access or DataAccessLayer()
        self._now_fn = now_fn or (lambda: datetime.now().astimezone())
        self._market_data = market_data or AkshareMarketData(
            data_access=self.data_access, now_fn=self._now_fn
        )
        self._ak = None

    def trade_dates(self) -> list[date]:
        cache_key = self._now_fn().date().isoformat()

        def loader() -> list[str]:
            frame = self._require_frame(self._require_akshare().tool_trade_date_hist_sina(), "trade dates")
            column = self._find_column(frame, ["trade_date", "日期", "date", "交易日"])
            if column is None:
                raise RuntimeError("trade dates response has no date column")
            dates = pd.to_datetime(frame[column], errors="coerce").dropna()
            if dates.empty:
                raise RuntimeError("trade dates response has no valid dates")
            return [value.date().isoformat() for value in dates]

        values = self.data_access.fetch(
            "akshare", "tool_trade_date_hist_sina", cache_key, 86400, 1.0, loader, fallback="raise"
        )
        try:
            result = sorted({date.fromisoformat(str(value)) for value in values})
        except (TypeError, ValueError) as exc:
            raise RuntimeError("cached trade dates are invalid") from exc
        if not result:
            raise RuntimeError("trade dates response is empty")
        return result

    def csi300_constituents(self) -> list[dict[str, Any]]:
        source_date = self._now_fn().date()

        def loader() -> list[dict[str, str]]:
            frame = self._require_frame(
                self._require_akshare().index_stock_cons_csindex(symbol="000300"),
                "CSI 300 constituents",
            )
            code_column = self._find_column(frame, ["成分券代码", "代码", "code", "证券代码"])
            name_column = self._find_column(frame, ["成分券名称", "名称", "name", "证券简称"])
            if code_column is None or name_column is None:
                raise RuntimeError("CSI 300 response has an invalid schema")
            records = [
                {
                    "code": normalize_a_share_code(str(row[code_column])),
                    "name": str(row[name_column]).strip(),
                }
                for _, row in frame.iterrows()
                if pd.notna(row[code_column]) and pd.notna(row[name_column]) and str(row[name_column]).strip()
            ]
            if not records:
                raise RuntimeError("CSI 300 response has no valid constituents")
            return records

        records = self.data_access.fetch(
            "akshare", "index_stock_cons_csindex", source_date.isoformat(), 86400, 1.0, loader, fallback="raise"
        )
        if not isinstance(records, list) or not records:
            raise RuntimeError("cached CSI 300 constituents are invalid")
        return [{**record, "source_date": source_date} for record in records]

    def industry_map(self) -> dict[str, str]:
        cache_key = "all"

        def loader() -> dict[str, str]:
            ak = self._require_akshare()
            try:
                return self._eastmoney_industry_map(ak)
            except Exception:
                return self._sw_industry_map(ak)

        mapping = self.data_access.fetch(
            "akshare", "stock_board_industry", cache_key, 7 * 86400, 1.0, loader, fallback="raise"
        )
        if not isinstance(mapping, dict) or not mapping:
            raise RuntimeError("cached industry mapping is invalid")
        return {normalize_a_share_code(str(code)): str(industry) for code, industry in mapping.items() if str(industry).strip()}

    def _eastmoney_industry_map(self, ak: Any) -> dict[str, str]:
        industries = self._require_frame(ak.stock_board_industry_name_em(), "industry names")
        name_column = self._find_column(industries, ["板块名称", "行业名称", "名称", "name"])
        if name_column is None:
            raise RuntimeError("industry names response has an invalid schema")
        mapping: dict[str, str] = {}
        for industry in industries[name_column].dropna().astype(str):
            industry = industry.strip()
            if not industry:
                continue
            members = self._require_frame(
                ak.stock_board_industry_cons_em(symbol=industry),
                f"industry members for {industry}",
            )
            code_column = self._find_column(members, ["代码", "code", "证券代码"])
            if code_column is None:
                raise RuntimeError(f"industry members response has an invalid schema for {industry}")
            for value in members[code_column].dropna():
                mapping[normalize_a_share_code(str(value))] = industry
        if not mapping:
            raise RuntimeError("industry membership response is empty")
        return mapping

    def _sw_industry_map(self, ak: Any) -> dict[str, str]:
        industries = self._require_frame(ak.sw_index_first_info(), "SW industry names")
        code_column = self._find_column(industries, ["行业代码", "code", "指数代码"])
        name_column = self._find_column(industries, ["行业名称", "name", "指数名称"])
        if code_column is None or name_column is None:
            raise RuntimeError("SW industry names response has an invalid schema")
        mapping: dict[str, str] = {}
        for _, row in industries.dropna(subset=[code_column, name_column]).iterrows():
            symbol = str(row[code_column]).split(".", 1)[0].strip()
            industry = str(row[name_column]).strip()
            if not symbol or not industry:
                continue
            members = self._require_frame(
                ak.index_component_sw(symbol=symbol),
                f"SW industry members for {symbol}",
            )
            member_code_column = self._find_column(members, ["证券代码", "代码", "code"])
            if member_code_column is None:
                raise RuntimeError(f"SW industry members response has an invalid schema for {symbol}")
            for value in members[member_code_column].dropna():
                mapping[normalize_a_share_code(str(value))] = industry
        if not mapping:
            raise RuntimeError("SW industry membership response is empty")
        return mapping

    def raw_history(self, code: str, days: int, end_date: date) -> pd.DataFrame:
        norm = normalize_a_share_code(code)
        end_value = pd.Timestamp(end_date).date()
        cache_key = f"{norm}_{days}_{end_value:%Y%m%d}"

        def loader() -> list[dict[str, Any]]:
            try:
                frame = self._market_data.history(
                    norm,
                    days=days,
                    adjust="",
                    end_date=end_value,
                    allow_stale_fallback=False,
                )
            except Exception:
                frame = self._sina_daily_history(norm, days, end_value)
            self._validate_history(frame)
            return self._records(frame)

        records = self.data_access.fetch(
            "akshare", "evaluation_raw_history", cache_key, 1800, 1.0, loader, fallback="raise"
        )
        frame = pd.DataFrame(records)
        self._validate_history(frame)
        return frame

    def _sina_daily_history(self, code: str, days: int, end_date: date) -> pd.DataFrame:
        ak = self._require_akshare()
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
        start_date = (
            pd.Timestamp(end_date) - pd.Timedelta(days=max(days * 3, 30))
        ).strftime("%Y%m%d")
        frame = self._require_frame(
            ak.stock_zh_a_daily(
                symbol=f"{prefix}{code}",
                start_date=start_date,
                end_date=pd.Timestamp(end_date).strftime("%Y%m%d"),
                adjust="",
            ),
            f"daily history for {code}",
        )
        return frame.tail(days).copy()

    def _load_akshare(self):
        if self._ak is not None:
            return self._ak
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:
            raise RuntimeError("akshare is not installed or unavailable") from exc
        self._ak = ak
        return ak

    def _require_akshare(self):
        return self._load_akshare()

    @staticmethod
    def _require_frame(value: Any, label: str) -> pd.DataFrame:
        if not isinstance(value, pd.DataFrame) or value.empty:
            raise RuntimeError(f"{label} response is empty")
        return value

    @staticmethod
    def _find_column(frame: pd.DataFrame, names: list[str]) -> str | None:
        return next((name for name in names if name in frame.columns), None)

    @staticmethod
    def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        clean = frame.copy().where(pd.notnull(frame), None)
        return [
            {
                str(key): value.isoformat() if isinstance(value, (pd.Timestamp, datetime, date)) else value.item() if hasattr(value, "item") else value
                for key, value in row.items()
            }
            for row in clean.to_dict(orient="records")
        ]

    @staticmethod
    def _validate_history(frame: pd.DataFrame) -> None:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise RuntimeError("raw history response is empty")
        required = {"date", "close", "volume"}
        if not required.issubset(frame.columns):
            raise RuntimeError("raw history response has an invalid schema")

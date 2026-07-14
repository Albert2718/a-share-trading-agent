from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from src.core import DataAccessLayer
from src.tools.utils import normalize_a_share_code, safe_float


class AkshareMarketData:
    def __init__(
        self,
        data_access: DataAccessLayer | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.data_access = data_access or DataAccessLayer()
        self._now_fn = now_fn or (lambda: datetime.now().astimezone())
        self._ak = None

    def available(self) -> bool:
        return self._load_akshare() is not None

    def candidates_from_codes(self, codes: List[str]) -> List[Dict[str, str]]:
        try:
            names = self.stock_names()
        except Exception:
            names = {}
        return [
            {"code": normalize_a_share_code(code), "name": names.get(normalize_a_share_code(code), "")}
            for code in codes
        ]

    def stock_names(self) -> Dict[str, str]:
        def loader():
            ak = self._require_akshare()
            df = ak.stock_info_a_code_name()
            code_col = self._find_column(df, ["code", "代码", "证券代码"])
            name_col = self._find_column(df, ["name", "名称", "股票简称", "证券简称"])
            if code_col is None or name_col is None:
                return {}
            return {
                normalize_a_share_code(str(row[code_col])): str(row[name_col])
                for _, row in df.iterrows()
            }

        return self.data_access.fetch("akshare", "stock_info_a_code_name", "all", 7 * 86400, 1.0, loader)

    def hot_candidates(self, top: int = 20) -> List[Dict[str, str]]:
        def loader():
            ak = self._require_akshare()
            df = ak.stock_hot_rank_em()
            return self._records(df)

        try:
            records = self.data_access.fetch("akshare", "stock_hot_rank_em", "all", 1800, 2.0, loader)
        except Exception:
            return []
        candidates = []
        for row in records[:top]:
            code = self._value(row, ["代码", "股票代码", "证券代码", "code"])
            name = self._value(row, ["股票名称", "名称", "证券简称", "name"])
            if code:
                candidates.append({"code": normalize_a_share_code(str(code)), "name": str(name or "")})
        return candidates

    def realtime_quote(self, code: str) -> Dict[str, Any]:
        norm = normalize_a_share_code(code)

        def loader():
            ak = self._require_akshare()
            errors = []
            providers = [
                ("akshare_stock_zh_a_spot_em", ak.stock_zh_a_spot_em),
                ("akshare_stock_zh_a_spot_sina", ak.stock_zh_a_spot),
            ]
            for source, fetcher in providers:
                try:
                    records = self._records(fetcher())
                    if records:
                        return {
                            "source": source,
                            "fetched_at": self._now_fn().isoformat(timespec="seconds"),
                            "records": records,
                        }
                    errors.append(f"{source}: empty")
                except Exception as exc:
                    errors.append(f"{source}: {exc}")
            raise RuntimeError("all realtime providers failed; " + " | ".join(errors[-2:]))

        payload = self.data_access.fetch(
            "akshare",
            "stock_zh_a_spot",
            "all",
            300,
            2.0,
            loader,
        )
        now = self._now_fn()
        fetched_at = str(payload.get("fetched_at") or now.isoformat(timespec="seconds"))
        quote_age_seconds = self._quote_age_seconds(fetched_at, now)
        if not self._realtime_snapshot_is_usable(fetched_at, now, quote_age_seconds):
            return {}
        source = str(payload.get("source") or "akshare_realtime")
        for row in payload.get("records", []):
            raw_code = self._value(row, ["代码", "股票代码", "证券代码", "code"])
            if raw_code is None or normalize_a_share_code(str(raw_code)) != norm:
                continue
            timestamp = self._value(row, ["时间戳", "时间", "timestamp"])
            volume = safe_float(self._value(row, ["成交量", "volume"]))
            if volume is not None and source == "akshare_stock_zh_a_spot_em":
                volume *= 100
            return {
                "code": norm,
                "name": str(self._value(row, ["名称", "股票名称", "证券简称", "name"]) or ""),
                "latest_price": self._value(row, ["最新价", "最新", "price"]),
                "previous_close": self._value(row, ["昨收", "昨收价", "previous_close"]),
                "open": self._value(row, ["今开", "开盘", "open"]),
                "high": self._value(row, ["最高", "high"]),
                "low": self._value(row, ["最低", "low"]),
                "volume": volume,
                "volume_unit": "shares",
                "amount": self._value(row, ["成交额", "amount"]),
                "change": self._value(row, ["涨跌额", "涨跌", "change"]),
                "change_pct": self._value(row, ["涨跌幅", "涨幅", "change_pct"]),
                "quote_time": self._normalize_quote_time(timestamp, fetched_at),
                "quote_age_seconds": quote_age_seconds,
                "data_freshness": "live" if quote_age_seconds <= 300 else "cached",
                "source": source,
            }
        return {}

    def history(self, code: str, days: int = 160) -> pd.DataFrame:
        norm = normalize_a_share_code(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        def loader():
            ak = self._require_akshare()
            errors = []
            for provider, fetcher in [
                (
                    "eastmoney",
                    lambda: ak.stock_zh_a_hist(
                        symbol=norm,
                        period="daily",
                        start_date=start,
                        end_date=end,
                        adjust="qfq",
                    ),
                ),
                (
                    "tencent",
                    lambda: ak.stock_zh_a_hist_tx(
                        symbol=self._market_symbol(norm),
                        start_date=start,
                        end_date=end,
                        adjust="qfq",
                    ),
                ),
                (
                    "sina",
                    lambda: ak.stock_zh_a_daily(
                        symbol=self._market_symbol(norm),
                        start_date=start,
                        end_date=end,
                        adjust="qfq",
                    ),
                ),
            ]:
                try:
                    df = fetcher()
                    records = self._records(df)
                    if records:
                        return records
                    errors.append(f"{provider}: empty")
                except Exception as exc:
                    errors.append(f"{provider}: {exc}")
            raise RuntimeError("all history providers failed; " + " | ".join(errors[-3:]))

        records = self.data_access.fetch("akshare", "stock_zh_a_hist", f"{norm}_{days}", 1800, 1.5, loader)
        return self._normalize_history(pd.DataFrame(records)).tail(days).reset_index(drop=True)

    def valuation(self, code: str) -> List[Dict[str, Any]]:
        norm = normalize_a_share_code(code)

        def loader():
            ak = self._require_akshare()
            df = ak.stock_value_em(symbol=norm)
            return self._records(df)

        return self.data_access.fetch("akshare", "stock_value_em", norm, 86400, 2.0, loader)

    def financial_indicators(self, code: str, start_year: str = "2020") -> List[Dict[str, Any]]:
        norm = normalize_a_share_code(code)

        def loader():
            ak = self._require_akshare()
            df = ak.stock_financial_analysis_indicator(symbol=norm, start_year=start_year)
            return self._records(df)

        return self.data_access.fetch(
            "akshare",
            "stock_financial_analysis_indicator",
            f"{norm}_{start_year}",
            86400,
            2.0,
            loader,
        )

    def stock_news(self, code: str) -> List[Dict[str, Any]]:
        norm = normalize_a_share_code(code)

        def loader():
            ak = self._require_akshare()
            df = ak.stock_news_em(symbol=norm)
            return self._records(df)

        return self.data_access.fetch("akshare", "stock_news_em", norm, 3600, 2.0, loader)

    def baidu_vote(self, code: str) -> List[Dict[str, Any]]:
        norm = normalize_a_share_code(code)

        def loader():
            ak = self._require_akshare()
            df = ak.stock_zh_vote_baidu(symbol=norm, indicator="股票")
            return self._records(df)

        return self.data_access.fetch("akshare", "stock_zh_vote_baidu", norm, 1800, 2.0, loader)

    def _load_akshare(self):
        if self._ak is not None:
            return self._ak
        try:
            import akshare as ak  # type: ignore
        except Exception:
            return None
        self._ak = ak
        return self._ak

    def _require_akshare(self):
        ak = self._load_akshare()
        if ak is None:
            raise RuntimeError("akshare is not installed or unavailable")
        return ak

    def _records(self, df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        if df is None or df.empty:
            return []
        clean = df.copy()
        clean = clean.where(pd.notnull(clean), None)
        return [
            {str(key): self._json_safe(value) for key, value in row.items()}
            for row in clean.to_dict(orient="records")
        ]

    def _json_safe(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (pd.Timestamp, datetime, date)):
            return value.isoformat()
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(value, "item"):
            value = value.item()
            if isinstance(value, (pd.Timestamp, datetime, date)):
                return value.isoformat()
        return value

    def _normalize_history(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        col_map = {
            "日期": "date",
            "date": "date",
            "开盘": "open",
            "open": "open",
            "最高": "high",
            "high": "high",
            "最低": "low",
            "low": "low",
            "收盘": "close",
            "close": "close",
            "成交量": "volume",
            "volume": "volume",
        }
        result = df.rename(columns={key: value for key, value in col_map.items() if key in df.columns})
        for col in ["date", "open", "high", "low", "close", "volume"]:
            if col not in result.columns:
                result[col] = 0.0 if col == "volume" else None
        result = result[["date", "open", "high", "low", "close", "volume"]].copy()
        for col in ["open", "high", "low", "close", "volume"]:
            result[col] = pd.to_numeric(result[col], errors="coerce")
        return result.dropna(subset=["close"]).reset_index(drop=True)

    def _market_symbol(self, code: str) -> str:
        norm = normalize_a_share_code(code)
        if norm.startswith(("6", "9")):
            return f"sh{norm}"
        if norm.startswith(("8", "4")):
            return f"bj{norm}"
        return f"sz{norm}"

    def _find_column(self, df: pd.DataFrame, names: List[str]) -> Optional[str]:
        for name in names:
            if name in df.columns:
                return name
        return None

    def _value(self, row: Dict[str, Any], names: List[str]) -> Any:
        for name in names:
            if name in row and row[name] not in (None, ""):
                return row[name]
        return None

    def _normalize_quote_time(self, timestamp: Any, fetched_at: str) -> str:
        text = str(timestamp or "").strip()
        if len(text) == 8 and text.count(":") == 2:
            fetched = datetime.fromisoformat(fetched_at)
            return fetched.replace(
                hour=int(text[0:2]),
                minute=int(text[3:5]),
                second=int(text[6:8]),
                microsecond=0,
            ).isoformat(timespec="seconds")
        return text or fetched_at

    def _quote_age_seconds(self, fetched_at: str, now: datetime) -> int:
        try:
            fetched = datetime.fromisoformat(fetched_at)
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=now.tzinfo)
            return max(0, int((now - fetched).total_seconds()))
        except (TypeError, ValueError):
            return 0

    def _realtime_snapshot_is_usable(self, fetched_at: str, now: datetime, age_seconds: int) -> bool:
        if age_seconds <= 900:
            return True
        try:
            fetched = datetime.fromisoformat(fetched_at)
        except (TypeError, ValueError):
            return False
        minute_of_day = now.hour * 60 + now.minute
        in_morning = 9 * 60 + 30 <= minute_of_day <= 11 * 60 + 30
        in_afternoon = 13 * 60 <= minute_of_day <= 15 * 60
        within_regular_hours = now.weekday() < 5 and (in_morning or in_afternoon)
        return not within_regular_hours and fetched.date() == now.date()

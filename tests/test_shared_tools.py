from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.tools.lstm import LSTMPredictor
from src.tools.market import get_realtime_price
from src.tools.market_data import AkshareMarketData
from src.tools.news_search import NewsSearchTool
from src.tools.utils import normalize_a_share_code


class _DataAccess:
    def fetch(self, namespace, endpoint, key, ttl_seconds, min_interval, loader, **kwargs):
        return loader()


class _RecordingDataAccess(_DataAccess):
    def __init__(self):
        self.calls = []

    def fetch(self, namespace, endpoint, key, ttl_seconds, min_interval, loader, **kwargs):
        self.calls.append({"endpoint": endpoint, "kwargs": kwargs})
        return super().fetch(
            namespace,
            endpoint,
            key,
            ttl_seconds,
            min_interval,
            loader,
            **kwargs,
        )


class _CachedRealtimeDataAccess:
    def fetch(self, namespace, endpoint, key, ttl_seconds, min_interval, loader, **kwargs):
        return {
            "source": "akshare_stock_zh_a_spot_sina",
            "fetched_at": "2026-07-14T15:20:00+08:00",
            "records": [{"代码": "sh600519", "名称": "贵州茅台", "最新价": 1214.88}],
        }


class _OldCachedRealtimeDataAccess(_CachedRealtimeDataAccess):
    def fetch(self, namespace, endpoint, key, ttl_seconds, min_interval, loader, **kwargs):
        payload = super().fetch(namespace, endpoint, key, ttl_seconds, min_interval, loader, **kwargs)
        payload["fetched_at"] = "2026-07-14T14:30:00+08:00"
        return payload


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"results": [{"title": "测试新闻", "content": "内容", "url": "https://example.com"}]}


class _SinaOnlyAkshare:
    def stock_zh_a_spot_em(self):
        raise ConnectionError("eastmoney unavailable")

    def stock_zh_a_spot(self):
        return pd.DataFrame(
            [
                {
                    "代码": "sh600519",
                    "名称": "贵州茅台",
                    "最新价": 1214.88,
                    "涨跌额": 3.89,
                    "涨跌幅": 0.321,
                    "昨收": 1210.99,
                    "今开": 1208.99,
                    "最高": 1226.87,
                    "最低": 1205.0,
                    "成交量": 4352726.0,
                    "成交额": 5294785036.0,
                    "时间戳": "15:18:15",
                }
            ]
        )


class _EastmoneyAkshare:
    def stock_zh_a_spot_em(self):
        return pd.DataFrame(
            [
                {
                    "代码": "600519",
                    "名称": "贵州茅台",
                    "最新价": 1214.88,
                    "成交量": 43527.26,
                }
            ]
        )

    def stock_zh_a_spot(self):
        raise AssertionError("sina should only be used as a fallback")


class _HistoryAkshare:
    def __init__(self):
        self.calls = []

    def stock_zh_a_hist(self, **kwargs):
        self.calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "日期": "2026-07-14",
                    "开盘": 10.0,
                    "最高": 11.0,
                    "最低": 9.5,
                    "收盘": 10.5,
                    "成交量": 1000.0,
                    "成交额": 10500.0,
                }
            ]
        )

    def stock_zh_a_hist_tx(self, **kwargs):
        raise AssertionError("eastmoney should satisfy the history request")

    def stock_zh_a_daily(self, **kwargs):
        raise AssertionError("eastmoney should satisfy the history request")


class _HistoryWithoutAmountAkshare(_HistoryAkshare):
    def stock_zh_a_hist(self, **kwargs):
        return super().stock_zh_a_hist(**kwargs).drop(columns=["成交额"])


class _RealtimeMarketData:
    def candidates_from_codes(self, codes):
        return [{"code": codes[0], "name": "贵州茅台"}]

    def realtime_quote(self, code):
        return {
            "code": code,
            "name": "贵州茅台",
            "latest_price": 1214.88,
            "previous_close": 1210.99,
            "open": 1208.99,
            "high": 1226.87,
            "low": 1205.0,
            "volume": 4352726.0,
            "amount": 5294785036.0,
            "change": 3.89,
            "change_pct": 0.321,
            "quote_time": "2026-07-14T15:18:15+08:00",
            "source": "akshare_stock_zh_a_spot_sina",
        }

    def history(self, code, days=8):
        raise AssertionError("realtime quote should not read daily history")


class _HistoricalMarketData:
    def realtime_quote(self, code):
        raise ConnectionError("realtime providers unavailable")

    def history(self, code, days=8):
        return pd.DataFrame(
            [
                {"date": "2026-07-13", "open": 1197.12, "high": 1215.0, "low": 1190.19, "close": 1210.99, "volume": 1.0},
                {"date": "2026-07-14", "open": 1208.99, "high": 1226.87, "low": 1205.0, "close": 1214.88, "volume": 2.0},
            ]
        )

    def candidates_from_codes(self, codes):
        return [{"code": codes[0], "name": "贵州茅台"}]


class SharedToolTests(unittest.TestCase):
    def test_normalize_a_share_code(self):
        self.assertEqual(normalize_a_share_code("SH.600519"), "600519")
        self.assertEqual(normalize_a_share_code("1"), "000001")

    def test_news_search_uses_injected_transport(self):
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return _Response()

        tool = NewsSearchTool(
            data_access=_DataAccess(),
            api_key="test-key",
            http_post=post,
            max_results=3,
        )
        results = tool.search("600519", "贵州茅台")

        self.assertEqual(results[0]["title"], "测试新闻")
        self.assertEqual(calls[0][0], "https://api.tavily.com/search")
        self.assertNotIn("test-key", str(results))

    def test_realtime_quote_falls_back_to_sina_and_normalizes_code(self):
        tool = AkshareMarketData(data_access=_DataAccess())
        tool._ak = _SinaOnlyAkshare()

        quote = tool.realtime_quote("600519")

        self.assertEqual(quote["code"], "600519")
        self.assertEqual(quote["latest_price"], 1214.88)
        self.assertEqual(quote["source"], "akshare_stock_zh_a_spot_sina")
        self.assertTrue(quote["quote_time"].endswith("15:18:15+08:00"))

    def test_realtime_quote_normalizes_eastmoney_volume_to_shares(self):
        tool = AkshareMarketData(data_access=_DataAccess())
        tool._ak = _EastmoneyAkshare()

        quote = tool.realtime_quote("600519")

        self.assertEqual(quote["volume"], 4352726.0)
        self.assertEqual(quote["volume_unit"], "shares")

    def test_realtime_quote_reuses_same_day_cached_snapshot_after_close(self):
        now = datetime(2026, 7, 14, 15, 30, tzinfo=timezone(timedelta(hours=8)))
        tool = AkshareMarketData(data_access=_CachedRealtimeDataAccess(), now_fn=lambda: now)

        quote = tool.realtime_quote("600519")

        self.assertEqual(quote["latest_price"], 1214.88)
        self.assertEqual(quote["data_freshness"], "cached")
        self.assertEqual(quote["quote_age_seconds"], 600)

    def test_realtime_quote_rejects_old_cached_snapshot_during_trading(self):
        now = datetime(2026, 7, 14, 14, 50, tzinfo=timezone(timedelta(hours=8)))
        tool = AkshareMarketData(data_access=_OldCachedRealtimeDataAccess(), now_fn=lambda: now)

        quote = tool.realtime_quote("600519")

        self.assertEqual(quote, {})

    def test_history_passes_raw_adjustment_and_explicit_end_date_to_akshare(self):
        akshare = _HistoryAkshare()
        tool = AkshareMarketData(data_access=_DataAccess())
        tool._ak = akshare

        history = tool.history("600519", adjust="", end_date=date(2026, 7, 14))

        self.assertEqual(akshare.calls[0]["adjust"], "")
        self.assertEqual(akshare.calls[0]["end_date"], "20260714")
        self.assertEqual(history.loc[0, "amount"], 10500.0)

    def test_history_defaults_to_qfq_adjustment(self):
        akshare = _HistoryAkshare()
        tool = AkshareMarketData(data_access=_DataAccess(), now_fn=lambda: datetime(2026, 7, 14))
        tool._ak = akshare

        tool.history("600519")

        self.assertEqual(akshare.calls[0]["adjust"], "qfq")

    def test_history_defaults_to_stale_cache_compatibility(self):
        data_access = _RecordingDataAccess()
        tool = AkshareMarketData(data_access=data_access)
        tool._ak = _HistoryAkshare()

        tool.history("600519", end_date=date(2026, 7, 14))

        self.assertEqual(data_access.calls[0]["kwargs"].get("fallback", "cache"), "cache")

    def test_history_can_disable_stale_cache_fallback(self):
        data_access = _RecordingDataAccess()
        tool = AkshareMarketData(data_access=data_access)
        tool._ak = _HistoryAkshare()

        tool.history(
            "600519",
            end_date=date(2026, 7, 14),
            allow_stale_fallback=False,
        )

        self.assertEqual(data_access.calls[0]["kwargs"]["fallback"], "raise")

    def test_history_preserves_absent_amount_column(self):
        tool = AkshareMarketData(data_access=_DataAccess())
        tool._ak = _HistoryWithoutAmountAkshare()

        history = tool.history("600519", adjust="", end_date=date(2026, 7, 14))

        self.assertNotIn("amount", history.columns)

    def test_get_realtime_price_returns_live_quote_without_history_lookup(self):
        with patch("src.tools.market.AkshareMarketData", return_value=_RealtimeMarketData()):
            result = get_realtime_price("600519")

        self.assertTrue(result["ok"])
        self.assertTrue(result["is_realtime"])
        self.assertEqual(result["name"], "贵州茅台")
        self.assertEqual(result["latest_price"], 1214.88)
        self.assertEqual(result["market_session"], "outside_regular_trading_hours")
        self.assertEqual(result["source"], "akshare_stock_zh_a_spot_sina")

    def test_get_realtime_price_marks_daily_history_as_fallback(self):
        with patch("src.tools.market.AkshareMarketData", return_value=_HistoricalMarketData()):
            result = get_realtime_price("600519")

        self.assertTrue(result["ok"])
        self.assertFalse(result["is_realtime"])
        self.assertEqual(result["name"], "贵州茅台")
        self.assertEqual(result["latest_price"], 1214.88)
        self.assertEqual(result["source"], "akshare_daily_fallback")

    def test_lstm_predictor_loads_project_model(self):
        predictor = LSTMPredictor()
        closes = np.array(
            [10, 10.1, 10.05, 10.2, 10.3, 10.25, 10.4, 10.5, 10.45, 10.6, 10.7, 10.65, 10.8, 10.9],
            dtype=np.float32,
        )

        value = predictor.predict_return(closes)

        self.assertEqual(predictor.model_path.name, "lstm_model.pt")
        self.assertIsNotNone(value, predictor.last_error)


if __name__ == "__main__":
    unittest.main()

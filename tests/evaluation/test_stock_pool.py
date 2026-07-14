from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.evaluation.market import EvaluationMarketData
from src.evaluation.stock_pool import StockPoolManager


FIXED_TIME = datetime(2026, 7, 14, 16, 0, 0)


class FakePoolProvider:
    def __init__(
        self,
        candidate_count: int,
        industry_count: int,
        omit_amount: bool = False,
        amount_value: float | None = None,
    ):
        self.candidate_count = candidate_count
        self.industry_count = industry_count
        self.omit_amount = omit_amount
        self.amount_value = amount_value
        self.constituent_calls = 0
        self.industry_calls = 0
        self.history_calls = 0

    def csi300_constituents(self):
        self.constituent_calls += 1
        return [
            {
                "code": f"{number:06d}",
                "name": f"Company {number}",
                "source_date": date(2026, 7, 14),
            }
            for number in range(1, self.candidate_count + 1)
        ]

    def industry_map(self):
        self.industry_calls += 1
        return {
            f"{number:06d}": f"Industry {number % self.industry_count:02d}"
            for number in range(1, self.candidate_count + 1)
        }

    def raw_history(self, code, days, end_date):
        self.history_calls += 1
        amount = self.amount_value if self.amount_value is not None else int(code) * 1000.0
        rows = [
            {
                "date": trade_date,
                "close": 10.0,
                "volume": 100.0,
                **({} if self.omit_amount else {"amount": amount}),
            }
            for trade_date in pd.bdate_range(end=end_date, periods=523)
        ]
        return pd.DataFrame(rows)


class FakeDataAccess:
    def __init__(self):
        self.calls = []

    def fetch(
        self,
        namespace,
        endpoint,
        key,
        ttl_seconds,
        min_interval,
        loader,
        **kwargs,
    ):
        self.calls.append(
            {
                "namespace": namespace,
                "endpoint": endpoint,
                "key": key,
                "ttl_seconds": ttl_seconds,
                "min_interval": min_interval,
                **kwargs,
            }
        )
        return loader()


class FakeEvaluationAkshare:
    def __init__(self):
        self.constituents = pd.DataFrame(
            [{"成分券代码": "600519", "成分券名称": "贵州茅台"}]
        )
        self.industry_names = pd.DataFrame([{"板块名称": "白酒"}])
        self.industry_members = {"白酒": pd.DataFrame([{"代码": "600519"}])}
        self.trade_calendar = pd.DataFrame(
            [{"trade_date": "2026-07-13"}, {"trade_date": "2026-07-14"}]
        )
        self.constituent_symbols = []
        self.industry_symbols = []

    def index_stock_cons_csindex(self, symbol):
        self.constituent_symbols.append(symbol)
        return self.constituents

    def stock_board_industry_name_em(self):
        return self.industry_names

    def stock_board_industry_cons_em(self, symbol):
        self.industry_symbols.append(symbol)
        return self.industry_members[symbol]

    def tool_trade_date_hist_sina(self):
        return self.trade_calendar


class StockPoolTests(unittest.TestCase):
    def test_selects_twenty_distinct_industries_before_duplicates(self):
        provider = FakePoolProvider(candidate_count=30, industry_count=25)

        entries = StockPoolManager(provider).select(selected_at=FIXED_TIME)

        self.assertEqual(len(entries), 20)
        self.assertEqual(len({entry.industry for entry in entries}), 20)
        self.assertEqual([entry.code for entry in entries], sorted(
            (entry.code for entry in entries), reverse=True
        ))

    def test_fills_remaining_pool_with_no_more_than_two_per_industry(self):
        provider = FakePoolProvider(candidate_count=30, industry_count=10)

        entries = StockPoolManager(provider).select(selected_at=FIXED_TIME)

        self.assertEqual(len(entries), 20)
        self.assertLessEqual(
            max(sum(entry.industry == industry for entry in entries) for industry in {entry.industry for entry in entries}),
            2,
        )

    def test_excludes_st_short_history_missing_close_and_zero_volume(self):
        provider = FakePoolProvider(candidate_count=24, industry_count=24)
        original_history = provider.raw_history

        def raw_history(code, days, end_date):
            history = original_history(code, days, end_date)
            if code == "000001":
                history.loc[:, "volume"] = 0.0
            if code == "000002":
                history.loc[:, "close"] = float("nan")
            if code == "000003":
                return history.tail(249)
            return history

        provider.raw_history = raw_history
        original_constituents = provider.csi300_constituents

        def constituents():
            rows = original_constituents()
            rows[3]["name"] = "ST Stock 4"
            rows[4]["name"] = "退市Stock 5"
            return rows

        provider.csi300_constituents = constituents

        with self.assertRaisesRegex(RuntimeError, "exactly 20 unique stocks"):
            StockPoolManager(provider).select(selected_at=FIXED_TIME)

    def test_select_rejects_fewer_than_twenty_stocks(self):
        provider = FakePoolProvider(candidate_count=19, industry_count=19)

        with self.assertRaisesRegex(RuntimeError, "exactly 20 unique stocks"):
            StockPoolManager(provider).select(selected_at=FIXED_TIME)

    def test_freeze_does_not_write_incomplete_pool(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
            provider = FakePoolProvider(candidate_count=19, industry_count=19)
            path = Path(root) / "stock_pool.json"

            with self.assertRaisesRegex(RuntimeError, "exactly 20 unique stocks"):
                StockPoolManager(provider).freeze(path, FIXED_TIME)

            self.assertFalse(path.exists())

    def test_freeze_reuses_existing_pool_without_refetch(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
            provider = FakePoolProvider(candidate_count=25, industry_count=25)
            manager = StockPoolManager(provider)
            path = Path(root) / "stock_pool.json"

            first = manager.freeze(path, FIXED_TIME)
            second = manager.freeze(path, FIXED_TIME)

            self.assertEqual(first, second)
            self.assertEqual(provider.constituent_calls, 1)
            self.assertEqual(manager.load(path), first)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["rule_version"], "1.0")
            self.assertEqual(payload["selected_at"], FIXED_TIME.isoformat())
            self.assertEqual(len(payload["entries"]), 20)

    def test_load_rejects_wrong_cardinality_and_duplicate_codes(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
            provider = FakePoolProvider(candidate_count=20, industry_count=20)
            manager = StockPoolManager(provider)
            path = Path(root) / "stock_pool.json"
            manager.freeze(path, FIXED_TIME)
            valid_payload = json.loads(path.read_text(encoding="utf-8"))

            malformed_payloads = []
            too_short = deepcopy(valid_payload)
            too_short["entries"].pop()
            malformed_payloads.append(too_short)
            duplicate = deepcopy(valid_payload)
            duplicate["entries"][19]["code"] = duplicate["entries"][0]["code"]
            malformed_payloads.append(duplicate)

            for index, payload in enumerate(malformed_payloads):
                malformed_path = Path(root) / f"malformed-{index}.json"
                malformed_path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                with self.subTest(index=index), self.assertRaisesRegex(
                    ValueError, "invalid frozen stock pool"
                ):
                    manager.load(malformed_path)

    def test_records_close_times_volume_when_amount_is_unavailable(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
            provider = FakePoolProvider(candidate_count=20, industry_count=20, omit_amount=True)
            path = Path(root) / "stock_pool.json"

            StockPoolManager(provider).freeze(path, FIXED_TIME)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["entries"][0]["liquidity_source"], "close_x_volume")

    def test_present_zero_or_invalid_amount_does_not_use_fallback(self):
        for amount in (0.0, float("nan")):
            with self.subTest(amount=amount):
                provider = FakePoolProvider(
                    candidate_count=20,
                    industry_count=20,
                    amount_value=amount,
                )
                manager = StockPoolManager(provider)

                with self.assertRaisesRegex(RuntimeError, "exactly 20 unique stocks"):
                    manager.select(selected_at=FIXED_TIME)

                self.assertEqual(manager._liquidity_sources, {})


class EvaluationMarketDataTests(unittest.TestCase):
    def make_adapter(self, akshare=None, data_access=None):
        adapter = EvaluationMarketData(
            data_access=data_access or FakeDataAccess(),
            now_fn=lambda: FIXED_TIME,
        )
        adapter._ak = akshare or FakeEvaluationAkshare()
        return adapter

    def test_parses_csi300_industries_and_trade_calendar_with_cache_contracts(self):
        data_access = FakeDataAccess()
        akshare = FakeEvaluationAkshare()
        adapter = self.make_adapter(akshare=akshare, data_access=data_access)

        constituents = adapter.csi300_constituents()
        industries = adapter.industry_map()
        trade_dates = adapter.trade_dates()

        self.assertEqual(constituents, [{
            "code": "600519",
            "name": "贵州茅台",
            "source_date": date(2026, 7, 14),
        }])
        self.assertEqual(industries, {"600519": "白酒"})
        self.assertEqual(trade_dates, [date(2026, 7, 13), date(2026, 7, 14)])
        self.assertEqual(akshare.constituent_symbols, ["000300"])
        self.assertEqual(akshare.industry_symbols, ["白酒"])
        self.assertEqual(
            [
                (call["endpoint"], call["key"], call["ttl_seconds"])
                for call in data_access.calls
            ],
            [
                ("index_stock_cons_csindex", "2026-07-14", 86400),
                ("stock_board_industry", "all", 7 * 86400),
                ("tool_trade_date_hist_sina", "2026-07-14", 86400),
            ],
        )

    def test_csi300_rejects_empty_and_invalid_schema(self):
        for frame in (pd.DataFrame(), pd.DataFrame([{"wrong": "value"}])):
            with self.subTest(columns=list(frame.columns)):
                akshare = FakeEvaluationAkshare()
                akshare.constituents = frame
                with self.assertRaises(RuntimeError):
                    self.make_adapter(akshare=akshare).csi300_constituents()

    def test_trade_calendar_rejects_empty_and_invalid_schema(self):
        for frame in (pd.DataFrame(), pd.DataFrame([{"wrong": "value"}])):
            with self.subTest(columns=list(frame.columns)):
                akshare = FakeEvaluationAkshare()
                akshare.trade_calendar = frame
                with self.assertRaises(RuntimeError):
                    self.make_adapter(akshare=akshare).trade_dates()

    def test_industry_map_rejects_empty_and_invalid_schemas(self):
        cases = [
            (pd.DataFrame(), {"白酒": pd.DataFrame([{"代码": "600519"}])}),
            (pd.DataFrame([{"wrong": "value"}]), {"白酒": pd.DataFrame([{"代码": "600519"}])}),
            (pd.DataFrame([{"板块名称": "白酒"}]), {"白酒": pd.DataFrame()}),
            (pd.DataFrame([{"板块名称": "白酒"}]), {"白酒": pd.DataFrame([{"wrong": "value"}])}),
        ]
        for names, members in cases:
            with self.subTest(name_columns=list(names.columns), members=members):
                akshare = FakeEvaluationAkshare()
                akshare.industry_names = names
                akshare.industry_members = members
                with self.assertRaises(RuntimeError):
                    self.make_adapter(akshare=akshare).industry_map()

    def test_requirements_pin_verified_akshare_version(self):
        requirements = (
            Path(__file__).resolve().parents[2] / "requirements.txt"
        ).read_text(encoding="utf-8").splitlines()

        self.assertIn("akshare==1.18.64", requirements)


if __name__ == "__main__":
    unittest.main()

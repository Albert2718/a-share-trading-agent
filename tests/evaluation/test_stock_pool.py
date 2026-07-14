from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.evaluation.stock_pool import StockPoolManager


FIXED_TIME = datetime(2026, 7, 14, 16, 0, 0)


class FakePoolProvider:
    def __init__(self, candidate_count: int, industry_count: int, omit_amount: bool = False):
        self.candidate_count = candidate_count
        self.industry_count = industry_count
        self.omit_amount = omit_amount
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
        amount = int(code) * 1000.0
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

        entries = StockPoolManager(provider).select(selected_at=FIXED_TIME)

        self.assertEqual(len(entries), 19)
        self.assertTrue({"000001", "000002", "000003", "000004", "000005"}.isdisjoint(
            {entry.code for entry in entries}
        ))

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

    def test_records_close_times_volume_when_amount_is_unavailable(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
            provider = FakePoolProvider(candidate_count=20, industry_count=20, omit_amount=True)
            path = Path(root) / "stock_pool.json"

            StockPoolManager(provider).freeze(path, FIXED_TIME)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["entries"][0]["liquidity_source"], "close_x_volume")


if __name__ == "__main__":
    unittest.main()

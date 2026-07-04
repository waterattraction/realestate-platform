"""资产情况统计单元测试."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import repayment_analytics as ra


class TestRatio(unittest.TestCase):
    def test_ratio_normal(self):
        self.assertEqual(ra._ratio(1, 4), 0.25)

    def test_ratio_zero_denominator(self):
        self.assertIsNone(ra._ratio(10, 0))


class TestPeriodLabel(unittest.TestCase):
    def test_month_label(self):
        self.assertEqual(ra._period_label("month", date(2026, 6, 1)), "2026-06")

    def test_year_label(self):
        self.assertEqual(ra._period_label("year", date(2026, 1, 1)), "2026")


class TestIssueDates(unittest.TestCase):
    def test_fetch_issue_dates(self):
        conn = MagicMock()

        def execute(sql, params=None):
            result = MagicMock()
            result.mappings.return_value = [
                {"issue_date": date(2026, 3, 15), "asset_primary_count": 310},
                {"issue_date": date(2026, 1, 1), "asset_primary_count": 100},
            ]
            return result

        conn.execute = execute
        items = ra.fetch_issue_dates(conn, 2)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["issue_date"], "2026-03-15")
        self.assertIn("310", items[0]["label"])


class TestAttachRatios(unittest.TestCase):
    def test_attach_ratios(self):
        periods = [{"period_label": "2026-06", "repaid_asset_count": 10, "repayment_amount": 1000.0}]
        baseline = {"asset_primary_count": 100, "min_transferable_total": 5000.0}
        stock = {"unpaid_asset_count": 80, "monitor_snapshot_date": "2026-06-26"}
        out = ra._attach_ratios(periods, baseline, stock)
        self.assertEqual(out[0]["repaid_asset_ratio"], 0.1)
        self.assertEqual(out[0]["repayment_amount_ratio"], 0.2)
        self.assertEqual(out[0]["unpaid_asset_count"], 80)


if __name__ == "__main__":
    unittest.main()

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


class TestPeriodEnd(unittest.TestCase):
    def test_month_end(self):
        self.assertEqual(ra._period_end("month", date(2026, 2, 1)), date(2026, 2, 28))

    def test_week_end(self):
        self.assertEqual(ra._period_end("week", date(2026, 3, 2)), date(2026, 3, 8))


class TestIssueDates(unittest.TestCase):
    def test_fetch_issue_dates(self):
        conn = MagicMock()

        def execute(sql, params=None):
            result = MagicMock()
            result.mappings.return_value = [
                {"issue_date": date(2026, 3, 15), "issued_asset_count": 310},
                {"issue_date": date(2026, 1, 1), "issued_asset_count": 100},
            ]
            return result

        conn.execute = execute
        items = ra.fetch_issue_dates(conn, 2)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["issue_date"], "2026-03-15")
        self.assertIn("310", items[0]["label"])


class TestResolveIssueDate(unittest.TestCase):
    def test_resolve_all(self):
        conn = MagicMock()

        def execute(sql, params=None):
            result = MagicMock()
            result.mappings.return_value = [
                {"issue_date": date(2026, 4, 20), "issued_asset_count": 64},
                {"issue_date": date(2026, 3, 20), "issued_asset_count": 110},
            ]
            return result

        conn.execute = execute
        self.assertEqual(ra.resolve_issue_date(conn, 4, "all"), "all")

    def test_resolve_auto_latest(self):
        conn = MagicMock()

        def execute(sql, params=None):
            result = MagicMock()
            result.mappings.return_value = [
                {"issue_date": date(2026, 4, 20), "issued_asset_count": 64},
            ]
            return result

        conn.execute = execute
        self.assertEqual(ra.resolve_issue_date(conn, 4, None), "2026-04-20")


class TestIssuanceStockAll(unittest.TestCase):
    def test_fetch_issuance_stock_with_monitor(self):
        conn = MagicMock()
        captured: dict[str, str] = {}

        def execute(sql, params=None):
            captured["sql"] = str(sql)
            result = MagicMock()
            mappings = MagicMock()
            mappings.first.return_value = {
                "issued_asset_count": 174,
                "transferred_out_count": 47,
                "active_asset_count": 127,
                "min_transferable_total": 13939294.44,
                "receivable_transfer_total": 11918344.82,
                "active_min_transferable_total": 9740396.44,
                "active_receivable_transfer_total": 8287530.34,
                "transferred_min_transferable_total": 3673885.10,
                "transferred_receivable_transfer_total": 3241271.63,
                "pre_transfer_repaid_total": 525012.90,
                "monitor_snapshot_date": date(2026, 7, 3),
                "monitor_asset_count": 127,
                "initial_transfer_total": 9740396.44,
                "repaid_total": 2537517.98,
                "remaining_total": 7202878.46,
                "paid_off_count": 4,
                "unpaid_count": 123,
                "no_monitor_count": 0,
            }
            result.mappings.return_value = mappings
            return result

        conn.execute = execute
        stock, monitor = ra.fetch_issuance_stock_with_monitor(conn, 4, "all")
        self.assertEqual(stock["effective_asset_count"], 127)
        self.assertEqual(stock["transferred_min_transferable_total"], 3673885.10)
        self.assertEqual(stock["pre_transfer_repaid_total"], 525012.90)
        self.assertAlmostEqual(
            stock["active_min_transferable_total"]
            + stock["transferred_min_transferable_total"]
            + stock["pre_transfer_repaid_total"],
            stock["min_transferable_total"],
        )
        self.assertEqual(monitor["initial_transfer_total"], 9740396.44)
        self.assertIn("pre_transfer_repaid", captured["sql"])
        self.assertIn("from_trust_product_id", captured["sql"])


class TestDisplayIssueDate(unittest.TestCase):
    def test_display_all(self):
        self.assertEqual(ra._display_issue_date("all"), "全部")

    def test_display_single(self):
        self.assertEqual(ra._display_issue_date("2026-04-20"), "2026-04-20")


class TestAttachRatios(unittest.TestCase):
    def test_attach_ratios(self):
        conn = MagicMock()

        def execute(sql, params=None):
            result = MagicMock()
            mappings = MagicMock()
            mappings.all.return_value = [
                {"period_start": date(2026, 6, 1), "cumulative_repayment": 1000.0},
            ]
            result.mappings.return_value = mappings
            return result

        conn.execute = execute
        periods = [{"period_key": "2026-06-01", "period_label": "2026-06", "repaid_asset_count": 10, "repayment_amount": 1000.0}]
        stock = {
            "active_asset_count": 100,
            "active_min_transferable_total": 5000.0,
            "paid_off_count": 20,
            "unpaid_count": 80,
        }
        monitor = {
            "monitor_snapshot_date": "2026-06-26",
            "initial_transfer_total": 10000.0,
        }
        out = ra._attach_ratios(
            conn, 4, "all", "month", periods, stock, monitor,
        )
        self.assertEqual(out[0]["repaid_asset_ratio"], 0.1)
        self.assertEqual(out[0]["repayment_amount_ratio"], 0.2)
        self.assertEqual(out[0]["cumulative_repayment"], 1000.0)
        self.assertEqual(out[0]["remaining_repayment"], 9000.0)
        self.assertEqual(out[0]["cumulative_repayment_ratio"], 0.1)


if __name__ == "__main__":
    unittest.main()

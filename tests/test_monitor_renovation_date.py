"""监控导入：最后一期装修款付款时间."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_html
from app.assetinfo_upload import _parse_monitor_rows


class TestMonitorRenovationDateParse(unittest.TestCase):
    def _base_row(self) -> dict:
        return {
            "统计日期": "2026-07-03",
            "初始受让金额": 100000,
            "已还款金额": 50000,
            "剩余还款金额": 50000,
            "托管房源编码": "107113281945",
        }

    def test_parse_includes_last_renovation_when_column_present(self):
        row = self._base_row()
        row["最后一期装修款付款时间"] = "2025-12-01"
        result = _parse_monitor_rows(
            pd.DataFrame([row]),
            file_name="test.xlsx",
            sheet_name="sheet1",
        )
        self.assertEqual(result.parsed_row_count, 1)
        self.assertEqual(result.rows[0]["last_renovation_payment_date"], date(2025, 12, 1))

    def test_parse_missing_column_sets_null_and_warns(self):
        result = _parse_monitor_rows(
            pd.DataFrame([self._base_row()]),
            file_name="test.xlsx",
            sheet_name="sheet1",
        )
        self.assertEqual(result.parsed_row_count, 1)
        self.assertIsNone(result.rows[0]["last_renovation_payment_date"])
        self.assertTrue(
            any("最后一期装修款付款时间" in w for w in result.warnings),
            msg=result.warnings,
        )


class TestMonitorRenovationDateDisplay(unittest.TestCase):
    def test_monitor_column_order_after_remaining_amount(self):
        order = list(assetinfo_html.MONITOR_COLUMN_ORDER)
        self.assertNotIn("asset_pool_code", order)
        self.assertNotIn("source_asset_code", order)
        rem_idx = order.index("remaining_amount")
        self.assertEqual(order[rem_idx + 1], "asset_status")
        self.assertEqual(order[rem_idx + 2], "last_renovation_payment_date")

    def test_monitor_column_label(self):
        self.assertEqual(
            assetinfo_html.MONITOR_COLUMN_LABELS["last_renovation_payment_date"],
            "最后一期装修款付款时间",
        )


if __name__ == "__main__":
    unittest.main()

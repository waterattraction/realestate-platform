"""监控列表：折扣率筛选与全量排序."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_upload


class TestMonitorDiscountRateFilter(unittest.TestCase):
    def test_none_sentinel(self):
        f = assetinfo_upload.build_record_filters(
            asset_transfer_discount_rate=assetinfo_upload.MONITOR_DISCOUNT_RATE_NONE,
        )
        self.assertEqual(
            f["asset_transfer_discount_rate"],
            assetinfo_upload.MONITOR_DISCOUNT_RATE_NONE,
        )

    def test_numeric_value(self):
        f = assetinfo_upload.build_record_filters(asset_transfer_discount_rate="0.83")
        self.assertAlmostEqual(f["asset_transfer_discount_rate"], 0.83)

    def test_invalid_value_ignored(self):
        f = assetinfo_upload.build_record_filters(asset_transfer_discount_rate="bad")
        self.assertIsNone(f["asset_transfer_discount_rate"])


class TestMonitorSortParsing(unittest.TestCase):
    def test_valid_sort_columns(self):
        f = assetinfo_upload.build_record_filters(
            sort_by="overdue_days",
            sort_dir="asc",
        )
        self.assertEqual(f["sort_by"], "overdue_days")
        self.assertEqual(f["sort_dir"], "asc")

    def test_invalid_sort_by_cleared(self):
        f = assetinfo_upload.build_record_filters(sort_by="DROP TABLE")
        self.assertIsNone(f["sort_by"])

    def test_sort_dir_defaults_desc(self):
        f = assetinfo_upload.build_record_filters(sort_by="data_date")
        self.assertEqual(f["sort_dir"], "desc")


class TestBuildMonitorOrderBy(unittest.TestCase):
    def test_default_order(self):
        sql = assetinfo_upload.build_monitor_order_by(None, None)
        self.assertIn("r.data_date DESC", sql)
        self.assertIn("r.custody_asset_code ASC", sql)

    def test_whitelisted_column_asc(self):
        sql = assetinfo_upload.build_monitor_order_by("overdue_days", "asc")
        self.assertIn("r.overdue_days ASC", sql)
        self.assertIn("r.data_date DESC", sql)

    def test_discount_rate_sort(self):
        sql = assetinfo_upload.build_monitor_order_by(
            "asset_transfer_discount_rate",
            "desc",
        )
        self.assertIn("iss.asset_transfer_discount_rate DESC", sql)

    def test_invalid_sort_by_falls_back(self):
        sql = assetinfo_upload.build_monitor_order_by("evil; DROP", "asc")
        self.assertIn("r.data_date DESC", sql)
        self.assertNotIn("evil", sql)


if __name__ == "__main__":
    unittest.main()

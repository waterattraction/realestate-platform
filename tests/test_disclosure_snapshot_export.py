"""还款披露快照导出：按产品文件名与 Sheet 名。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.disclosure import (
    monitor_export_sheet_name,
    monitor_product_filename,
    repayment_snapshot_product_filename,
    repayment_snapshot_sheet_names,
    snapshot_export_zip_filename,
)


class RepaymentSnapshotExportNamingTests(unittest.TestCase):
    def test_sheet_names_use_compact_as_of_only_on_detail(self):
        detail, plan = repayment_snapshot_sheet_names("20260717")
        self.assertEqual(detail, "20260717已还款")
        self.assertEqual(plan, "回款计划")

    def test_product_filename(self):
        name = repayment_snapshot_product_filename("美好生活2号", "20260717")
        self.assertEqual(name, "美好生活2号-还款明细披露信息-20260717.xlsx")

    def test_filename_strips_forbidden_chars(self):
        name = repayment_snapshot_product_filename('美/好:生活', "20260717")
        self.assertEqual(name, "美_好_生活-还款明细披露信息-20260717.xlsx")

    def test_as_of_label_yyyyymmdd(self):
        from datetime import date
        from app.disclosure import _as_of_label

        self.assertEqual(_as_of_label(date(2026, 7, 17)), "20260717")
        self.assertEqual(_as_of_label("2026-07-17"), "20260717")

    def test_zip_filename_uses_beijing_ymdhm_without_suffix(self):
        from datetime import datetime, timezone

        name = snapshot_export_zip_filename(
            "还款明细披露信息",
            datetime(2026, 7, 21, 8, 10, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(name, "还款明细披露信息-202607211610.zip")
        self.assertNotIn("按产品", name)


class MonitorExportNamingTests(unittest.TestCase):
    def test_sheet_name_fixed(self):
        self.assertEqual(monitor_export_sheet_name(), "资产监控表")

    def test_product_filename(self):
        name = monitor_product_filename("美好生活2号", "20260717")
        self.assertEqual(name, "美好生活2号-资产监控表-20260717.xlsx")

    def test_filename_strips_forbidden_chars(self):
        name = monitor_product_filename('美/好:生活', "20260717")
        self.assertEqual(name, "美_好_生活-资产监控表-20260717.xlsx")

    def test_zip_filename(self):
        from datetime import datetime, timezone

        name = snapshot_export_zip_filename(
            "资产监控表",
            datetime(2026, 7, 21, 8, 10, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(name, "资产监控表-202607211610.zip")
        self.assertNotIn("按产品", name)


if __name__ == "__main__":
    unittest.main()

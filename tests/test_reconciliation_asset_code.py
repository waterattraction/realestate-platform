"""金额核对：按 r.asset_code 跨表汇总 + 编码不一致告警."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import main as main_mod
from app.service import checks_service


class TestReconciliationItemFromRow(unittest.TestCase):
    def _row(self, **kwargs):
        defaults = {
            "trust_product_id": 2,
            "trust_product_name": "美好生活2号",
            "data_date": "2026-07-03",
            "asset_code": "107113281945",
            "custody_count": 1,
            "initial_transfer_amount": 87800.0,
            "repaid_amount": 20345.08,
            "remaining_amount": 67454.92,
            "balance_remainder": 0.0,
            "repayment_detail_total": 17676.81,
            "cross_diff": 2668.27,
            "code_mismatch_count": 1,
            "code_mismatch_amount": 2668.27,
        }
        defaults.update(kwargs)
        return type("Row", (), defaults)()

    def test_cross_fail_when_repaid_differs_from_r_asset_code_sum(self):
        item = main_mod._reconciliation_item_from_row(self._row())
        self.assertFalse(item["cross_passed"])
        self.assertAlmostEqual(item["cross_diff"], 2668.27)

    def test_code_mismatch_flags_anomaly_independently(self):
        item = main_mod._reconciliation_item_from_row(
            self._row(
                repayment_detail_total=20345.08,
                cross_diff=0.0,
                code_mismatch_count=1,
            )
        )
        self.assertTrue(item["cross_passed"])
        self.assertFalse(item["code_mismatch_passed"])
        self.assertTrue(item["has_anomaly"])

    def test_all_pass_when_aligned(self):
        item = main_mod._reconciliation_item_from_row(
            self._row(
                repayment_detail_total=20345.08,
                cross_diff=0.0,
                code_mismatch_count=0,
                code_mismatch_amount=0.0,
            )
        )
        self.assertTrue(item["has_anomaly"] is False)


class TestChecksServiceCodeMismatch(unittest.TestCase):
    def test_code_mismatch_marks_anomaly(self):
        checks = checks_service.run_asset_checks(
            100.0, 50.0, 50.0, 50.0,
            code_mismatch={"row_count": 1, "amount_sum": 10.0},
        )
        self.assertFalse(checks["code_mismatch"]["passed"])
        self.assertTrue(checks["has_anomaly"])

    def test_summary_counts_code_mismatch(self):
        items = [
            {"balance_passed": True, "cross_passed": True, "code_mismatch_passed": False},
            {"balance_passed": True, "cross_passed": False, "code_mismatch_passed": True},
        ]
        summary = main_mod._reconciliation_summary(items)
        self.assertEqual(summary["code_mismatch_fail_count"], 1)
        self.assertEqual(summary["cross_fail_count"], 1)


if __name__ == "__main__":
    unittest.main()

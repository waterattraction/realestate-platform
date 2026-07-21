"""手工结算 overlay / 虚拟还款行."""

from __future__ import annotations

import unittest
from datetime import date

from app.manual_settlement import (
    SOURCE_MANUAL_SETTLEMENT,
    apply_amount_overlay,
    merge_repayment_items_with_settlements,
    overlay_monitor_amounts,
    virtual_repayment_rows_from_settlements,
)


class ManualSettlementOverlayTests(unittest.TestCase):
    def test_apply_amount_overlay(self):
        repaid, remaining = apply_amount_overlay(100.0, 50.0, 30.0)
        self.assertEqual(repaid, 130.0)
        self.assertEqual(remaining, 20.0)

    def test_remaining_floors_at_zero(self):
        repaid, remaining = apply_amount_overlay(10.0, 20.0, 50.0)
        self.assertEqual(repaid, 60.0)
        self.assertEqual(remaining, 0.0)

    def test_overlay_monitor_amounts(self):
        row = overlay_monitor_amounts(
            {"repaid_amount": 100, "remaining_amount": 80}, 25
        )
        self.assertEqual(row["repaid_amount"], 125.0)
        self.assertEqual(row["remaining_amount"], 55.0)

    def test_virtual_repayment_rows(self):
        rows = virtual_repayment_rows_from_settlements(
            [
                {
                    "id": 9,
                    "trust_product_id": 1,
                    "asset_code": "A1",
                    "custody_asset_code": "A1-01",
                    "settlement_date": date(2026, 7, 21),
                    "payer": "甲方",
                    "repayer": "中国对外经济贸易信托有限公司",
                    "amount": 12.5,
                    "description": "补录",
                    "voided_at": None,
                },
                {
                    "id": 10,
                    "amount": 5,
                    "voided_at": "2026-07-21T00:00:00+08:00",
                },
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], SOURCE_MANUAL_SETTLEMENT)
        self.assertEqual(rows[0]["actual_repayment_amount"], 12.5)
        self.assertEqual(rows[0]["planned_repayment_amount"], 12.5)
        self.assertEqual(rows[0]["current_payer"], "中国对外经济贸易信托有限公司")
        self.assertEqual(rows[0]["manual_settlement_id"], 9)

    def test_merge_repayment_items_sorts_desc(self):
        merged = merge_repayment_items_with_settlements(
            [
                {
                    "id": 1,
                    "repayment_date": "2026-07-01",
                    "actual_repayment_amount": 1,
                }
            ],
            [
                {
                    "id": 2,
                    "asset_code": "A1",
                    "settlement_date": "2026-07-20",
                    "payer": "P",
                    "amount": 3,
                }
            ],
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["source"], SOURCE_MANUAL_SETTLEMENT)
        self.assertEqual(merged[0]["repayment_date"], "2026-07-20")

    def test_overlay_both_sides_cancels_in_cross_check(self):
        """左右同加结算后，交叉核对差额与仅事实表一致。"""
        from app.service.checks_service import run_asset_checks

        monitor_repaid, detail_total, settlement = 100.0, 80.0, 20.0
        left, rem = apply_amount_overlay(monitor_repaid, 50.0, settlement)
        right = detail_total + settlement
        checks = run_asset_checks(150.0, left, rem, right)
        # 事实口径：100 vs 80 → 不通过；叠加后 120 vs 100 → 仍不通过且差额同为 20
        self.assertEqual(checks["cross_sheet_repayment"]["diff_amount"], 20.0)
        fact_checks = run_asset_checks(150.0, monitor_repaid, 50.0, detail_total)
        self.assertEqual(
            checks["cross_sheet_repayment"]["diff_amount"],
            fact_checks["cross_sheet_repayment"]["diff_amount"],
        )


if __name__ == "__main__":
    unittest.main()

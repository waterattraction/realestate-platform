"""资产监控披露：M 级 → 资产状态，以及列序含逾期天数。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_templates as templates
from app.disclosure import disclosure_monitor_asset_status


class DisclosureMonitorStatusTests(unittest.TestCase):
    def test_m05_m1_m1_plus_map_to_light(self):
        # M0.5: 1–15 days
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=10, remaining_amount=1000, fallback_status="正常"
            ),
            "轻度",
        )
        # M1: 16–30
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20, remaining_amount=1000, fallback_status="正常"
            ),
            "轻度",
        )
        # M1+: >30
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=45, remaining_amount=1000, fallback_status="正常"
            ),
            "轻度",
        )

    def test_m0_maps_to_normal(self):
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=0, remaining_amount=1000, fallback_status="轻度"
            ),
            "正常",
        )
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=-5, remaining_amount=500, fallback_status="待置换资产"
            ),
            "正常",
        )

    def test_es_maps_to_early_settlement(self):
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=10, remaining_amount=0, fallback_status="正常"
            ),
            "提前结清",
        )
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=0, remaining_amount=0.005, fallback_status="提前还款"
            ),
            "提前结清",
        )

    def test_sd_source_status_maps_to_severe(self):
        # 无法算出 M 级时，源状态 SD → 重度
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=None, remaining_amount=1000, fallback_status="SD"
            ),
            "重度",
        )

    def test_active_severe_followup_overrides_to_severe(self):
        # 即使 M 级本应为轻度，活跃重度逾期事项优先 → 重度
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20,
                remaining_amount=1000,
                fallback_status="正常",
                has_severe_followup=True,
            ),
            "重度",
        )

    def test_no_severe_followup_keeps_m_mapping(self):
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20,
                remaining_amount=1000,
                fallback_status="正常",
                has_severe_followup=False,
            ),
            "轻度",
        )

    def test_repurchased_and_swap_out_beat_m_level_and_severe(self):
        # 即使逾期落入轻度、且有重度跟进，强制业务态仍优先
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20,
                remaining_amount=1000,
                fallback_status="正常",
                has_severe_followup=True,
                force_status="已回购",
            ),
            "已回购",
        )
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=45,
                remaining_amount=1000,
                fallback_status="轻度",
                has_severe_followup=True,
                force_status="已置换转出",
            ),
            "已置换转出",
        )

    def test_swap_in_uses_m_level_when_no_force(self):
        # 转入方：不传 force_status → M 级
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20,
                remaining_amount=1000,
                fallback_status="待置换资产",
                force_status=None,
            ),
            "轻度",
        )

    def test_normal_status_clears_overdue_days_for_disclosure(self):
        from app.disclosure import (
            _apply_disclosure_monitor_row,
            _blank_repayment_overdue_if_normal,
        )

        row = _apply_disclosure_monitor_row(
            {
                "trust_product_id": 1,
                "asset_code": "A1",
                "overdue_days": 0,
                "remaining_amount": 1000,
                "asset_status": "待确认",
            }
        )
        self.assertEqual(row["asset_status"], "正常")
        self.assertIsNone(row["overdue_days"])

        mild = _apply_disclosure_monitor_row(
            {
                "trust_product_id": 1,
                "asset_code": "A2",
                "overdue_days": 10,
                "remaining_amount": 1000,
                "asset_status": "正常",
            }
        )
        self.assertEqual(mild["asset_status"], "轻度")
        self.assertEqual(mild["overdue_days"], 10)

        severe = _apply_disclosure_monitor_row(
            {
                "trust_product_id": 1,
                "asset_code": "A3",
                "overdue_days": 5,
                "remaining_amount": 1000,
                "asset_status": "正常",
                # force via followup path below
            },
            severe_followup_keys={(1, "A3")},
        )
        self.assertEqual(severe["asset_status"], "重度")
        self.assertEqual(severe["overdue_days"], 5)

        swapped = _apply_disclosure_monitor_row(
            {
                "trust_product_id": 1,
                "asset_code": "A4",
                "overdue_days": 32,
                "remaining_amount": 1000,
                "asset_status": "正常",
            },
            force_status="已置换转出",
        )
        self.assertEqual(swapped["asset_status"], "已置换转出")
        self.assertIsNone(swapped["overdue_days"])

        bought = _apply_disclosure_monitor_row(
            {
                "trust_product_id": 1,
                "asset_code": "A5",
                "overdue_days": 12,
                "remaining_amount": 1000,
                "asset_status": "轻度",
            },
            force_status="已回购",
        )
        self.assertEqual(bought["asset_status"], "已回购")
        self.assertIsNone(bought["overdue_days"])

        detail = {
            "overdue_days": 0,
            "remaining_balance": 1000,
            "_monitor_remaining_amount": 1000,
        }
        _blank_repayment_overdue_if_normal(
            detail, monitor_remaining_amount=detail.get("_monitor_remaining_amount")
        )
        self.assertIsNone(detail["overdue_days"])
        self.assertNotIn("_monitor_remaining_amount", detail)

        detail_overdue = {"overdue_days": 10, "remaining_balance": 1000}
        _blank_repayment_overdue_if_normal(
            detail_overdue, monitor_remaining_amount=1000
        )
        self.assertEqual(detail_overdue["overdue_days"], 10)


class MonitorForceBusinessStatusTests(unittest.TestCase):
    def test_helper_priority(self):
        from app.disclosure import monitor_force_business_status

        self.assertEqual(
            monitor_force_business_status(is_repurchased=True, is_swap_out_view=True),
            "已回购",
        )
        self.assertEqual(
            monitor_force_business_status(is_repurchased=False, is_swap_out_view=True),
            "已置换转出",
        )
        self.assertIsNone(
            monitor_force_business_status(is_repurchased=False, is_swap_out_view=False)
        )


class DisclosureMonitorColumnsTests(unittest.TestCase):
    def test_overdue_days_follows_asset_status(self):
        keys = templates.template_field_keys(
            templates.DISCLOSURE_MONITOR_TEMPLATE_COLUMNS
        )
        headers = templates.template_headers(
            templates.DISCLOSURE_MONITOR_TEMPLATE_COLUMNS
        )
        idx = keys.index("asset_status")
        self.assertEqual(keys[idx + 1], "overdue_days")
        self.assertEqual(headers[idx], "资产状态")
        self.assertEqual(headers[idx + 1], "逾期天数")


if __name__ == "__main__":
    unittest.main()

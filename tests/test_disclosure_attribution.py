"""披露归属裁决：同日冲突 / 最新事件 / 三列覆写。"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date

from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.disclosure_attribution import (
    SOURCE_ISSUANCE,
    SOURCE_REPURCHASE,
    SOURCE_SWAP,
    AttributionEvent,
    AssetAttribution,
    apply_triad_from_attribution,
    resolve_events_for_asset,
)


class ResolveEventsTests(unittest.TestCase):
    def test_latest_business_date_wins(self):
        events = [
            AttributionEvent(SOURCE_ISSUANCE, date(2026, 1, 1), 1, ref="a"),
            AttributionEvent(SOURCE_SWAP, date(2026, 6, 1), 2, ref="b"),
            AttributionEvent(SOURCE_REPURCHASE, date(2026, 3, 1), 3, ref="c"),
        ]
        w = resolve_events_for_asset(events, asset_label="A1")
        self.assertEqual(w.source, SOURCE_SWAP)
        self.assertEqual(w.trust_product_id, 2)

    def test_same_day_conflict_raises(self):
        events = [
            AttributionEvent(SOURCE_SWAP, date(2026, 7, 17), 1, ref="s"),
            AttributionEvent(SOURCE_REPURCHASE, date(2026, 7, 17), 2, ref="r"),
        ]
        with self.assertRaises(HTTPException) as ctx:
            resolve_events_for_asset(events, asset_label="A1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("冲突", ctx.exception.detail)

    def test_empty_returns_none(self):
        self.assertIsNone(resolve_events_for_asset([], asset_label="A1"))


class TriadApplyTests(unittest.TestCase):
    def test_apply_triad_maps_monitor_fields(self):
        row = {
            "initial_renovation_amount": 1,
            "cumulative_repaid_amount": 2,
            "remaining_balance": 3,
        }
        attr = AssetAttribution(
            asset_code="A1",
            source=SOURCE_SWAP,
            initial_transfer_amount=100.0,
            repaid_amount=40.0,
            remaining_amount=60.0,
        )
        apply_triad_from_attribution(row, attr)
        self.assertEqual(row["initial_renovation_amount"], 100.0)
        self.assertEqual(row["cumulative_repaid_amount"], 40.0)
        self.assertEqual(row["remaining_balance"], 60.0)

    def test_no_source_keeps_original(self):
        row = {"initial_renovation_amount": 1}
        apply_triad_from_attribution(row, AssetAttribution(asset_code="A1"))
        self.assertEqual(row["initial_renovation_amount"], 1)


class ForceStatusTests(unittest.TestCase):
    def test_force_status_overrides(self):
        from app.disclosure import disclosure_monitor_asset_status

        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20,
                remaining_amount=1000,
                fallback_status="正常",
                force_status="已回购",
            ),
            "已回购",
        )
        self.assertEqual(
            disclosure_monitor_asset_status(
                overdue_days=20,
                remaining_amount=1000,
                fallback_status="正常",
                force_status="已置换转出",
            ),
            "已置换转出",
        )


if __name__ == "__main__":
    unittest.main()

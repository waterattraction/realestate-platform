"""无还款资产：逾期天数从发行日起算."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import text

from app.assetinfo_pipeline import RECONCILIATION_TOLERANCE


def _overdue_days_on_import(
    data_date: date,
    *,
    last_payment_date: date | None,
    remaining_amount: float,
    issue_date: date | None,
) -> int | None:
    """Legacy pipeline import path logic (mirrors assetinfo_pipeline.py)."""
    if last_payment_date:
        return max(0, (data_date - last_payment_date).days)
    if remaining_amount <= RECONCILIATION_TOLERANCE:
        return None
    if issue_date:
        return max(0, (data_date - issue_date).days)
    return None


class TestOverdueDaysImportLogic(unittest.TestCase):
    def test_no_repayment_uses_issue_date(self):
        od = _overdue_days_on_import(
            date(2026, 7, 3),
            last_payment_date=None,
            remaining_amount=1000.0,
            issue_date=date(2026, 4, 20),
        )
        self.assertEqual(od, 74)

    def test_no_repayment_no_issue_date_is_null(self):
        od = _overdue_days_on_import(
            date(2026, 7, 3),
            last_payment_date=None,
            remaining_amount=1000.0,
            issue_date=None,
        )
        self.assertIsNone(od)

    def test_early_settlement_is_null(self):
        od = _overdue_days_on_import(
            date(2026, 7, 3),
            last_payment_date=None,
            remaining_amount=0.0,
            issue_date=date(2026, 4, 20),
        )
        self.assertIsNone(od)

    def test_with_repayment_uses_last_payment(self):
        od = _overdue_days_on_import(
            date(2026, 7, 3),
            last_payment_date=date(2026, 6, 1),
            remaining_amount=1000.0,
            issue_date=date(2026, 4, 20),
        )
        self.assertEqual(od, 32)


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL not set")
class TestRecalculateOverdueNoRepaymentIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.main import engine

        cls.engine = engine

    def test_product4_0703_no_repayment_assets(self) -> None:
        from app.main import recalculate_overdue_days

        as_of = date(2026, 7, 3)
        with self.engine.begin() as conn:
            result = recalculate_overdue_days(
                conn,
                trust_product_id=4,
                data_date="2026-07-03",
                as_of=as_of,
            )
            rows = conn.execute(
                text("""
                    SELECT asset_code, overdue_days
                    FROM trust_asset_monitor_records
                    WHERE trust_product_id = 4
                      AND data_date = '2026-07-03'
                      AND asset_code IN (
                          '101134229290', '107112427808', '101132799241', '107112396048'
                      )
                    ORDER BY asset_code
                """)
            ).mappings().all()

        by_code = {r["asset_code"]: r["overdue_days"] for r in rows}
        self.assertEqual(result["no_repayment_from_issue_count"], 4)
        self.assertEqual(result["missing_issuance_count"], 0)
        self.assertEqual(by_code["101134229290"], 74)
        self.assertEqual(by_code["107112427808"], 105)
        self.assertEqual(by_code["101132799241"], 74)
        self.assertEqual(by_code["107112396048"], 169)


if __name__ == "__main__":
    unittest.main()

"""IssuanceRepo primary asset_code lookup — cross-product chain."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import create_engine

from app.repo.issuance_repo import IssuanceRepo
from app.service.overdue_workbench import _pick_issuance_identity_id

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://admin:ChangeThisPassword123!@localhost:5432/realestate",
)


class TestIssuanceRepoPrimaryAssetCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)
        cls.repo = IssuanceRepo(cls.engine)

    def test_107112396048_returns_two_cross_product_rows(self):
        rows = self.repo.fetch_by_primary_asset_code("107112396048")
        self.assertEqual(len(rows), 2)
        products = {r["trust_product_name"] for r in rows}
        self.assertIn("美好生活2号", products)
        self.assertIn("美润1号", products)
        custodies = {r["custody_asset_code"] for r in rows}
        self.assertIn("107112396048", custodies)
        self.assertIn("107112396048-1", custodies)

    def test_pick_identity_prefers_current_product(self):
        rows = self.repo.fetch_by_primary_asset_code("107112396048")
        identity_id = _pick_issuance_identity_id(rows, trust_product_id=4)
        meirun = next(r for r in rows if r["trust_product_id"] == 4)
        self.assertEqual(identity_id, meirun["id"])

    def test_empty_primary_returns_empty(self):
        self.assertEqual(self.repo.fetch_by_primary_asset_code(""), [])
        self.assertEqual(self.repo.fetch_by_primary_asset_code("   "), [])


if __name__ == "__main__":
    unittest.main()

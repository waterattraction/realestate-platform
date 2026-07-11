"""监控列表：已转让筛选."""

from __future__ import annotations

import os
import sys
import unittest

from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_upload


class TestTransferredFilterParsing(unittest.TestCase):
    def test_yes_no_values(self):
        f = assetinfo_upload.build_record_filters(trust_product_id=4, transferred="yes")
        self.assertEqual(f["transferred"], "yes")
        f = assetinfo_upload.build_record_filters(trust_product_id=4, transferred="no")
        self.assertEqual(f["transferred"], "no")
        f = assetinfo_upload.build_record_filters(trust_product_id=4, transferred="是")
        self.assertEqual(f["transferred"], "yes")

    def test_requires_trust_product(self):
        with self.assertRaises(HTTPException) as ctx:
            assetinfo_upload.build_record_filters(transferred="yes")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_value(self):
        with self.assertRaises(HTTPException):
            assetinfo_upload.build_record_filters(trust_product_id=4, transferred="maybe")


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL not set")
class TestTransferredFilterIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.db import get_engine

        cls.engine = get_engine()

    def test_product4_transferred_yes_includes_transferred_in_custody(self):
        filters = {
            "trust_product_id": 4,
            "custody_asset_code": "101128210944",
            "transferred": "yes",
        }
        with self.engine.connect() as conn:
            data = assetinfo_upload.fetch_paginated_records(
                conn, "monitor", 1, 10, filters,
            )
        self.assertGreaterEqual(data["total"], 1)
        item = data["items"][0]
        self.assertEqual(item["custody_asset_code"], "101128210944")
        self.assertEqual(int(item["trust_product_id"]), 3)

    def test_product4_transferred_yes_count_on_fixed_date(self):
        with self.engine.connect() as conn:
            data = assetinfo_upload.fetch_paginated_records(
                conn,
                "monitor",
                1,
                200,
                {"trust_product_id": 4, "data_date": "2026-07-03", "transferred": "yes"},
            )
        self.assertEqual(data["total"], 47)

    def test_product4_transferred_no_excludes_transferred_out_custody(self):
        with self.engine.connect() as conn:
            data = assetinfo_upload.fetch_paginated_records(
                conn,
                "monitor",
                1,
                200,
                {
                    "trust_product_id": 4,
                    "data_date": "2026-07-03",
                    "transferred": "no",
                    "custody_asset_code": "101128210944",
                },
            )
        self.assertEqual(data["total"], 0)

    def test_product4_all_matches_transferred_no_on_fixed_date(self):
        base = {"trust_product_id": 4, "data_date": "2026-07-03"}
        with self.engine.connect() as conn:
            all_rows = assetinfo_upload.fetch_paginated_records(
                conn, "monitor", 1, 200, dict(base),
            )
            no_rows = assetinfo_upload.fetch_paginated_records(
                conn, "monitor", 1, 200, {**base, "transferred": "no"},
            )
        self.assertEqual(all_rows["total"], no_rows["total"])


if __name__ == "__main__":
    unittest.main()

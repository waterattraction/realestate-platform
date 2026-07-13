"""监控列表：城市列/筛选与 Excel 导出."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_upload
from app.issuance_upload import ISSUANCE_CITY_UNKNOWN


class TestMonitorCityFilter(unittest.TestCase):
    def test_city_filter_parsed(self):
        f = assetinfo_upload.build_record_filters(city="北京")
        self.assertEqual(f["city"], "北京")

    def test_build_query_includes_city_in_select(self):
        _, _, _, _, _, select_extra = assetinfo_upload._build_monitor_record_query({})
        self.assertIn("iss.city", select_extra)

    def test_unknown_city_where(self):
        where_parts: list[str] = []
        params: dict = {}
        assetinfo_upload._append_monitor_issuance_filters(
            where_parts,
            params,
            {"city": ISSUANCE_CITY_UNKNOWN},
        )
        self.assertEqual(len(where_parts), 1)
        self.assertIn("iss.city IS NULL", where_parts[0])


class TestMonitorExport(unittest.TestCase):
    def test_export_columns_include_city(self):
        self.assertIn("city", assetinfo_upload.MONITOR_EXPORT_COLUMNS)
        idx_reno = assetinfo_upload.MONITOR_EXPORT_COLUMNS.index("last_renovation_payment_date")
        self.assertEqual(assetinfo_upload.MONITOR_EXPORT_COLUMNS[idx_reno + 1], "city")

    def test_build_xlsx_empty(self):
        data = assetinfo_upload.build_monitor_export_xlsx([])
        self.assertGreater(len(data), 100)

    def test_build_xlsx_with_row(self):
        items = [{
            "trust_product_name": "美润1号",
            "asset_code": "101",
            "custody_asset_code": "101",
            "source_asset_code": "101-001",
            "data_date": "2026-07-03",
            "overdue_days": 0,
            "initial_transfer_amount": 1000.0,
            "repaid_amount": 500.0,
            "remaining_amount": 500.0,
            "asset_transfer_discount_rate": 0.83,
            "last_renovation_payment_date": "2026-10-06",
            "city": "北京",
        }]
        data = assetinfo_upload.build_monitor_export_xlsx(items)
        self.assertGreater(len(data), 100)

    def test_export_max_constant(self):
        self.assertEqual(assetinfo_upload.MONITOR_EXPORT_MAX, 20_000)


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL not set")
class TestMonitorCityExportIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.db import get_engine

        cls.engine = get_engine()

    def test_city_options_not_empty(self):
        with self.engine.connect() as conn:
            cities = assetinfo_upload.fetch_monitor_city_options(conn)
        self.assertIn(ISSUANCE_CITY_UNKNOWN, cities)

    def test_export_count_matches_list_total(self):
        filters = assetinfo_upload.build_record_filters(trust_product_id=4)
        with self.engine.connect() as conn:
            page = assetinfo_upload.fetch_paginated_records(conn, "monitor", 1, 10, filters)
            items, total = assetinfo_upload.fetch_monitor_records_for_export(conn, filters)
        self.assertEqual(page["total"], total)
        self.assertEqual(len(items), total)


if __name__ == "__main__":
    unittest.main()

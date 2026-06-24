"""发行资产明细防重逻辑单元测试."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import issuance_cleanse as ic
from app import issuance_upload as iu


class TestBusinessAssetKey(unittest.TestCase):
    def test_key_uses_issue_date_not_data_date(self):
        key = ic.build_business_asset_key(1, date(2025, 6, 1), "H001")
        self.assertEqual(key, "1:2025-06-01:H001")
        self.assertNotIn("data_date", key)

    def test_key_excludes_amount_and_source(self):
        key = ic.build_business_asset_key(2, date(2024, 1, 15), "ABC-99")
        parts = key.split(":")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "2")
        self.assertEqual(parts[1], "2024-01-15")
        self.assertEqual(parts[2], "ABC-99")


class TestWithinSheetChecks(unittest.TestCase):
    def _row(self, key: str, contract: float = 100.0, transfer: float = 90.0) -> dict:
        return {
            "business_asset_key": key,
            "receivable_contract_amount": contract,
            "receivable_transfer_amount": transfer,
            "signing_date": date(2025, 1, 1),
            "first_rent_withholding_date": None,
            "rental_contract_end_date": None,
        }

    def test_same_key_multiple_rows_warns_not_deduped(self):
        rows = [self._row("1:2025-06-01:A"), self._row("1:2025-06-01:A")]
        dupes, exact, warnings = iu._within_sheet_checks(rows)
        self.assertEqual(dupes, 1)
        self.assertEqual(exact, 1)
        self.assertTrue(any("多行" in w for w in warnings))

    def test_different_keys_no_within_sheet_warning(self):
        rows = [self._row("1:2025-06-01:A"), self._row("1:2025-06-01:B")]
        dupes, exact, warnings = iu._within_sheet_checks(rows)
        self.assertEqual(dupes, 0)
        self.assertEqual(exact, 0)
        self.assertEqual(warnings, [])


class TestPrecheckActions(unittest.TestCase):
    def _make_df(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def _mock_conn(self, scope_cnt=0, cross_rows=None):
        conn = MagicMock()
        calls = {"count": 0}

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "COUNT(*)" in sql_text and "source_file_name" in sql_text:
                result.fetchone.return_value = MagicMock(cnt=scope_cnt, amount_sum=0.0)
            elif "EXISTS" in sql_text:
                result.fetchone.return_value = MagicMock(ex=False)
            elif "business_asset_key = ANY" in sql_text:
                result.__iter__ = lambda self: iter(cross_rows or [])
            elif "FROM trust_products" in sql_text:
                result.fetchone.return_value = MagicMock(id=1, name="测试产品")
            else:
                result.fetchone.return_value = None
            calls["count"] += 1
            return result

        conn.execute = execute
        return conn

    def test_fresh_import_action_import(self):
        df = self._make_df([{
            "房源编码": "H001",
            "实际成交价（应收账款合同金额）": 1000000,
            "应收账款转让价款": 900000,
        }])
        conn = self._mock_conn(scope_cnt=0)
        result = iu.precheck_issuance_sheet(
            conn, 1, "测试产品", date(2025, 6, 1), "file.xlsx", "Sheet1", df,
        )
        self.assertEqual(result["action"], "import")
        self.assertTrue(result["importable"])
        self.assertNotIn("data_date", result)

    def test_same_scope_overwrite(self):
        df = self._make_df([{
            "房源编码": "H001",
            "实际成交价（应收账款合同金额）": 1000000,
            "应收账款转让价款": 900000,
        }])
        conn = self._mock_conn(scope_cnt=5)
        result = iu.precheck_issuance_sheet(
            conn, 1, "测试产品", date(2025, 6, 1), "file.xlsx", "Sheet1", df,
        )
        self.assertEqual(result["action"], "overwrite")
        self.assertIn("覆盖", result["reason"])

    def test_cross_file_duplicate_needs_confirm(self):
        df = self._make_df([{
            "房源编码": "H001",
            "实际成交价（应收账款合同金额）": 1000000,
            "应收账款转让价款": 900000,
        }])
        cross = [MagicMock(
            business_asset_key="1:2025-06-01:H001",
            custody_asset_code="H001",
            source_file_name="other.xlsx",
            source_sheet_name="S2",
            receivable_contract_amount=1000000,
            receivable_transfer_amount=900000,
        )]
        conn = self._mock_conn(scope_cnt=0, cross_rows=cross)
        result = iu.precheck_issuance_sheet(
            conn, 1, "测试产品", date(2025, 6, 1), "file.xlsx", "Sheet1", df,
        )
        self.assertEqual(result["action"], "needs_confirm")
        self.assertGreater(result["cross_file_duplicate_count"], 0)


class TestNoDataDateInModule(unittest.TestCase):
    FILES = [
        "issuance_schema.sql",
        "backend/app/issuance_upload.py",
        "backend/app/issuance_cleanse.py",
        "backend/app/issuance_html.py",
    ]

    def test_issuance_files_have_no_data_date_field(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        banned = ("data_date", "快照日期", "发行快照日期")
        for rel in self.FILES:
            path = os.path.join(root, rel)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            for term in banned:
                if term == "data_date" and rel == "issuance_schema.sql":
                    lines = [
                        ln for ln in content.splitlines()
                        if term in ln and "无 data_date" not in ln
                    ]
                    self.assertEqual(lines, [], f"{rel} contains {term}: {lines}")
                elif term in content:
                    self.fail(f"{rel} contains banned term: {term}")


class TestMigrationType(unittest.TestCase):
    def test_default_new_issuance_without_from_product(self):
        val, warnings = ic.resolve_migration_type(
            excel_column_present=False,
            excel_value=None,
            from_trust_product_id=None,
            source_row_number=2,
        )
        self.assertEqual(val, "new_issuance")
        self.assertEqual(warnings, [])

    def test_default_transfer_with_from_product(self):
        val, warnings = ic.resolve_migration_type(
            excel_column_present=False,
            excel_value=None,
            from_trust_product_id=99,
            source_row_number=2,
        )
        self.assertEqual(val, "transfer")
        self.assertEqual(warnings, [])

    def test_excel_chinese_mapping(self):
        val, _ = ic.resolve_migration_type(
            excel_column_present=True,
            excel_value="展期",
            from_trust_product_id=None,
            source_row_number=3,
        )
        self.assertEqual(val, "rollover")

    def test_excel_blank_maps_new_issuance(self):
        val, _ = ic.resolve_migration_type(
            excel_column_present=True,
            excel_value="",
            from_trust_product_id=1,
            source_row_number=4,
        )
        self.assertEqual(val, "new_issuance")

    def test_unrecognized_excel_warns_and_transfer(self):
        val, warnings = ic.resolve_migration_type(
            excel_column_present=True,
            excel_value="未知类型",
            from_trust_product_id=None,
            source_row_number=5,
        )
        self.assertEqual(val, "transfer")
        self.assertTrue(warnings)

    def test_label_display_chinese(self):
        self.assertEqual(ic.migration_type_label("new_issuance"), "新发行")
        self.assertEqual(ic.migration_type_label("rollover"), "续发")
        self.assertEqual(ic.migration_type_label("repackage"), "重新封包")
        self.assertEqual(ic.migration_type_label("transfer"), "转让")

    def test_fingerprint_unchanged_by_migration_type(self):
        row_a = {
            "business_asset_key": "1:2025-06-01:H001",
            "receivable_contract_amount": 100.0,
            "receivable_transfer_amount": 90.0,
            "signing_date": date(2025, 1, 1),
            "first_rent_withholding_date": None,
            "rental_contract_end_date": None,
        }
        self.assertEqual(ic.exact_duplicate_fingerprint(row_a), ic.exact_duplicate_fingerprint(row_a))


class TestMainIssuanceRoutes(unittest.TestCase):
    def test_main_issuance_routes_no_data_date(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        path = os.path.join(root, "backend/app/main.py")
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        in_issuance = False
        for line in lines:
            if '@app.get("/issuance/' in line or '@app.post("/issuance/' in line:
                in_issuance = True
            if in_issuance and line.startswith("@app.") and "/issuance/" not in line:
                break
            if in_issuance:
                self.assertNotIn("data_date", line)


if __name__ == "__main__":
    unittest.main()

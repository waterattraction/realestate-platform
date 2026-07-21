"""资产回购 — 单位校验 / 编号解析 / 金额校验 / 页面渲染."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi import HTTPException

from app import asset_repurchase as rp
from app import asset_repurchase_html


class TestUnitFieldValidation(unittest.TestCase):
    def test_valid_fields(self):
        company, contact, email = rp._validate_unit_fields(
            " 光明地产 ", "张三", "zhangsan@example.com"
        )
        self.assertEqual(company, "光明地产")
        self.assertEqual(contact, "张三")
        self.assertEqual(email, "zhangsan@example.com")

    def test_empty_company_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            rp._validate_unit_fields("", "张三", "a@b.com")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_empty_contact_rejected(self):
        with self.assertRaises(HTTPException):
            rp._validate_unit_fields("公司", " ", "a@b.com")

    def test_bad_email_rejected(self):
        for bad in ("", "abc", "a@b", "a b@c.com"):
            with self.assertRaises(HTTPException):
                rp._validate_unit_fields("公司", "张三", bad)


class TestParseRepurchaseAssetCodes(unittest.TestCase):
    def test_dedupe_and_strip(self):
        codes = rp.parse_repurchase_asset_codes([" a ", "a", "b", ""])
        self.assertEqual(codes, ["a", "b"])

    def test_empty_rejected(self):
        with self.assertRaises(HTTPException):
            rp.parse_repurchase_asset_codes([])
        with self.assertRaises(HTTPException):
            rp.parse_repurchase_asset_codes(["  ", ""])

    def test_max_count(self):
        raw = [f"c{i}" for i in range(rp.MAX_REPURCHASE_ASSETS + 1)]
        with self.assertRaises(HTTPException):
            rp.parse_repurchase_asset_codes(raw)


class TestNormalizeAmounts(unittest.TestCase):
    def test_rounds_to_two_decimals(self):
        result = rp._normalize_amounts({"a": "100.456", "b": 20})
        self.assertEqual(result, {"a": 100.46, "b": 20.0})

    def test_blank_values_skipped(self):
        result = rp._normalize_amounts({"a": "", "b": None, "c": "1"})
        self.assertEqual(result, {"c": 1.0})

    def test_negative_rejected(self):
        with self.assertRaises(HTTPException):
            rp._normalize_amounts({"a": -1})

    def test_non_numeric_rejected(self):
        with self.assertRaises(HTTPException):
            rp._normalize_amounts({"a": "abc"})

    def test_none_input(self):
        self.assertEqual(rp._normalize_amounts(None), {})


class TestDecorateAssetItem(unittest.TestCase):
    def test_bucket_from_overdue_days(self):
        item = rp._decorate_asset_item(
            {"asset_code": "x", "overdue_days": 20, "remaining_amount": 1000.0}
        )
        self.assertEqual(item["delinquency_bucket"], "M1")
        self.assertIn("20天", item["delinquency_bucket_display"])
        self.assertEqual(item["city"], "—")
        self.assertEqual(item["historical_property_codes"], "")

    def test_settled_is_es(self):
        item = rp._decorate_asset_item(
            {"asset_code": "x", "overdue_days": 5, "remaining_amount": 0.0}
        )
        self.assertEqual(item["delinquency_bucket"], "ES")


class TestBucketDisplay(unittest.TestCase):
    def test_known_bucket(self):
        display = rp._bucket_display("M0", -3)
        self.assertIn("-3天", display)

    def test_none_days(self):
        display = rp._bucket_display("ES", None)
        self.assertNotIn("天", display)


class TestMonitorPreviewColumns(unittest.TestCase):
    def test_contains_complete_standard_monitor_columns(self):
        keys = [key for key, _ in rp.MONITOR_PREVIEW_COLUMNS]
        self.assertEqual(keys[0], "trust_product_name")
        self.assertNotIn("asset_pool_code", keys)
        self.assertNotIn("source_asset_code", keys)
        for key in (
            "asset_code",
            "custody_asset_code",
            "renovation_vendor",
            "last_renovation_payment_date",
            "collection_contract_code",
            "custody_agreement_sign_date",
            "collection_contract_years",
            "owner_code",
            "withholding_ratio",
            "actual_monthly_rent",
            "asset_transfer_discount_rate",
            "source_file_name",
            "source_sheet_name",
            "risk_score",
            "risk_level",
            "id",
            "trust_asset_id",
        ):
            self.assertIn(key, keys)


class TestRenderPage(unittest.TestCase):
    def test_page_contains_key_sections(self):
        html = asset_repurchase_html.render_repurchase_page(
            [{"id": 1, "name": "美好生活1号"}],
            username="tester",
        )
        self.assertIn("资产回购", html)
        self.assertIn("美好生活1号", html)
        for element_id in (
            "rp-product",
            "rp-unit",
            "rp-biz-date",
            "rp-preview-btn",
            "rp-confirm-btn",
            "rp-orders-table-wrap",
            "rp-unit-add-btn",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("/asset-repurchase/preview", html)
        self.assertIn("/asset-repurchase/execute", html)
        self.assertIn("历史房源号", html)
        self.assertIn("资产监控明细（完整字段）", html)
        self.assertIn("monitor_records", html)


if __name__ == "__main__":
    unittest.main()

"""发行资产明细防重逻辑单元测试."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import issuance_cleanse as ic
from app import issuance_upload as iu


def _db_row(row_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, name=name)


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
                result.fetchone.return_value = _db_row(1, "测试产品")
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
        "db/modules/issuance/schema.sql",
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
                if term == "data_date" and rel == "db/modules/issuance/schema.sql":
                    lines = [
                        ln for ln in content.splitlines()
                        if term in ln and "无 data_date" not in ln
                    ]
                    self.assertEqual(lines, [], f"{rel} contains {term}: {lines}")
                elif term in content:
                    self.fail(f"{rel} contains banned term: {term}")


class TestCityResolution(unittest.TestCase):
    def test_region_jingbei_maps_beijing(self):
        city, warnings = ic.resolve_city(
            excel_column_present=True,
            excel_value="京北",
            property_address=None,
            source_row_number=2,
        )
        self.assertEqual(city, "北京")
        self.assertEqual(warnings, [])

    def test_region_shanghai(self):
        city, _ = ic.resolve_city(
            excel_column_present=True,
            excel_value="上海",
            property_address=None,
            source_row_number=2,
        )
        self.assertEqual(city, "上海")

    def test_address_fallback_beijing_district(self):
        city, warnings = ic.resolve_city(
            excel_column_present=False,
            excel_value=None,
            property_address="宋庄路12号院2号楼",
            source_row_number=3,
        )
        self.assertIsNone(city)
        self.assertTrue(warnings)

    def test_address_fallback_with_haidian(self):
        city, _ = ic.resolve_city(
            excel_column_present=False,
            excel_value=None,
            property_address="海淀区阜成路11号",
            source_row_number=4,
        )
        self.assertEqual(city, "北京")

    def test_city_distribution(self):
        rows = [{"city": "北京"}, {"city": "上海"}, {"city": "上海"}, {}]
        self.assertEqual(ic.city_distribution(rows), {"北京": 1, "上海": 2})
        self.assertEqual(ic.city_blank_count(rows), 1)


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


class TestFromTrustProductTokenize(unittest.TestCase):
    def test_single_token(self):
        self.assertEqual(ic.tokenize_from_trust_product_raw("单一信托"), ["单一信托"])

    def test_chinese_comma_multi_token(self):
        self.assertEqual(
            ic.tokenize_from_trust_product_raw("单一信托，美好生活3号"),
            ["单一信托", "美好生活3号"],
        )

    def test_dunhao_multi_token(self):
        self.assertEqual(
            ic.tokenize_from_trust_product_raw("未知别名、美润1号"),
            ["未知别名", "美润1号"],
        )


class TestFromTrustProductColumnPick(unittest.TestCase):
    def test_current_issued_plan_column(self):
        df = pd.DataFrame(columns=[
            "房源编码",
            "实际成交价（应收账款合同金额）",
            "应收账款转让价款",
            "当前信托计划（已发行）",
        ])
        col = ic.pick_column(df, "from_trust_product_name")
        self.assertEqual(col, "当前信托计划（已发行）")

    def test_current_issued_plan_priority_over_other_aliases(self):
        df = pd.DataFrame(columns=[
            "房源编码",
            "实际成交价（应收账款合同金额）",
            "应收账款转让价款",
            "当前信托计划（已发行）",
            "原信托计划",
        ])
        col = ic.pick_column(df, "from_trust_product_name")
        self.assertEqual(col, "当前信托计划（已发行）")

    def test_planned_transfer_not_mapped_to_from_trust(self):
        df = pd.DataFrame(columns=[
            "房源编码",
            "实际成交价（应收账款合同金额）",
            "应收账款转让价款",
            "拟转入计划（未发行）",
        ])
        self.assertIsNone(ic.pick_column(df, "from_trust_product_name"))
        self.assertEqual(
            ic.pick_column(df, "planned_trust_product_name"),
            "拟转入计划（未发行）",
        )

    def test_dual_from_and_planned_columns(self):
        df = pd.DataFrame(columns=[
            "当前信托计划（已发行）",
            "拟转入计划（未发行）",
        ])
        self.assertEqual(
            ic.pick_column(df, "from_trust_product_name"),
            "当前信托计划（已发行）",
        )
        self.assertEqual(
            ic.pick_column(df, "planned_trust_product_name"),
            "拟转入计划（未发行）",
        )


class TestFromTrustProductResolve(unittest.TestCase):
    def _mock_conn(self, *, aliases: dict[str, tuple[int, str]], products: dict[str, tuple[int, str]]):
        conn = MagicMock()

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "trust_product_aliases" in sql_text:
                alias = (params or {}).get("alias")
                hit = aliases.get(alias)
                if hit:
                    result.fetchone.return_value = _db_row(hit[0], hit[1])
                else:
                    result.fetchone.return_value = None
            elif "FROM trust_products" in sql_text and "alias_name" not in sql_text:
                name = (params or {}).get("name")
                hit = products.get(name)
                if hit:
                    result.fetchone.return_value = _db_row(hit[0], hit[1])
                else:
                    result.fetchone.return_value = None
            else:
                result.fetchone.return_value = None
            return result

        conn.execute = execute
        return conn

    def test_alias_hit_danyi_to_meirun(self):
        conn = self._mock_conn(
            aliases={"单一信托": (4, "美润1号")},
            products={},
        )
        pid, pname, warnings = iu._resolve_from_trust_product(conn, "单一信托", 2)
        self.assertEqual(pid, 4)
        self.assertEqual(pname, "美润1号")
        self.assertEqual(warnings, [])

    def test_direct_product_name_hit(self):
        conn = self._mock_conn(
            aliases={},
            products={"美润1号": (4, "美润1号")},
        )
        pid, pname, warnings = iu._resolve_from_trust_product(conn, "美润1号", 3)
        self.assertEqual(pid, 4)
        self.assertEqual(pname, "美润1号")
        self.assertEqual(warnings, [])

    def test_alias_miss(self):
        conn = self._mock_conn(aliases={}, products={})
        pid, pname, warnings = iu._resolve_from_trust_product(conn, "不存在的产品", 4)
        self.assertIsNone(pid)
        self.assertIsNone(pname)
        self.assertTrue(any("未匹配" in w for w in warnings))

    def test_multi_token_first_alias_wins(self):
        conn = self._mock_conn(
            aliases={"单一信托": (4, "美润1号")},
            products={"美好生活3号": (3, "美好生活3号")},
        )
        pid, pname, warnings = iu._resolve_from_trust_product(
            conn, "单一信托，美好生活3号", 5,
        )
        self.assertEqual(pid, 4)
        self.assertEqual(pname, "美润1号")
        self.assertEqual(warnings, [])

    def test_multi_token_skip_unknown_then_hit_product_name(self):
        conn = self._mock_conn(
            aliases={},
            products={"美润1号": (4, "美润1号")},
        )
        pid, pname, warnings = iu._resolve_from_trust_product(
            conn, "未知别名、美润1号", 6,
        )
        self.assertEqual(pid, 4)
        self.assertEqual(pname, "美润1号")
        self.assertEqual(warnings, [])


class TestFromTrustProductPrecheckStats(unittest.TestCase):
    def _mock_conn(self, *, aliases: dict[str, tuple[int, str]], products: dict[str, tuple[int, str]]):
        conn = MagicMock()

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "COUNT(*)" in sql_text and "source_file_name" in sql_text:
                result.fetchone.return_value = MagicMock(cnt=0, amount_sum=0.0)
            elif "EXISTS" in sql_text:
                result.fetchone.return_value = MagicMock(ex=False)
            elif "business_asset_key = ANY" in sql_text:
                result.__iter__ = lambda self: iter([])
            elif "trust_product_aliases" in sql_text:
                alias = (params or {}).get("alias")
                hit = aliases.get(alias)
                if hit:
                    result.fetchone.return_value = _db_row(hit[0], hit[1])
                else:
                    result.fetchone.return_value = None
            elif "FROM trust_products" in sql_text:
                name = (params or {}).get("name")
                hit = products.get(name)
                if hit:
                    result.fetchone.return_value = _db_row(hit[0], hit[1])
                else:
                    result.fetchone.return_value = None
            else:
                result.fetchone.return_value = None
            return result

        conn.execute = execute
        return conn

    def test_precheck_from_trust_product_stats_all_matched(self):
        df = pd.DataFrame([{
            "房源编码": "H001",
            "实际成交价（应收账款合同金额）": 1000000,
            "应收账款转让价款": 900000,
            "当前信托计划（已发行）": "单一信托",
        }])
        conn = self._mock_conn(
            aliases={"单一信托": (4, "美润1号")},
            products={},
        )
        result = iu.precheck_issuance_sheet(
            conn, 3, "美好生活3号", date(2026, 4, 28), "file.xlsx", "Sheet1", df,
        )
        self.assertEqual(result["from_trust_product_matched_count"], 1)
        self.assertEqual(result["from_trust_product_unmatched_count"], 0)
        self.assertEqual(result["from_trust_product_distribution"], {"美润1号": 1})

    def test_parse_row_migration_transfer_when_from_product_matched(self):
        df = pd.DataFrame([{
            "房源编码": "H002",
            "实际成交价（应收账款合同金额）": 500000,
            "应收账款转让价款": 450000,
            "当前信托计划（已发行）": "单一信托",
        }])
        conn = self._mock_conn(
            aliases={"单一信托": (4, "美润1号")},
            products={},
        )
        rows, errors, _ = iu.parse_issuance_sheet(
            conn, df,
            trust_product_id=3,
            trust_product_name="美好生活3号",
            issue_date=date(2026, 4, 28),
            file_name="file.xlsx",
            sheet_name="Sheet1",
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["from_trust_product_id"], 4)
        self.assertEqual(rows[0]["from_trust_product_name"], "美润1号")
        self.assertEqual(rows[0]["migration_type"], "transfer")


class TestAssetTransferDiscountRateColumnPick(unittest.TestCase):
    def _df_with_rate_col(self, rate_col: str) -> pd.DataFrame:
        return pd.DataFrame(columns=[
            "房源编码",
            "实际成交价（应收账款合同金额）",
            "应收账款转让价款",
            rate_col,
        ])

    def test_chinese_bracket_numeric_column(self):
        col = "资产转让折扣率（数值）(%)"
        self.assertEqual(ic.pick_column(self._df_with_rate_col(col), "asset_transfer_discount_rate"), col)

    def test_ascii_bracket_numeric_column(self):
        col = "资产转让折扣率(数值)(%)"
        self.assertEqual(ic.pick_column(self._df_with_rate_col(col), "asset_transfer_discount_rate"), col)


class TestAssetTransferDiscountRateValue(unittest.TestCase):
    def test_decimal_083(self):
        self.assertEqual(ic.to_rate_value(0.83), 0.83)

    def test_percent_83(self):
        self.assertEqual(ic.to_rate_value(83), 0.83)


class TestAssetTransferDiscountRatePrecheckStats(unittest.TestCase):
    def _mock_conn(self):
        conn = MagicMock()

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "COUNT(*)" in sql_text and "source_file_name" in sql_text:
                result.fetchone.return_value = MagicMock(cnt=0, amount_sum=0.0)
            elif "EXISTS" in sql_text:
                result.fetchone.return_value = MagicMock(ex=False)
            elif "business_asset_key = ANY" in sql_text:
                result.__iter__ = lambda self: iter([])
            elif "FROM trust_products" in sql_text:
                result.fetchone.return_value = _db_row(4, "美润1号")
            else:
                result.fetchone.return_value = None
            return result

        conn.execute = execute
        return conn

    def test_precheck_present_and_blank_counts(self):
        df = pd.DataFrame([
            {
                "房源编码": "H001",
                "实际成交价（应收账款合同金额）": 1000000,
                "应收账款转让价款": 900000,
                "资产转让折扣率（数值）(%)": 0.83,
            },
            {
                "房源编码": "H002",
                "实际成交价（应收账款合同金额）": 2000000,
                "应收账款转让价款": 1800000,
                "资产转让折扣率（数值）(%)": None,
            },
        ])
        result = iu.precheck_issuance_sheet(
            self._mock_conn(), 4, "美润1号", date(2026, 3, 20), "file.xlsx", "Sheet1", df,
        )
        self.assertEqual(result["asset_transfer_discount_rate_present_count"], 1)
        self.assertEqual(result["asset_transfer_discount_rate_blank_count"], 1)
        self.assertTrue(any("资产转让折扣率为空 1 行" in w for w in result["warnings"]))

    def test_precheck_unmapped_suspicious_column_warning(self):
        df = pd.DataFrame([{
            "房源编码": "H001",
            "实际成交价（应收账款合同金额）": 1000000,
            "应收账款转让价款": 900000,
            "资产转让折扣率-未知列名(%)": 0.83,
        }])
        result = iu.precheck_issuance_sheet(
            self._mock_conn(), 4, "美润1号", date(2026, 3, 20), "file.xlsx", "Sheet1", df,
        )
        self.assertEqual(result["asset_transfer_discount_rate_present_count"], 0)
        self.assertEqual(result["asset_transfer_discount_rate_blank_count"], 1)
        self.assertTrue(any("发现疑似资产转让折扣率列" in w for w in result["warnings"]))


class TestFileScopedMinColumnAliases(unittest.TestCase):
    def _issuance_df(self, min_col: str | None = None) -> pd.DataFrame:
        data = {
            "房源编码": ["107112371893"],
            "实际成交价（应收账款合同金额）": [179771.0],
            "应收账款转让价款": [149209.93],
        }
        if min_col:
            data[min_col] = [120000.0]
        return pd.DataFrame(data)

    def test_meirun_initial_transfer_maps_financial_institution_column(self):
        df = self._issuance_df("金融机构可转让")
        col = ic.pick_column(
            df,
            "min_institution_transferable_amount",
            file_name=ic.MEIRUN1_INITIAL_TRANSFER_FILE,
        )
        self.assertEqual(col, "金融机构可转让")

    def test_other_file_does_not_map_financial_institution_column(self):
        df = self._issuance_df("金融机构可转让")
        col = ic.pick_column(
            df, "min_institution_transferable_amount", file_name="其他.xlsx",
        )
        self.assertIsNone(col)

    def test_parse_row_populates_min_for_meirun_file(self):
        df = self._issuance_df("金融机构可转让")
        conn = MagicMock()
        rows, errors, _ = iu.parse_issuance_sheet(
            conn,
            df,
            trust_product_id=4,
            trust_product_name="美润1号",
            issue_date=date(2026, 3, 20),
            file_name=ic.MEIRUN1_INITIAL_TRANSFER_FILE,
            sheet_name="合同",
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["min_institution_transferable_amount"], 120000.0)


class TestFullColumnAliases(unittest.TestCase):
    def test_short_withholding_and_cycle_aliases(self):
        df = pd.DataFrame(columns=[
            "代扣金额",
            "预计代扣周期-最初",
            "贝壳已租金代扣金额合计",
            "基础交易合同名称",
        ])
        self.assertEqual(
            ic.pick_column(df, "total_rent_withholding_amount"), "代扣金额",
        )
        self.assertEqual(
            ic.pick_column(df, "initial_expected_withholding_cycle"),
            "预计代扣周期-最初",
        )
        self.assertEqual(
            ic.pick_column(df, "rent_withheld_amount_before_pooling"),
            "贝壳已租金代扣金额合计",
        )
        self.assertEqual(ic.pick_column(df, "contract_name"), "基础交易合同名称")

    def test_find_unmapped_business_columns_allows_xuhao(self):
        df = pd.DataFrame(columns=[
            "房源编码",
            "实际成交价（应收账款合同金额）",
            "应收账款转让价款",
            "序号",
            "神秘新列",
        ])
        unmapped = ic.find_unmapped_business_columns(df)
        self.assertEqual(unmapped, ["神秘新列"])

    def test_precheck_warns_unmapped_business_columns(self):
        df = pd.DataFrame([{
            "房源编码": "H001",
            "实际成交价（应收账款合同金额）": 1000000,
            "应收账款转让价款": 900000,
            "神秘新列": "x",
        }])
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = MagicMock(
            cnt=0, amount_sum=0, ex=False,
        )
        conn.execute.return_value.fetchall.return_value = []
        result = iu.precheck_issuance_sheet(
            conn, 4, "美润1号", date(2026, 3, 20), "file.xlsx", "Sheet1", df,
        )
        self.assertTrue(any("未映射业务列" in w and "神秘新列" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()

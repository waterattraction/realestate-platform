"""还款/监控导入 · 资产编码权威性与预检 ERROR 单元测试."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_upload as iu


def _repayment_row(
    asset_no: str,
    custody_no: str,
    *,
    amount: float = 1000.0,
    period: int = 1,
    repay_date: str = "2026-06-12",
) -> dict:
    return {
        "资产编号(房源)": asset_no,
        "托管房源编码": custody_no,
        "当期实际还款金额": amount,
        "还款期数": period,
        "当期还款日期": repay_date,
    }


def _monitor_row(
    asset_no: str,
    custody_no: str,
    *,
    stat_date: str = "2026-06-12",
) -> dict:
    return {
        "资产编号(房源)": asset_no,
        "托管房源编码": custody_no,
        "统计日期": stat_date,
        "初始受让金额": 50000.0,
        "已还款金额": 10000.0,
        "剩余还款金额": 40000.0,
    }


class TestNormalizeExcelAssetCode(unittest.TestCase):
    def test_strips_excel_float_suffix(self):
        self.assertEqual(iu._normalize_excel_asset_code(107114177883.0), "107114177883")

    def test_plain_string_unchanged(self):
        self.assertEqual(iu._normalize_excel_asset_code("107114177883"), "107114177883")


class TestResolveMonitorAssetFields(unittest.TestCase):
    def test_trust_custody_primary_split(self):
        row = pd.Series(_monitor_row("101127075900-001", "101127075900"))
        asset, custody, source = iu._resolve_monitor_asset_fields(
            row, "资产编号(房源)", "托管房源编码",
        )
        self.assertEqual(source, "101127075900-001")
        self.assertEqual(custody, "101127075900")
        self.assertEqual(asset, "101127075900")

    def test_trust_only_fills_custody_from_primary(self):
        row = pd.Series({
            "资产编号(房源)": "101127075900-001",
            "统计日期": "2026-06-12",
            "初始受让金额": 1.0,
            "已还款金额": 1.0,
            "剩余还款金额": 1.0,
        })
        asset, custody, source = iu._resolve_monitor_asset_fields(
            row, "资产编号(房源)", None,
        )
        self.assertEqual(source, "101127075900-001")
        self.assertEqual(asset, "101127075900")
        self.assertEqual(custody, "101127075900")


class TestResolveAssetFields(unittest.TestCase):
    def test_asset_number_is_authoritative_when_columns_differ(self):
        row = pd.Series(_repayment_row("107114177883", "107114502274"))
        asset, custody, source = iu._resolve_asset_fields(
            row, "资产编号(房源)", "托管房源编码",
        )
        self.assertEqual(asset, "107114177883")
        self.assertEqual(custody, "107114177883")
        self.assertEqual(source, "107114177883")

    def test_aligned_columns_use_same_value(self):
        row = pd.Series(_repayment_row("107114177883", "107114177883"))
        asset, custody, source = iu._resolve_asset_fields(
            row, "资产编号(房源)", "托管房源编码",
        )
        self.assertEqual((asset, custody, source), ("107114177883",) * 3)

    def test_custody_only_when_asset_column_missing(self):
        row = pd.Series({"托管房源编码": "107114502274"})
        asset, custody, source = iu._resolve_asset_fields(row, None, "托管房源编码")
        self.assertEqual((asset, custody, source), ("107114502274",) * 3)

    def test_empty_when_both_missing(self):
        row = pd.Series({})
        self.assertEqual(iu._resolve_asset_fields(row, None, None), (None, None, None))


class TestExcelCustodySourceMismatchRows(unittest.TestCase):
    def test_detects_mismatch_rows(self):
        df = pd.DataFrame([
            _repayment_row("107114177883", "107114502274"),
            _repayment_row("A", "A"),
        ])
        mismatches = iu._excel_custody_source_mismatch_rows(df)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["excel_row"], 2)
        self.assertEqual(mismatches[0]["asset_number"], "107114177883")
        self.assertEqual(mismatches[0]["custody_from_excel"], "107114502274")

    def test_returns_empty_when_columns_missing(self):
        df = pd.DataFrame([{"托管房源编码": "X"}])
        self.assertEqual(iu._excel_custody_source_mismatch_rows(df), [])


class TestApplyAssetCodeMismatchPrecheck(unittest.TestCase):
    def test_sets_needs_confirm_and_error_warning(self):
        result: dict = {
            "action": "import",
            "importable": True,
            "reason": "可导入",
            "warnings": [],
        }
        mismatches = [{"excel_row": 2, "asset_number": "A", "custody_from_excel": "B"}]
        iu._apply_asset_code_mismatch_precheck(result, mismatches)
        self.assertEqual(result["action"], "needs_confirm")
        self.assertTrue(result["importable"])
        self.assertEqual(result["asset_code_mismatch_count"], 1)
        self.assertTrue(any("[ERROR]" in w for w in result["warnings"]))
        self.assertIn("权威字段", result["reason"])

    def test_does_not_override_failed(self):
        result = {"action": "failed", "warnings": [], "reason": "解析失败"}
        iu._apply_asset_code_mismatch_precheck(
            result,
            [{"excel_row": 2, "asset_number": "A", "custody_from_excel": "B"}],
        )
        self.assertEqual(result["action"], "failed")


class TestParseRepaymentRowsRegression0612(unittest.TestCase):
    def test_mismatched_excel_row_uses_source_not_custody(self):
        df = pd.DataFrame([_repayment_row("107114177883", "107114502274")])
        rows, errors = iu._parse_repayment_rows(df, date(2026, 6, 12))
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source_asset_code"], "107114177883")
        self.assertEqual(row["custody_asset_code"], "107114177883")
        self.assertEqual(row["asset_code"], "107114177883")
        self.assertNotEqual(row["custody_asset_code"], "107114502274")


class TestUpsertTrustAssetLookupOrder(unittest.TestCase):
    def _conn(self, *, by_source=None, by_asset=None, by_custody=None):
        conn = MagicMock()
        calls: list[str] = []

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "source_asset_code = :source" in sql_text:
                calls.append("source")
                result.fetchone.return_value = by_source
            elif "asset_code = :code" in sql_text and "INSERT" not in sql_text:
                calls.append("asset")
                result.fetchone.return_value = by_asset
            elif "custody_asset_code = :custody" in sql_text:
                calls.append("custody")
                result.fetchone.return_value = by_custody
            elif "INSERT INTO trust_assets" in sql_text:
                calls.append("insert")
                result.fetchone.return_value = SimpleNamespace(id=99)
            else:
                calls.append("update")
                result.fetchone.return_value = None
            return result

        conn.execute = execute
        conn._calls = calls
        return conn

    def test_lookup_source_asset_code_first(self):
        existing = SimpleNamespace(id=10, asset_code="107114177883")
        conn = self._conn(by_source=existing)
        asset_id = iu._upsert_trust_asset(
            conn, 3, "107114502274", "107114502274", 0.0, "107114177883",
        )
        self.assertEqual(asset_id, 10)
        self.assertEqual(conn._calls[0], "source")
        self.assertNotIn("custody", conn._calls)

    def test_skips_custody_lookup_when_custody_differs_from_source(self):
        conn = self._conn(by_source=None, by_asset=None, by_custody=SimpleNamespace(id=20, asset_code="X"))
        asset_id = iu._upsert_trust_asset(
            conn, 3, "107114177883", "107114502274", 0.0, "107114177883",
        )
        self.assertEqual(asset_id, 99)
        self.assertNotIn("custody", conn._calls)

    def test_custody_lookup_when_distinct_custody(self):
        existing = SimpleNamespace(id=30, asset_code="101127075900")
        conn = self._conn(by_source=None, by_asset=None, by_custody=existing)
        asset_id = iu._upsert_trust_asset(
            conn,
            3,
            "101127075900",
            "101127075900",
            0.0,
            "101127075900-001",
            distinct_custody=True,
        )
        self.assertEqual(asset_id, 30)
        self.assertIn("custody", conn._calls)


class TestPrecheckRepaymentSheetMismatch(unittest.TestCase):
    def _mock_conn(self, *, db_cnt: int = 0):
        conn = MagicMock()

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "COUNT(*)" in sql_text and "trust_repayment_detail_records" in sql_text:
                result.fetchone.return_value = MagicMock(cnt=db_cnt, total=0.0)
            elif "source_file_name !=" in sql_text:
                result.fetchone.return_value = None
            else:
                result.fetchone.return_value = None
                result.__iter__ = lambda self: iter([])
            return result

        conn.execute = execute
        return conn

    def test_mismatch_upgrades_import_to_needs_confirm(self):
        df = pd.DataFrame([_repayment_row("107114177883", "107114502274")])
        result = iu.precheck_repayment_sheet(
            conn=self._mock_conn(),
            trust_product_id=3,
            product_name="美好生活3号",
            file_name="美好生活3号-还款明细披露信息_20260612.xlsx",
            sheet_name="0612已还款",
            df=df,
        )
        self.assertEqual(result["action"], "needs_confirm")
        self.assertTrue(result["importable"])
        self.assertEqual(result["asset_code_mismatch_count"], 1)
        self.assertTrue(any("[ERROR]" in w for w in result["warnings"]))

    def test_aligned_columns_allow_import(self):
        df = pd.DataFrame([_repayment_row("107114177883", "107114177883")])
        result = iu.precheck_repayment_sheet(
            conn=self._mock_conn(),
            trust_product_id=3,
            product_name="美好生活3号",
            file_name="美好生活3号-还款明细披露信息_20260612.xlsx",
            sheet_name="0612已还款",
            df=df,
        )
        self.assertEqual(result["action"], "import")
        self.assertNotIn("asset_code_mismatch_count", result)


class TestMonitorPrecheckConfirmRules(unittest.TestCase):
    def test_first_import_needs_confirm(self):
        reasons = iu._monitor_precheck_confirm_reasons(
            latest_date=None,
            latest_total=0,
            latest_codes=set(),
            excel_rows=3,
            excel_codes={"101127075900"},
            sheet_db_cnt=0,
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("首次导入", reasons[0])

    def test_row_count_mismatch_on_latest_snapshot(self):
        reasons = iu._monitor_precheck_confirm_reasons(
            latest_date=date(2026, 6, 12),
            latest_total=111,
            latest_codes={"101127075900"},
            excel_rows=110,
            excel_codes={"101127075900"},
            sheet_db_cnt=0,
        )
        self.assertTrue(any("记录数不一致" in r for r in reasons))

    def test_unknown_primary_codes(self):
        reasons = iu._monitor_precheck_confirm_reasons(
            latest_date=date(2026, 6, 12),
            latest_total=1,
            latest_codes={"101127075900"},
            excel_rows=1,
            excel_codes={"101127075901"},
            sheet_db_cnt=0,
        )
        self.assertTrue(any("不在最新快照日" in r for r in reasons))

    def test_new_snapshot_same_total_no_confirm(self):
        reasons = iu._monitor_precheck_confirm_reasons(
            latest_date=date(2026, 6, 12),
            latest_total=111,
            latest_codes={"101127075900"},
            excel_rows=111,
            excel_codes={"101127075900"},
            sheet_db_cnt=0,
        )
        self.assertEqual(reasons, [])


class TestPrecheckMonitorSheetMismatch(unittest.TestCase):
    def _mock_conn(
        self,
        *,
        sheet_db_cnt: int = 0,
        latest_date: date | None = None,
        latest_total: int = 0,
        latest_codes: set[str] | None = None,
    ):
        conn = MagicMock()
        latest_codes = latest_codes or set()

        def execute(sql, params=None):
            sql_text = str(sql)
            result = MagicMock()
            if "MAX(data_date)" in sql_text:
                result.fetchone.return_value = MagicMock(
                    latest_date=latest_date,
                )
            elif "COUNT(*)" in sql_text and "DISTINCT" not in sql_text:
                if params and params.get("sheet"):
                    result.fetchone.return_value = MagicMock(cnt=sheet_db_cnt)
                else:
                    result.fetchone.return_value = MagicMock(cnt=latest_total)
            elif "DISTINCT asset_code" in sql_text:
                result.__iter__ = lambda self: iter(
                    [MagicMock(asset_code=c) for c in latest_codes]
                )
            elif "duplicate_batch" in sql_text or "GROUP BY" in sql_text:
                result.__iter__ = lambda self: iter([])
            else:
                result.fetchone.return_value = None
                result.__iter__ = lambda self: iter([])
            return result

        conn.execute = execute
        return conn

    def test_trust_custody_difference_allows_import_when_aligned_counts(self):
        df = pd.DataFrame([_monitor_row("101127075900-001", "101127075900")])
        result = iu.precheck_monitor_sheet(
            conn=self._mock_conn(
                latest_date=date(2026, 6, 12),
                latest_total=1,
                latest_codes={"101127075900"},
            ),
            trust_product_id=3,
            product_name="美好生活3号",
            file_name="美好生活3号-资产监控表_0612.xlsx",
            sheet_name="资产监控",
            df=df,
        )
        self.assertEqual(result["action"], "import")
        self.assertNotIn("asset_code_mismatch_count", result)

    def test_first_import_needs_confirm(self):
        df = pd.DataFrame([_monitor_row("101127075900-001", "101127075900")])
        result = iu.precheck_monitor_sheet(
            conn=self._mock_conn(latest_date=None),
            trust_product_id=3,
            product_name="美好生活3号",
            file_name="美好生活3号-资产监控表_0612.xlsx",
            sheet_name="资产监控",
            df=df,
        )
        self.assertEqual(result["action"], "needs_confirm")
        self.assertIn("首次导入", result["reason"])


class TestAssetCodeGlobalPolicy(unittest.TestCase):
    """asset_code 为历史字段：新逻辑不得修改 trust_assets.asset_code。"""

    BANNED_IN_UPSERT = (
        "SET asset_code =",
        "asset_code = :new",
    )

    def test_upsert_trust_asset_does_not_overwrite_asset_code(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "app", "assetinfo_upload.py",
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        update_block = content.split("def _upsert_trust_asset", 1)[1].split("def _resolve_asset_fields", 1)[0]
        for banned in self.BANNED_IN_UPSERT:
            self.assertNotIn(banned, update_block, f"_upsert_trust_asset must not {banned}")

    def test_identifiers_doc_marks_asset_code_immutable(self):
        path = os.path.join(os.path.dirname(__file__), "..", "docs", "standards", "identifiers.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("可变性", text)
        self.assertIn("asset_code", text)
        self.assertIn("否", text)


if __name__ == "__main__":
    unittest.main()

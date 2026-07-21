"""披露还款明细：仅披露截止日当天且实际还款 > 0。"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import disclosure


class DisclosureRepaymentAsOfFilterTests(unittest.TestCase):
    def test_fetch_sql_requires_as_of_date_and_positive_actual(self):
        """抓取 SQL 文本：截止日等值 + actual > 0（不扫历史 ≤ as_of）。"""
        captured: dict = {}

        class _Result:
            def fetchall(self):
                return []

        def fake_execute(stmt, params=None):
            sql = str(stmt)
            captured.setdefault("sqls", []).append(sql)
            captured.setdefault("params", []).append(params)
            return _Result()

        conn = MagicMock()
        conn.execute.side_effect = fake_execute
        disclosure.fetch_repayment_live(conn, [2], date(2026, 7, 17))

        detail_sql = captured["sqls"][0]
        self.assertIn("r.repayment_date = :as_of", detail_sql)
        self.assertIn("r.actual_repayment_amount > 0", detail_sql)
        self.assertNotIn("r.repayment_date <= :as_of", detail_sql)
        self.assertEqual(captured["params"][0]["as_of"], date(2026, 7, 17))


if __name__ == "__main__":
    unittest.main()

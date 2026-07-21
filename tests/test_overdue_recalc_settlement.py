"""逾期重算纳入手工结算：SQL 契约（不连库）。"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.overdue.recalc_monitor import recompute_monitor_overdue_for_scope


class RecalcMonitorSettlementSqlTests(unittest.TestCase):
    def test_sql_includes_settlement_anchor_and_as_of_cutoff(self):
        captured: list[tuple[str, dict]] = []

        class _Result:
            rowcount = 0

            def fetchall(self):
                return []

            def fetchone(self):
                return None

        def fake_execute(stmt, params=None):
            captured.append((str(stmt), dict(params or {})))
            return _Result()

        conn = MagicMock()
        conn.execute.side_effect = fake_execute

        recompute_monitor_overdue_for_scope(
            conn,
            trust_product_id=2,
            data_date=date(2026, 7, 17),
            as_of=date(2026, 7, 21),
        )

        self.assertGreaterEqual(len(captured), 3)
        joined = "\n".join(s for s, _ in captured)
        self.assertIn("trust_asset_manual_settlements", joined)
        self.assertIn("settlement_date <= CAST(:as_of AS date)", joined)
        self.assertIn("voided_at IS NULL", joined)
        # 锚点合并导入还款与结算日
        self.assertIn("VALUES (rp.max_rd), (ms.max_sd)", joined)
        # 有效剩余
        self.assertIn("settlement_sum", joined)

        first_params = captured[0][1]
        self.assertEqual(first_params["as_of"], date(2026, 7, 21))
        self.assertEqual(first_params["data_date"], date(2026, 7, 17))
        self.assertEqual(first_params["trust_product_id"], 2)


if __name__ == "__main__":
    unittest.main()

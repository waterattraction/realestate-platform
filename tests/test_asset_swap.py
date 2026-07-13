"""资产置换推荐."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import asset_swap


class TestParseAssetCodes(unittest.TestCase):
    def test_split_by_comma_and_newline(self):
        codes = asset_swap.parse_asset_code_list("a, b\nc", max_count=10)
        self.assertEqual(codes, ["a", "b", "c"])

    def test_dedupe(self):
        codes = asset_swap.parse_asset_code_list(["a", "a", "b"], max_count=10)
        self.assertEqual(codes, ["a", "b"])


class TestAddMonths(unittest.TestCase):
    def test_add_36_months(self):
        result = asset_swap._add_months(date(2026, 4, 28), 36)
        self.assertEqual(result, date(2029, 4, 28))


class TestComboSort(unittest.TestCase):
    def _c(self, code: str, remaining: float, rate: float) -> asset_swap.Candidate:
        return asset_swap.Candidate(
            asset_code=code,
            custody_asset_code=code,
            remaining_amount=remaining,
            asset_transfer_discount_rate=rate,
            last_renovation_payment_date=date(2028, 1, 1),
            data_date=date(2026, 7, 3),
            city="北京",
            delinquency_bucket="M1",
            overdue_days=0,
        )

    def test_scheme_a_prefers_min_count(self):
        candidates = [
            self._c("a", 5000, 0.86),
            self._c("b", 3000, 0.86),
            self._c("c", 2500, 0.86),
        ]
        r0, k0, c0 = 4000, 0.86, 4000 * 0.86
        combos, min_n = asset_swap.scheme_a_combinations(
            candidates, r0, c0, k0, limit=1
        )
        self.assertEqual(min_n, 1)
        self.assertEqual(combos[0]["asset_count"], 1)
        self.assertEqual(combos[0]["assets"][0]["asset_code"], "a")

    def test_scheme_a_two_assets_when_one_insufficient(self):
        candidates = [
            self._c("a", 2000, 0.86),
            self._c("b", 2500, 0.86),
        ]
        r0, k0, c0 = 4000, 0.86, 4000 * 0.86
        combos, min_n = asset_swap.scheme_a_combinations(
            candidates, r0, c0, k0, limit=1
        )
        self.assertEqual(min_n, 2)
        self.assertEqual(combos[0]["asset_count"], 2)

    def test_scheme_a_prefers_lower_rate_at_same_surplus(self):
        candidates = [
            self._c("low", 5000, 0.86),
            self._c("high", 5000, 0.95),
        ]
        r0, k0, c0 = 4000, 0.86, 4000 * 0.86
        combos, min_n = asset_swap.scheme_a_combinations(
            candidates, r0, c0, k0, limit=1
        )
        self.assertEqual(min_n, 1)
        self.assertEqual(combos[0]["assets"][0]["asset_code"], "low")
        self.assertLess(
            combos[0]["weighted_cost"],
            asset_swap._combo_weighted_cost([candidates[1]]),
        )

    def test_scheme_b_greedy(self):
        candidates = [
            self._c("a", 3000, 0.86),
            self._c("b", 2000, 0.86),
        ]
        r0, k0, c0 = 4000, 0.86, 4000 * 0.86
        combos = asset_swap.scheme_b_combinations(candidates, r0, c0, k0)
        self.assertGreaterEqual(len(combos), 1)
        total = combos[0]["total_remaining"]
        self.assertGreaterEqual(total, 4000)

    def test_scheme_a_includes_pinned(self):
        pinned = [self._c("pin", 1500, 0.86)]
        pool = [
            self._c("a", 3000, 0.86),
            self._c("b", 2000, 0.86),
        ]
        r0, k0, c0 = 4000, 0.86, 4000 * 0.86
        combos, min_n = asset_swap.scheme_a_combinations(
            pool,
            r0,
            c0,
            k0,
            pinned=pinned,
            required_codes={"pin"},
            limit=1,
        )
        self.assertEqual(min_n, 2)
        codes = {a["asset_code"] for a in combos[0]["assets"]}
        self.assertIn("pin", codes)
        self.assertTrue(combos[0]["assets"][0]["pinned"] or any(
            a["pinned"] for a in combos[0]["assets"] if a["asset_code"] == "pin"
        ))

    def test_scheme_a_pinned_alone_covers_target(self):
        pinned = [self._c("pin", 5000, 0.86)]
        r0, k0, c0 = 4000, 0.86, 4000 * 0.86
        combos, min_n = asset_swap.scheme_a_combinations(
            [],
            r0,
            c0,
            k0,
            pinned=pinned,
            required_codes={"pin"},
            limit=1,
        )
        self.assertEqual(min_n, 1)
        self.assertEqual(combos[0]["asset_count"], 1)
        self.assertEqual(combos[0]["assets"][0]["asset_code"], "pin")

    def test_required_ineligibility_m2(self):
        reason = asset_swap._required_asset_ineligibility_reason(
            remaining=10000,
            overdue_days=45,
            delinquency_bucket="M2",
            last_renovation_payment_date=date(2027, 1, 1),
            discount_rate=0.9,
            transferred=False,
            renovation_deadline=date(2028, 9, 25),
        )
        self.assertIn("M2", reason or "")
        self.assertIn("45", reason or "")

    def test_required_ineligibility_low_rate_allowed(self):
        reason = asset_swap._required_asset_ineligibility_reason(
            remaining=10000,
            overdue_days=10,
            delinquency_bucket="M1",
            last_renovation_payment_date=date(2027, 1, 1),
            discount_rate=0.86,
            transferred=False,
            renovation_deadline=date(2028, 9, 25),
        )
        self.assertIsNone(reason)

    def test_required_ineligibility_renovation_deadline(self):
        reason = asset_swap._required_asset_ineligibility_reason(
            remaining=10000,
            overdue_days=10,
            delinquency_bucket="M1",
            last_renovation_payment_date=date(2029, 1, 1),
            discount_rate=0.9,
            transferred=False,
            renovation_deadline=date(2028, 9, 25),
        )
        self.assertIn("装修款截止日", reason or "")

    def test_required_ineligibility_ok(self):
        reason = asset_swap._required_asset_ineligibility_reason(
            remaining=10000,
            overdue_days=10,
            delinquency_bucket="M1",
            last_renovation_payment_date=date(2027, 1, 1),
            discount_rate=0.9,
            transferred=False,
            renovation_deadline=date(2028, 9, 25),
        )
        self.assertIsNone(reason)


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL not set")
class TestAssetSwapIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.db import get_engine

        cls.engine = get_engine()

    def test_meihaosheng_products(self):
        with self.engine.connect() as conn:
            products = asset_swap.fetch_meihaosheng_products(conn)
        self.assertTrue(all(p["name"].startswith("美好生活") for p in products))

    def test_resolve_meirun(self):
        with self.engine.connect() as conn:
            pid = asset_swap.resolve_meirun_product_id(conn)
        self.assertIsInstance(pid, int)

    def test_recommendations_shape(self):
        with self.engine.connect() as conn:
            products = asset_swap.fetch_meihaosheng_products(conn)
        if not products:
            self.skipTest("no products")
        pid = products[0]["id"]
        with self.engine.connect() as conn:
            row = conn.execute(
                __import__("sqlalchemy").text("""
                    SELECT r.asset_code
                    FROM trust_asset_monitor_records r
                    INNER JOIN (
                        SELECT trust_product_id, trust_asset_id, MAX(data_date) AS data_date
                        FROM trust_asset_monitor_records
                        GROUP BY trust_product_id, trust_asset_id
                    ) latest_snap
                        ON latest_snap.trust_product_id = r.trust_product_id
                       AND latest_snap.trust_asset_id = r.trust_asset_id
                       AND latest_snap.data_date = r.data_date
                    WHERE r.trust_product_id = :pid
                      AND r.remaining_amount > 0.01
                    LIMIT 1
                """),
                {"pid": pid},
            ).fetchone()
        if not row:
            self.skipTest("no monitor asset")
        with self.engine.connect() as conn:
            data = asset_swap.fetch_swap_recommendations(
                conn,
                trust_product_id=pid,
                asset_codes=[str(row.asset_code)],
                exclude_asset_codes=[],
            )
        self.assertIn("schemes", data)
        self.assertIn("a", data["schemes"])
        self.assertIn("b", data["schemes"])
        self.assertIn("c", data["schemes"])
        self.assertIn("required", data)


class TestRenderSwapPage(unittest.TestCase):
    def test_render_does_not_raise(self):
        from app import asset_swap_html

        html = asset_swap_html.render_swap_page(
            [{"id": 1, "name": "美好生活1号"}],
            username="admin",
        )
        self.assertIn("资产置换推荐", html)
        self.assertIn("手工指定房源", html)
        self.assertIn("localStorage", html)
        self.assertIn("资产主编号", html)
        self.assertIn("class=\"container\"", html)


if __name__ == "__main__":
    unittest.main()

import unittest

from app.overdue.buckets import (
    M0_5_MAX_DAYS,
    M0_MAX_DAYS,
    M1_MAX_DAYS,
    M1_PLUS_MIN_DAYS,
    OVERDUE_ASSET_MIN_DAYS,
    calc_delinquency_bucket,
    is_overdue_asset,
    matches_delinquency_bucket_filter,
    normalize_delinquency_bucket_filter,
    stage_from_overdue_days,
)
from app.overdue.overdue_days import add_calendar_months, compute_overdue_days
from datetime import date


class DelinquencyBucketTests(unittest.TestCase):
    def test_boundaries_with_balance(self):
        cases = [
            (-5, "M0"),
            (0, "M0"),
            (1, "M0_5"),
            (15, "M0_5"),
            (16, "M1"),
            (30, "M1"),
            (31, "M1_PLUS"),
        ]
        for days, expected in cases:
            with self.subTest(days=days):
                self.assertEqual(calc_delinquency_bucket(days, 100.0), expected)

    def test_null_days_not_m0(self):
        self.assertIsNone(calc_delinquency_bucket(None, 100.0))

    def test_es_when_settled(self):
        self.assertEqual(calc_delinquency_bucket(100, 0.0), "ES")
        self.assertEqual(calc_delinquency_bucket(None, 0.0), "ES")

    def test_overdue_asset_min_days(self):
        self.assertEqual(OVERDUE_ASSET_MIN_DAYS, 1)
        self.assertFalse(is_overdue_asset(0, 100.0))
        self.assertFalse(is_overdue_asset(-3, 100.0))
        self.assertTrue(is_overdue_asset(1, 100.0))
        self.assertFalse(is_overdue_asset(None, 100.0))

    def test_stage_skips_non_positive(self):
        self.assertIsNone(stage_from_overdue_days(0))
        self.assertIsNone(stage_from_overdue_days(-1))
        self.assertEqual(stage_from_overdue_days(1), "M0.5")
        self.assertEqual(stage_from_overdue_days(15), "M0.5")
        self.assertEqual(stage_from_overdue_days(16), "M1")
        self.assertEqual(stage_from_overdue_days(31), "M1+")

    def test_constants(self):
        self.assertEqual(M0_MAX_DAYS, 0)
        self.assertEqual(M0_5_MAX_DAYS, 15)
        self.assertEqual(M1_MAX_DAYS, 30)
        self.assertEqual(M1_PLUS_MIN_DAYS, 31)

    def test_matches_delinquency_bucket_filter(self):
        self.assertTrue(matches_delinquency_bucket_filter("M0_5", "M0_PLUS"))
        self.assertTrue(matches_delinquency_bucket_filter("M1", "M0_PLUS"))
        self.assertTrue(matches_delinquency_bucket_filter("M1_PLUS", "M0_PLUS"))
        self.assertFalse(matches_delinquency_bucket_filter("M0", "M0_PLUS"))
        self.assertFalse(matches_delinquency_bucket_filter("ES", "M0_PLUS"))
        self.assertTrue(matches_delinquency_bucket_filter("M0_5", "M2"))  # legacy
        self.assertTrue(matches_delinquency_bucket_filter("M1", "M3"))  # legacy
        self.assertTrue(matches_delinquency_bucket_filter("M1_PLUS", "M3_PLUS"))

    def test_normalize_legacy_filters(self):
        self.assertEqual(normalize_delinquency_bucket_filter("M2_PLUS"), "M0_PLUS")
        self.assertEqual(normalize_delinquency_bucket_filter("M2"), "M0_5")
        self.assertEqual(normalize_delinquency_bucket_filter("M0"), "M0")
        # bare M1 is canonical new M1 (no remap — collides with legacy performing)
        self.assertEqual(normalize_delinquency_bucket_filter("M1"), "M1")

    def test_month_end_and_overdue_formula(self):
        self.assertEqual(add_calendar_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_calendar_months(date(2026, 5, 29), 1), date(2026, 6, 29))
        # as_of 2026-07-20, last pay 2026-05-29 → due 2026-06-29 → 21 days
        self.assertEqual(
            compute_overdue_days(date(2026, 7, 20), date(2026, 5, 29)),
            21,
        )
        self.assertEqual(
            compute_overdue_days(date(2026, 6, 20), date(2026, 5, 29)),
            -9,
        )


if __name__ == "__main__":
    unittest.main()

import unittest

from app.overdue.buckets import (
    M1_MAX_DAYS,
    M2_MAX_DAYS,
    M3_MAX_DAYS,
    M3_PLUS_MIN_DAYS,
    OVERDUE_ASSET_MIN_DAYS,
    calc_delinquency_bucket,
    is_overdue_asset,
    matches_delinquency_bucket_filter,
    stage_from_overdue_days,
)


class DelinquencyBucketTests(unittest.TestCase):
    def test_boundaries_with_balance(self):
        cases = [
            (0, "M1"),
            (35, "M1"),
            (36, "M2"),
            (63, "M2"),
            (64, "M3"),
            (91, "M3"),
            (92, "M3_PLUS"),
        ]
        for days, expected in cases:
            with self.subTest(days=days):
                self.assertEqual(calc_delinquency_bucket(days, 100.0), expected)

    def test_es_when_settled(self):
        self.assertEqual(calc_delinquency_bucket(100, 0.0), "ES")

    def test_overdue_asset_min_days(self):
        self.assertEqual(OVERDUE_ASSET_MIN_DAYS, 36)
        self.assertFalse(is_overdue_asset(35, 100.0))
        self.assertTrue(is_overdue_asset(36, 100.0))

    def test_stage_skips_zero(self):
        self.assertIsNone(stage_from_overdue_days(0))
        self.assertEqual(stage_from_overdue_days(1), "M1")
        self.assertEqual(stage_from_overdue_days(35), "M1")
        self.assertEqual(stage_from_overdue_days(36), "M2")

    def test_constants(self):
        self.assertEqual(M1_MAX_DAYS, 35)
        self.assertEqual(M2_MAX_DAYS, 63)
        self.assertEqual(M3_MAX_DAYS, 91)
        self.assertEqual(M3_PLUS_MIN_DAYS, 92)

    def test_matches_delinquency_bucket_filter(self):
        self.assertTrue(matches_delinquency_bucket_filter("M2", "M2_PLUS"))
        self.assertTrue(matches_delinquency_bucket_filter("M3", "M2_PLUS"))
        self.assertTrue(matches_delinquency_bucket_filter("M3_PLUS", "M2_PLUS"))
        self.assertFalse(matches_delinquency_bucket_filter("M1", "M2_PLUS"))
        self.assertFalse(matches_delinquency_bucket_filter("ES", "M2_PLUS"))
        self.assertTrue(matches_delinquency_bucket_filter("M2", "M2"))
        self.assertFalse(matches_delinquency_bucket_filter("M3", "M2"))


if __name__ == "__main__":
    unittest.main()

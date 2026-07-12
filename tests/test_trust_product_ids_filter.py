import unittest

from app import query_utils


class ParseTrustProductIdsTests(unittest.TestCase):
    def test_empty_means_all(self):
        self.assertIsNone(query_utils.parse_trust_product_ids(None, None))
        self.assertIsNone(query_utils.parse_trust_product_ids("", []))

    def test_single_legacy_param(self):
        self.assertEqual(query_utils.parse_trust_product_ids("4", None), [4])

    def test_repeated_params(self):
        self.assertEqual(
            query_utils.parse_trust_product_ids(None, ["3", "4", "3"]),
            [3, 4],
        )

    def test_merge_legacy_and_repeated(self):
        self.assertEqual(
            query_utils.parse_trust_product_ids("2", ["3", "4"]),
            [3, 4, 2],
        )


class SqlInIntColumnTests(unittest.TestCase):
    def test_none_returns_empty(self):
        sql, params = query_utils.sql_in_int_column("trust_product_id", None)
        self.assertEqual(sql, "")
        self.assertEqual(params, {})

    def test_single_id_uses_equality(self):
        sql, params = query_utils.sql_in_int_column("trust_product_id", [4], param_prefix="tp")
        self.assertIn("= :tp_0", sql)
        self.assertEqual(params, {"tp_0": 4})

    def test_multiple_ids_use_in(self):
        sql, params = query_utils.sql_in_int_column("trust_product_id", [3, 4], param_prefix="tp")
        self.assertIn("IN", sql)
        self.assertEqual(params, {"tp_0": 3, "tp_1": 4})


if __name__ == "__main__":
    unittest.main()

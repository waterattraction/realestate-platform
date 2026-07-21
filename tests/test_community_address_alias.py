"""community_name 列别名含「小区地址」。"""

from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import assetinfo_cleanse as cleanse
from app.assetinfo_upload import _parse_repayment_plan_rows


class CommunityAddressAliasTests(unittest.TestCase):
    def test_pick_community_address_alias(self):
        df = pd.DataFrame({"小区地址": ["番南小区"], "城市": ["上海"]})
        self.assertEqual(cleanse.pick_aliased_column(df, "community_name"), "小区地址")

    def test_parse_plan_maps_community_address(self):
        df = pd.DataFrame(
            {
                "资产编号(房源)": ["107112633046-001"],
                "托管房源编码": ["107112633046"],
                "统计日期": ["2026-07-17"],
                "初始受让金额": [100],
                "已还款金额": [10],
                "剩余还款金额": [90],
                "小区地址": ["北京市丰台区某小区"],
                "城市": ["北京"],
            }
        )
        rows, errors = _parse_repayment_plan_rows(df)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["community_name"], "北京市丰台区某小区")


if __name__ == "__main__":
    unittest.main()

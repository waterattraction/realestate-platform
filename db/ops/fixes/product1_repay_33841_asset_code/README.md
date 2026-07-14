# Ops：美好生活1号 · 还款 id=33841 · 资产主编号对齐

| 元数据 | 值 |
|--------|-----|
| **repair_name** | `product1_repay_33841_asset_code` |
| **风险等级** | **P3** |
| **状态** | **已完成并验收通过**（2026-07-14） |
| **规范** | [`docs/engineering/production_data_repair_standard.md`](../../../docs/engineering/production_data_repair_standard.md) |

## 概述

| 项 | 值 |
|----|-----|
| 产品 | 美好生活1号 (`trust_product_id = 1`) |
| 行 | `trust_repayment_detail_records.id = 33841` |
| 文件 | `美好生活1号-还款明细披露信息_20260710.xlsx` / `0710已还款` |
| 修正字段 | `asset_code` → `trust_assets.asset_code`（`101130798182`） |
| 不改 | `trust_asset_id`、`custody_asset_code`、`source_asset_code`、金额、日期、来源、导入逻辑 |

## 执行顺序

```bash
REPAIR=db/ops/fixes/product1_repay_33841_asset_code

docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py check
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py dry-run
# 人工审阅后
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py apply
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py verify
```

或 SQL：[`repair.sql`](./repair.sql) / [`rollback.sql`](./rollback.sql)。

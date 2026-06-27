# Ops：美好生活3号 · 0612已还款 · 托管编码归属修正

| 元数据 | 值 |
|--------|-----|
| **repair_name** | `product3_repay_0612_custody` |
| **风险等级** | **P2** |
| **状态** | **已完成并验收通过** |
| **规范** | [`docs/engineering/production_data_repair_standard.md`](../../../docs/engineering/production_data_repair_standard.md) |

> 完整验收记录见 [`ACCEPTANCE.md`](./ACCEPTANCE.md)。备份表与日志表**暂时保留，勿删除**。

## 概述

| 项 | 值 |
|----|-----|
| 产品 | 美好生活3号 (`trust_product_id = 3`) |
| 文件 | `美好生活3号-还款明细披露信息_20260612.xlsx` |
| Sheet | `0612已还款` |
| 错挂行数 | **71**（`custody_asset_code` ≠ `source_asset_code`） |
| 修正字段 | `custody_asset_code`、`trust_asset_id`（`asset_code` 幂等同步） |
| 不改 | 金额、期次、还款日期、源文件、Sheet、`synced_at`、`created_at`、`source_asset_code` |

## 执行顺序

```bash
REPAIR=db/ops/fixes/product3_repay_0612_custody

# 1. 只读检查 + 基线
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py check

# 2. Dry Run（产物 → /data/uploads/ops/product3_repay_0612_custody/）
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py dry-run

# 3. 人工审阅 dry-run CSV / JSON

# 4. Apply（事务 + 行数断言 71）
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py apply

# 5. Verify
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py verify
```

兼容入口：`scripts/ops/fix_product3_repay_0612_custody.py`（shim → 本目录 `repair.py`）。

或使用 SQL：[`repair.sql`](./repair.sql)（默认末尾 `ROLLBACK`）。

## 回滚

```bash
docker compose exec -T backend python3 /data/repo/db/ops/fixes/product3_repay_0612_custody/repair.py rollback
```

或 [`rollback.sql`](./rollback.sql)。

## 审计

| 资源 | 说明 |
|------|------|
| `_ops_p3_repay_0612_custody_fix_backup` | 历史备份表（规范前命名，**71 行，保留**） |
| `_ops_p3_repay_0612_custody_fix_log` | 历史日志表（**1 条，保留**） |
| `repair_log` | 新 Repair 统一表；本案例 verify 可双写（见 `repair.py`） |

## asset_code 全局结论

依据 `docs/standards/identifiers.md`：**不修改** `trust_assets.asset_code`；还款表 `asset_code` 仅幂等归一化。

## 防复发

- `backend/app/assetinfo_upload.py` — 权威字段、预检 ERROR、`upsert` 顺序
- `tests/test_assetinfo_asset_codes.py` — 19 项单元测试

# Ops：美好生活3号 · 0612已还款 · 托管编码归属修正

> **任务状态：已完成并验收通过。** 完整验收记录见 [`ACCEPTANCE_product3_repay_0612_custody.md`](./ACCEPTANCE_product3_repay_0612_custody.md)。备份表与日志表**暂时保留，勿删除**。

## 概述

| 项 | 值 |
|----|-----|
| 类型 | `ops/fix` |
| 产品 | 美好生活3号 (`trust_product_id = 3`) |
| 文件 | `美好生活3号-还款明细披露信息_20260612.xlsx` |
| Sheet | `0612已还款` |
| 错挂行数 | **71**（`custody_asset_code` ≠ `source_asset_code`） |
| 修正字段 | `custody_asset_code`、`trust_asset_id`（`asset_code` 已与 source 一致，幂等同步） |
| 不改 | 金额、期次、还款日期、源文件、Sheet、`synced_at`、`created_at`、`source_asset_code` |

## 执行顺序

```bash
# 1. 只读检查 + 基线
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py check

# 2. Dry Run（输出 71 行修正前后对照，不写库；产物在 /data/uploads/ops/product3_repay_0612/）
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py dry-run

# 3. 人工审阅 dry-run CSV / JSON

# 4. 执行修复（事务 + 行数断言 71 + 自动验收，失败则 ROLLBACK）
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py apply

# 5. 修正后复验（可重复执行）
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py verify
```

或使用 SQL：`./db/apply.sh ops fixes/20250624_fix_product3_repay_0612_custody.sql`（需先去掉末尾 ROLLBACK 并人工 COMMIT）。

## 回滚

```bash
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py rollback
```

## 审计表

- `_ops_p3_repay_0612_custody_fix_backup` — 修正前 71 行快照
- `_ops_p3_repay_0612_custody_fix_log` — 执行元数据（时间、操作人、updated_count）

## asset_code 修改结论（全局）

依据 `docs/standards/identifiers.md`：**`asset_code` 为历史兼容字段，新逻辑禁止扩散修改**。

| 位置 | 本次是否修改 | 说明 |
|------|:------------:|------|
| `trust_assets.asset_code` | **否** | `UNIQUE(trust_product_id, asset_code)`；FK 锚点为 `trust_asset_id` |
| `trust_repayment_detail_records.asset_code` | 幂等同步 | 仅归一化为 `source_asset_code`（71 行已一致） |
| `trust_asset_monitor_records.asset_code` | **否** | 不在本修复范围 |
| `trust_overdue_*` / 风险 / 标记 | **否** | 经 `trust_asset_id` 关联，不读还款表 `asset_code` |
| 发行 `custody_asset_code` | **否** | 独立业务链 |

**`trust_assets` 唯一性预检**（apply 前强制）：同一 `trust_product_id` 下 `source_asset_code` 不得对应多个 `id`；`check` / `apply` 均断言 duplicate groups = 0。

## 导入防复发（代码）

- `_resolve_asset_fields`：`资产编号(房源)` 为权威，三码对齐
- `_excel_custody_source_mismatch_rows` + 预检 `[ERROR]` → `needs_confirm`
- `_upsert_trust_asset`：查找顺序 `source_asset_code` → `asset_code` → `custody`（仅当 custody==source）
- 单元测试：`tests/test_ingestion_asset_codes.py`

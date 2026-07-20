# 资产置换（`asset_swap_*`）

置换推荐只读；确认置换后**仅写入本域新表**，不修改 `trust_asset_monitor_records` 与 `trust_product_issuance_asset_records`。

## 表

| 表 | 用途 |
|----|------|
| `asset_swap_orders` | 置换单头：业务日、方案、状态、执行人 |
| `asset_swap_assets` | 互换资产行：`out`（美好→美润）/ `in`（美润→美好） |
| `asset_swap_monitor_snapshots` | 每资产 `exit` + `entry` 监控副本 |


Migration：`db/migrations/20260720_asset_swap_orders.sql`

## 规则

| 项 | 说明 |
|----|------|
| 查询推荐 | 只读，不写库 |
| 流程 | 选用方案 → **预览** → **确认置换** |
| 置换业务日 | 人工选择，默认当日（`swap_business_date`） |
| 监控快照 | exit 拷贝转出时监控；entry 归属改为转入产品，且初始受让=exit 剩余还款、已还款=0、剩余=初始−已还 |
| 失效 | 可将 `completed` 标为 `voided`；若 `executed_at` 之后相关产品有 `assetinfo_pipeline_runs.inserted_monitor_count > 0`，不可失效 |

## 页面

- `/asset-swap`
- 主页 §3「资产置换」

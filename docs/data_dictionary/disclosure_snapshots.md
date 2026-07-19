# 数据披露快照

披露页将模版列结果冻结为不可变副本，与导入事实表分离。

## 表

| 表 | 用途 |
|----|------|
| `disclosure_snapshots` | 快照头：`repayment` / `monitor`、`as_of_date`、`frozen_at`、`product_ids[]`、行数、备注 |
| `disclosure_repayment_rows` | 还款明细模版列物化（含冻结时的 `overdue_days`） |
| `disclosure_repayment_plan_rows` | 回款计划模版列物化 |
| `disclosure_monitor_rows` | 资产监控模版列物化 |

Migration：`db/migrations/20260720_disclosure_snapshots.sql`

## 业务规则

| 项 | 规则 |
|----|------|
| 还款时点 UI | **披露截止日** |
| 还款裁切 | 明细 `repayment_date ≤ as_of`；计划按产品取 `data_date ≤ as_of` 最新批次；逾期取监控 `data_date ≤ as_of` 最新 |
| 监控时点 UI | **统计日期** = `trust_asset_monitor_records.data_date` |
| 产品 | 可多选；冻结须至少选一个 |
| 多次冻结 | 同产品同时点允许；以 `frozen_at` 区分 |
| 删除 | 物理删除 + 确认；`frozen_at` 满 30 天不可删 |

## 页面入口

- `/disclosure/repayment` — 还款明细披露
- `/disclosure/monitor` — 资产监控披露
- 主页 §5「数据披露」

列契约 SSOT：`backend/app/assetinfo_templates.py`

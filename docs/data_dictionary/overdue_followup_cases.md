# 逾期跟进事项（`trust_overdue_followup_cases`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 逾期跟进事项 |
| 表英文名 | `trust_overdue_followup_cases` |
| Schema 来源 | `db/migrations/20260623_overdue_followup_cases_entries.sql` |
| 主键 | `id` |
| 业务主体 | `(trust_product_id, asset_code)`；同一资产主编号可有多条事项 |

## 表用途

资产主编号维度的**跟进事项**。分类/状态/描述由事项本身维护；具体跟进行为在 `trust_overdue_followup_entries`。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 开案 | `POST /overdue/workbench/followups/cases` |
| 跟进中 | `status` = `open`（展示「待跟进」）/ `in_progress` |
| 结案 | 人工将状态改为 `resolved` / `closed`（保存 entry **不**自动改状态） |
| 约束 | 允许同一资产多条活跃事项 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 事项 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 系统 | FK | |
| asset_code | 资产主编号 | VARCHAR(128) | 是 | 运营入口 | 事项主体 | |
| custody_asset_code | 托管房源号 | VARCHAR(128) | 否 | 系统 | 冗余 | |
| data_date | 开案快照日 | DATE | 是 | 监控 | 开案时 `data_date` | |
| category | 事项分类 | VARCHAR(64) | 是 | 人工 | 字典五值 | 轻度逾期/重度逾期/回购/置换/潜在风险 |
| description | 事项描述 | TEXT | 否 | 人工 | | |
| status | 事项状态 | VARCHAR(32) | 是 | 人工 | open/in_progress/resolved/closed | 默认 open |
| owner_name | 当前负责人 | VARCHAR(100) | 否 | entry | 最新跟进人 | |
| opened_at | 开案时间 | TIMESTAMPTZ | 是 | 系统 | | |
| closed_at | 结案时间 | TIMESTAMPTZ | 否 | 状态变更 | resolved/closed 时写入 | |
| last_follow_up_at | 最近跟进 | TIMESTAMPTZ | 否 | entry | | |
| created_by | 创建人 | VARCHAR(64) | 否 | 系统 | | |
| updated_by | 更新人 | VARCHAR(64) | 否 | 系统 | | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | UI 展示 YYYYMMDDHHMM | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_followup_cases_product_asset` | `trust_product_id, asset_code` | 查询 |

## 下游使用模块

- `OverdueWorkbenchService` — 事项条 + 派生 `internal_status`
- `/overdue` / 资产组合管理 — 活跃事项计数

## 注意事项

- 事项状态仅能通过 case API 人工变更；entry 保存不改状态。
- 活跃事项数 N>0 → `internal_status=待跟进(N)`；否则 `正常`。
- 与 `trust_risk_cases` 分域，无 FK。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06-23 | 初版 | `20260623_overdue_followup_cases_entries.sql` |
| 2026-07-14 | 多事项 + category/description；取消唯一活跃约束 | `20260714_followup_cases_multi_and_entry_slim.sql` |

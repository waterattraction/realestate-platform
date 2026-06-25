# 逾期跟进案件（`trust_overdue_followup_cases`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 逾期跟进案件 |
| 表英文名 | `trust_overdue_followup_cases` |
| Schema 来源 | `db/migrations/20260623_overdue_followup_cases_entries.sql` |
| 主键 | `id` |
| 业务主体 | `(trust_product_id, custody_asset_code)` 托管维度 |

## 表用途

托管房源维度的**逾期案件状态缓存**。每次运营保存跟进时更新；真实跟进行为记录在 `trust_overdue_followup_entries`。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 开案 | 首次 `POST /overdue/workbench/followups/entries` 自动 INSERT |
| 跟进中 | `status` = `open` / `in_progress` |
| 结案 | entry 写入 `resolved` / `closed` 时更新 `closed_at` |
| 约束 | 每托管仅一条活跃案件（`open`/`in_progress`） |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 案件 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 系统 | FK | |
| custody_asset_code | 托管房源号 | VARCHAR(128) | 是 | 运营入口 | 案件主体 | |
| data_date | 开案快照日 | DATE | 是 | 监控 | 开案时 `data_date` | |
| status | 案件状态 | VARCHAR(32) | 是 | entry 副作用 | open/in_progress/resolved/closed | |
| owner_name | 当前负责人 | VARCHAR(100) | 否 | entry | 最新跟进人 | |
| opened_at | 开案时间 | TIMESTAMPTZ | 是 | 系统 | | |
| closed_at | 结案时间 | TIMESTAMPTZ | 否 | entry | resolved/closed 时写入 | |
| last_follow_up_at | 最近跟进 | TIMESTAMPTZ | 否 | entry | | |
| created_by | 创建人 | VARCHAR(64) | 否 | 系统 | | |
| updated_by | 更新人 | VARCHAR(64) | 否 | 系统 | | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_followup_cases_active_custody` | `(trust_product_id, custody_asset_code)` WHERE active | 唯一活跃案件 |
| `idx_followup_cases_product_custody` | `trust_product_id, custody_asset_code` | 查询 |

## 下游使用模块

- `OverdueWorkbenchService.get_detail()` — 案件摘要
- `/overdue` 列表 — `has_followup`（活跃案件 EXISTS）

## 注意事项

- **禁止**独立 PATCH 改 `status`；唯一写入路径为 followup entry。
- 与 `trust_asset_trust_marks.internal_status`（队列状态）字段分离。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06-23 | 初版 | `20260623_overdue_followup_cases_entries.sql` |

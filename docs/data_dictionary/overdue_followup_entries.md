# 逾期跟进记录（`trust_overdue_followup_entries`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 逾期跟进记录 |
| 表英文名 | `trust_overdue_followup_entries` |
| Schema 来源 | `db/migrations/20260623_overdue_followup_cases_entries.sql` |
| 主键 | `id` |
| 业务语义 | 事项下的跟进事实（可编辑/删除，受事项是否活跃约束） |

## 表用途

运营在某一跟进事项下录入的记录；构成工作台时间线事实源。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | `POST /overdue/workbench/followups/entries`（须带 `case_id`） |
| 更新 | `POST .../entries/{id}`（事项为 open/in_progress 时） |
| 删除 | `POST .../entries/{id}/delete` |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| case_id | 事项 ID | BIGINT | 是 | 系统 | FK → cases | |
| entry_type | 记录类型 | VARCHAR(32) | 是 | 系统/人工 | manual/system/trust_request | |
| overdue_reason | 原因说明 | TEXT | 否 | 人工 | | |
| follow_up_plan | 跟进方案 | TEXT | 否 | 人工 | | |
| owner_name | 跟进人 | VARCHAR(100) | 否 | 人工 | | |
| created_by | 创建人 | VARCHAR(64) | 否 | 登录用户 | | |
| created_at | 跟进时间 | TIMESTAMPTZ | 是 | 系统 | 时间线排序键 | |
| updated_by | 更新人 | VARCHAR(64) | 否 | 登录用户 | | |
| updated_at | 更新时间 | TIMESTAMPTZ | 否 | 系统 | | |

> 已删除列（2026-07-14）：`status_snapshot`、`trust_feedback`、`note`。

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_followup_entries_case_created` | `case_id, created_at DESC` | 时间线 |

## 下游使用模块

- 工作台时间线 / 跟进录入面板
- `/overdue` — `followup_count`

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06-23 | 初版 | `20260623_overdue_followup_cases_entries.sql` |
| 2026-07-14 | 去掉 status_snapshot / trust_feedback / note | `20260714_followup_cases_multi_and_entry_slim.sql` |

# 逾期跟进记录（`trust_overdue_followup_entries`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 逾期跟进记录 |
| 表英文名 | `trust_overdue_followup_entries` |
| Schema 来源 | `db/migrations/20260623_overdue_followup_cases_entries.sql` |
| 主键 | `id` |
| 业务语义 | **只追加**的行为事实（event log） |

## 表用途

每次运营点击「保存本次跟进」INSERT 一条记录，构成时间线事实源。`/overdue` 列表 `followup_count` = 本表 COUNT。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | `POST /overdue/workbench/followups/entries` |
| 更新 | **禁止**（V2.2 仅追加） |
| 删除 | 仅 admin（TODO） |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| case_id | 案件 ID | BIGINT | 是 | 系统 | FK → cases | |
| entry_type | 记录类型 | VARCHAR(32) | 是 | 系统/人工 | manual/system/trust_request | |
| status_snapshot | 录入时案件状态 | VARCHAR(32) | 否 | 表单 | | |
| overdue_reason | 逾期原因 | TEXT | 否 | 人工 | | |
| follow_up_plan | 跟进方案 | TEXT | 否 | 人工 | | |
| trust_feedback | 信托反馈口径 | TEXT | 否 | 人工 | | |
| note | 补充说明 | TEXT | 否 | 人工 | | |
| owner_name | 跟进人 | VARCHAR(100) | 否 | 人工 | | |
| created_by | 创建人 | VARCHAR(64) | 否 | 登录用户 | | |
| created_at | 跟进时间 | TIMESTAMPTZ | 是 | 系统 | 时间线排序键 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_followup_entries_case_created` | `case_id, created_at DESC` | 时间线 |

## 下游使用模块

- 工作台时间线（`get_detail().timeline`）
- `/overdue` — `followup_count`

## 注意事项

- `entry_type=system` 仅用于 escalate 等系统记录（可选）。
- 旧表 `trust_overdue_followups` 记录在时间线标「历史台账」只读展示。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06-23 | 初版 | `20260623_overdue_followup_cases_entries.sql` |

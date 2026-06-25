# 逾期跟进台账（`trust_overdue_followups`）— 遗留

> **状态：遗留只读。** V2.2 起运营跟进写入 `trust_overdue_followup_cases` + `trust_overdue_followup_entries`。本表由 `risk_hub` 等历史路径只读引用；新功能禁止写入。

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 逾期跟进台账 |
| 表英文名 | `trust_overdue_followups` |
| Schema 来源 | `db/modules/overdue/schema.sql` + `db/modules/risk/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | TODO：按 `(trust_product_id, trust_asset_id, data_date)` 或案件维度 |

## 表用途

记录逾期资产的跟进状态、计划与反馈。风险 V2 扩展后兼作「风险案件（Case）」逻辑载体（无独立 `risk_cases` 表）。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 系统触发 / 人工创建 / 页面维护 |
| 更新 | 跟进状态、SLA、风险分等 |
| 冻结 | 案件关闭后 |
| 删除/归档 | TODO |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 系统 | 产品维度 | FK |
| trust_asset_id | 底层资产 ID | BIGINT | 是 | 系统 | 资产维度 | FK |
| data_date | 快照日期 | DATE | 是 | 系统 | 跟进所依快照日 | |
| trigger_source | 触发来源 | VARCHAR(32) | 是 | 系统 | 默认 `system` | |
| overdue_reason | 逾期原因 | TEXT | 否 | 人工/系统 | | |
| follow_up_plan | 跟进计划 | TEXT | 否 | 人工 | | |
| status | 状态 | VARCHAR(32) | 是 | 人工/系统 | 如 `open` | |
| owner_name | 负责人 | VARCHAR(100) | 否 | 人工 | | |
| last_follow_up_at | 最近跟进时间 | TIMESTAMPTZ | 否 | 人工 | | |
| trust_feedback | 信托反馈 | TEXT | 否 | 人工 | | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | | |
| risk_score | 风险评分 | INT | 否 | 风险 | Case 扩展 | risk_v2 |
| risk_level | 风险等级 | VARCHAR(2) | 否 | 风险 | Case 扩展 | |
| sla_due_date | SLA 截止 | TIMESTAMPTZ | 否 | 风险 | | |
| sla_status | SLA 状态 | VARCHAR(32) | 否 | 风险 | | |
| alert_source | 预警来源 | VARCHAR(32) | 否 | 风险 | 默认 `system` | |
| case_priority | 案件优先级 | VARCHAR(8) | 否 | 风险 | | |
| next_action_date | 下次行动日 | DATE | 否 | 风险 | | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_trust_overdue_followups_status` | `status` | 按状态 |
| `idx_trust_overdue_followups_product_asset` | `trust_product_id, trust_asset_id` | 按产品+资产 |
| `idx_trust_overdue_followups_sla_status` | `sla_status` | SLA 筛选 |

## 上游来源

- **无独立 Excel 导入模板**（见 `docs/excel/overdue.md`）
- 系统根据监控/逾期规则生成 + 页面人工维护

## 下游使用模块

逾期管理（`/overdue`）、风险案件视图、Dashboard

## 数据质量规则

- TODO：状态枚举、必填跟进字段

## 注意事项

- 当前**无独立逾期 Excel 导入**；本表主要由系统与页面维护。
- 风险「案件」语义映射到本表扩展列，非物理 `risk_cases` 表。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/overdue/schema.sql` |
| — | 风险扩展 | `db/modules/risk/schema.sql` |

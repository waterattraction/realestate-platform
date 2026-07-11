# 风险案件（`trust_risk_cases`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 风险案件 |
| 表英文名 | `trust_risk_cases` |
| Schema 来源 | `db/modules/risk/schema.sql` + `db/migrations/20260712_trust_risk_cases.sql` |
| 主键 | `id` |
| 业务主体 | `(trust_product_id, trust_asset_id)` 分笔维度 |

## 表用途

分笔维度的风险案件状态与 SLA 载体，由 `risk_hub` 自动开案/更新及 `/risk/cases` 人工维护。与运营跟进 `trust_overdue_followup_cases` 分域，无 FK。

## 字段清单

| Field | 中文名 | 类型 | 必填 | 说明 |
|-------|--------|------|:----:|------|
| id | 案件 ID | BIGINT | 是 | 主键 |
| trust_product_id | 信托产品 ID | BIGINT | 是 | FK |
| trust_asset_id | 底层资产 ID | BIGINT | 是 | FK，分笔 |
| data_date | 快照日期 | DATE | 是 | 开案监控快照日 |
| trigger_source | 触发来源 | VARCHAR(32) | 是 | system / trust / manual |
| alert_source | 预警来源 | VARCHAR(32) | 否 | |
| status | 状态 | VARCHAR(32) | 是 | open / in_progress / resolved / closed |
| owner_name | 负责人 | VARCHAR(100) | 否 | |
| overdue_reason | 原因 | TEXT | 否 | |
| follow_up_plan | 处置计划 | TEXT | 否 | |
| trust_feedback | 信托反馈 | TEXT | 否 | |
| last_follow_up_at | 最近跟进 | TIMESTAMPTZ | 否 | |
| risk_score | 风险评分 | INT | 否 | |
| risk_level | 风险等级 | VARCHAR(2) | 否 | A/B/C/D |
| sla_due_date | SLA 截止 | TIMESTAMPTZ | 否 | |
| sla_status | SLA 状态 | VARCHAR(32) | 否 | on_time / overdue / breached |
| case_priority | 优先级 | VARCHAR(8) | 否 | P0–P3 |
| next_action_date | 下次行动日 | DATE | 否 | |
| created_at / updated_at | 审计 | TIMESTAMPTZ | 是 | |

## 索引

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_trust_risk_cases_product_status` | `trust_product_id, status` | 产品筛选 |
| `idx_trust_risk_cases_asset_status` | `trust_asset_id, status` | 分笔筛选 |
| `idx_trust_risk_cases_sla` | `sla_status` (active) | SLA 违约计数 |
| `idx_trust_risk_cases_asset_date` | `trust_asset_id, data_date DESC` | 历史 |

## 约束说明

- **无**「每分笔唯一活跃案件」约束；同一 `trust_asset_id` 可有多条 `open` / `in_progress`。
- 风险重算 `sync_risk_cases` 更新**最新一条**活跃案件，否则 INSERT。

## 下游

- `risk_hub.py` — 读写主路径
- `GET/POST/PATCH /risk/cases`、`/risk/workbench`

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-07-12 | 从 `trust_overdue_followups` 拆出独立表 | `20260712_trust_risk_cases.sql` |

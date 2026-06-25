# 风险（`risk_alerts` 及扩展列）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 风险预警 / 风险扩展 |
| 表英文名 | `risk_alerts`；扩展列在 `trust_asset_monitor_records`、`trust_overdue_followups` |
| Schema 来源 | `db/modules/risk/schema.sql` |
| 主键 | `risk_alerts.id` |
| 业务唯一标识 | 开放预警：`uq_risk_alerts_open_rule (trust_asset_id, data_date, risk_type)` WHERE open |

## 表用途

- **`risk_alerts`**：系统生成的风险预警记录
- **扩展列**：监控表上的 `risk_score`/`risk_level`；跟进表上的 Case/SLA 字段

> 平台**无**独立 `risk_cases`、`risk_scores` 物理表；Canonical「RiskCase」为逻辑对象。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 规则引擎 / 系统批处理 |
| 更新 | 确认、解决、升级 |
| 冻结 | `status` 非 open |
| 删除/归档 | TODO |

## 字段清单 — `risk_alerts`

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 预警 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 系统 | | FK |
| trust_asset_id | 底层资产 ID | BIGINT | 是 | 系统 | | FK |
| data_date | 快照日期 | DATE | 是 | 系统 | 风险所依快照日 | |
| risk_type | 风险类型 | VARCHAR(64) | 是 | 规则 | 分类 | |
| risk_level | 风险等级 | VARCHAR(2) | 是 | 规则 | 如高/中/低编码 | |
| trigger_rule | 触发规则 | VARCHAR(200) | 是 | 规则 | 规则标识 | |
| status | 状态 | VARCHAR(32) | 是 | 系统/人工 | `open`/`acknowledged`/… | |
| generated_at | 生成时间 | TIMESTAMPTZ | 是 | 系统 | | |
| resolved_at | 解决时间 | TIMESTAMPTZ | 否 | 人工 | | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | | |

## 扩展列（另见 monitor / overdue 字典）

| 表 | 字段 | 用途 |
|----|------|------|
| `trust_asset_monitor_records` | `risk_score`, `risk_level` | 资产级风险分 |
| `trust_overdue_followups` | `risk_score`, `risk_level`, `sla_*`, `case_priority` | 案件级风险 |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_risk_alerts_status` | `status` | 按状态 |
| `idx_risk_alerts_asset` | `trust_asset_id, data_date` | 按资产 |
| `uq_risk_alerts_open_rule` | 部分唯一 | 同规则未关闭预警唯一 |

## 上游来源

- 监控快照、逾期状态、规则配置（`db/modules/risk/seed.sql` TODO 细读）

## 下游使用模块

风险管理 Dashboard、逾期联动、TODO：告警通知

## 数据质量规则

- 开放状态同 `(asset, data_date, risk_type)` 唯一

## 注意事项

- 查「风险案件」时查 `trust_overdue_followups` 扩展列，非独立表。
- `data_date` 与监控快照对齐。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/risk/schema.sql` |

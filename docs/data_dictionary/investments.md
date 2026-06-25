# 投资记录（`investments`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 投资记录 |
| 表英文名 | `investments` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `subscription_no` UNIQUE |

## 表用途

投资人认购信托产品的记录，关联 `investors` 与 `trust_products`。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 认购录入 |
| 更新 | `status`、`invested_at` |
| 冻结 | TODO |
| 删除/归档 | 一般保留审计 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 投资记录 ID | BIGINT | 是 | 系统 | 主键 | |
| investor_id | 投资人 ID | BIGINT | 是 | 系统 | FK → investors | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 系统 | FK → trust_products | |
| subscription_no | 认购编号 | VARCHAR(32) | 是 | 系统 | 业务唯一号 | UNIQUE |
| amount | 认购金额 | NUMERIC(18,2) | 是 | 系统 | 金额 | > 0 |
| status | 状态 | VARCHAR(32) | 是 | 系统 | pending 等 | |
| invested_at | 投资时间 | TIMESTAMPTZ | 否 | 系统 | 实际投资日 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_investments_subscription_no` | `subscription_no` | UNIQUE |
| `idx_investments_investor_id` | `investor_id` | 反查 |
| `idx_investments_trust_product_id` | `trust_product_id` | 反查 |
| `idx_investments_status` | `status` | 筛选 |

## 上游来源

- 种子 / 管理录入

## 下游使用模块

- Dashboard `GET /investments`、产品募集进度（TODO）

## 注意事项

- 与底层资产发行/监控链路独立。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/baseline/001_schema.sql` |

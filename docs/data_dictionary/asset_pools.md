# 资产包（`asset_pools`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 资产包 |
| 表英文名 | `asset_pools` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `code` UNIQUE |

## 表用途

证券化资产包主数据；通过 `trust_products.asset_pool_id` 关联信托产品。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 种子 / 管理录入 |
| 更新 | `status`、`appraised_value` 等 |
| 冻结 | TODO |
| 删除/归档 | 有信托产品 FK 时禁止物理删除 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 资产包 ID | BIGINT | 是 | 系统 | 主键 | IDENTITY |
| code | 资产包编码 | VARCHAR(32) | 是 | 系统 | 业务唯一编码 | UNIQUE |
| name | 资产包名称 | VARCHAR(200) | 是 | 系统 | 展示 | |
| status | 状态 | VARCHAR(32) | 是 | 系统 | pending / active | 默认 pending |
| appraised_value | 评估价值 | NUMERIC(18,2) | 是 | 系统 | 资产规模 | ≥ 0 |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | trigger |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_asset_pools_code` | `code` | UNIQUE |
| `idx_asset_pools_status` | `status` | 筛选 |

## 上游来源

- `db/baseline/002_seed.sql` 种子数据

## 下游使用模块

- `trust_products`（FK）
- Dashboard 基础实体 API

## 注意事项

- 与 Excel 导入无直接关系；业务链为 Project → AssetPool → TrustProduct。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/baseline/001_schema.sql` |

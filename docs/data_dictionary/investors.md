# 投资人（`investors`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 投资人 |
| 表英文名 | `investors` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `code` UNIQUE |

## 表用途

投资人主数据；通过 `investments` 关联信托产品认购记录。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 种子 / KYC 录入 |
| 更新 | 联系方式、KYC 状态 |
| 冻结 | TODO |
| 删除/归档 | 有投资记录时禁止删 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 投资人 ID | BIGINT | 是 | 系统 | 主键 | |
| code | 投资人编码 | VARCHAR(32) | 是 | 系统 | 唯一编码 | UNIQUE |
| name | 投资人名称 | VARCHAR(200) | 是 | 系统 | 展示 | |
| investor_type | 投资人类型 | VARCHAR(32) | 是 | 系统 | individual 等 | 默认 individual |
| kyc_status | KYC 状态 | VARCHAR(32) | 是 | 系统 | pending 等 | |
| phone | 电话 | VARCHAR(20) | 否 | 系统 | 联系 | |
| email | 邮箱 | VARCHAR(200) | 否 | 系统 | 联系 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_investors_code` | `code` | UNIQUE |
| `idx_investors_type` | `investor_type` | 筛选 |
| `idx_investors_kyc_status` | `kyc_status` | 筛选 |

## 上游来源

- `db/baseline/002_seed.sql`

## 下游使用模块

- `investments`；Dashboard `GET /investors`

## 注意事项

- 与发行/监控 Excel 导入无直接关系。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/baseline/001_schema.sql` |

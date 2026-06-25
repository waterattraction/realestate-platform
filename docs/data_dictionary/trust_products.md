# 信托产品（`trust_products`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 信托产品 |
| 表英文名 | `trust_products` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `code`（UNIQUE）；业务上亦用 `name` |

## 表用途

存储证券化信托产品主数据，关联资产包，作为发行、监控、还款、逾期、风险等模块的产品维度外键。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 种子数据 / 管理录入 / `db/modules/trust/seed_products.sql` |
| 更新 | 状态、募集金额等字段可更新 |
| 冻结 | TODO：产品结清后状态约定 |
| 删除/归档 | 无外键级联删除；有业务数据时禁止物理删除 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 产品 ID | BIGINT | 是 | 系统 | 主键、外键引用 | IDENTITY |
| asset_pool_id | 资产包 ID | BIGINT | 是 | 系统 | 关联 `asset_pools` | FK |
| code | 产品编码 | VARCHAR(32) | 是 | 系统 | 唯一业务编码 | UNIQUE |
| name | 产品名称 | VARCHAR(200) | 是 | 系统 | 展示、导入快照、别名解析目标 | 如「美好生活1号」 |
| status | 状态 | VARCHAR(32) | 是 | 系统 | 产品生命周期状态 | 默认 `draft` |
| target_amount | 目标规模 | NUMERIC(18,2) | 是 | 系统 | 募集目标 | > 0 |
| raised_amount | 已募集金额 | NUMERIC(18,2) | 是 | 系统 | 募集进度 | ≥ 0 |
| expected_return_rate | 预期收益率 | NUMERIC(8,4) | 否 | 系统 | 展示 | TODO |
| open_date | 开放日 | DATE | 否 | 系统 | 产品开放 | |
| close_date | 关闭日 | DATE | 否 | 系统 | 产品关闭 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | 触发器维护 |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_trust_products_code` | `code` | 唯一约束 |
| `idx_trust_products_asset_pool_id` | `asset_pool_id` | 按资产包查询 |
| `idx_trust_products_status` | `status` | 按状态筛选 |

## 上游来源

- `db/baseline/002_seed.sql`、`db/modules/trust/seed_products.sql`
- 管理端录入（如有）

## 下游使用模块

发行、监控、还款、逾期、风险、导入管道；`trust_product_aliases` 别名解析。

## 数据质量规则

- `code`、`name` 不可为空
- `target_amount` 必须 > 0

## 注意事项

- 导入模块常同时写入 `trust_product_id` 与 `trust_product_name` 快照
- 别名匹配见 `trust_product_aliases`（非本表字段）

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线表 | `db/baseline/001_schema.sql` |

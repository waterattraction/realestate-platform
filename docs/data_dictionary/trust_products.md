# 信托产品（`trust_products`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 信托产品 |
| 表英文名 | `trust_products` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `code`（UNIQUE）；`name` 业务唯一（应用层校验） |

## 表用途

存储证券化信托产品主数据，关联资产包，作为发行、监控、还款、逾期、风险等模块的产品维度外键。

## 管理端（V1 Lite）

| 页面 | 路径 |
|------|------|
| 列表 | `GET /trust-products/manage` |
| 新增 | `GET /trust-products/new` → `POST /trust-products` |
| 编辑 | `GET /trust-products/{id}/edit` → `PATCH /trust-products/{id}` |
| 单条 JSON | `GET /trust-products/{id}` |

保留只读目录 API：`GET /trust-products`（供下拉等，本轮未改契约）。

**不支持**：DELETE、`trust_product_aliases` 管理、自动维护 `assetinfo_date_rules.py`。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 管理端 `POST /trust-products`；`code`、`asset_pool_id` 创建后只读 |
| 更新 | `PATCH` 可改 `name`、`status`、`trust_end_date` |
| 删除/归档 | **不支持物理删除**；有业务数据时禁止删除 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 产品 ID | BIGINT | 是 | 系统 | 主键、外键引用 | IDENTITY |
| asset_pool_id | 资产包 ID | BIGINT | 是 | 系统 | 关联 `asset_pools` | FK；创建后只读 |
| code | 产品编码 | VARCHAR(32) | 是 | 系统 | 唯一业务编码 | UNIQUE；创建后只读 |
| name | 产品名称 | VARCHAR(200) | 是 | 系统 | 展示、导入快照 | 业务唯一 |
| status | 状态 | VARCHAR(32) | 是 | 系统 | 产品生命周期 | 写入仅 `issued` / `ended` |
| trust_end_date | 信托结束日期 | DATE | 否 | 系统 | 产品结束日 | V1 Lite 新增 |
| expected_return_rate | 预期收益率 | NUMERIC(8,4) | 否 | 系统 | 遗留列 | 管理端 V1 不维护 |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | 触发器维护 |

## status（V1 Lite）

| 写入值 | 中文 | 含义 |
|--------|------|------|
| `issued` | 已发行 | 产品有效 / 运行中 |
| `ended` | 结束 | 产品已结束 |

**读取兼容**（仅展示/API 归一化，未 PATCH 前库中可能仍为旧值）：

| 旧值 | 归一化为 | 中文 |
|------|----------|------|
| `draft` / `raising` / `active` / `issued` | `issued` | 已发行 |
| `completed` / `closed` / `ended` | `ended` | 结束 |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_trust_products_code` | `code` | 唯一约束 |
| `idx_trust_products_asset_pool_id` | `asset_pool_id` | 按资产包查询 |
| `idx_trust_products_status` | `status` | 按状态筛选 |

## 上游来源

- `db/baseline/002_seed.sql`、`db/modules/trust/seed_products.sql`
- 管理端 `POST /trust-products`

## 下游使用模块

发行、监控、还款、逾期、风险、导入管道；`trust_product_aliases` 别名解析（非本表字段）。

## 数据质量规则

- `code`、`name` 不可为空；`code` 全局唯一；`name` 全局唯一（应用校验）
- 新产品导入监控/还款前，须手动配置 `assetinfo_date_rules.py`

## 注意事项

- 导入模块常同时写入 `trust_product_id` 与 `trust_product_name` 快照
- 别名匹配见 `trust_product_aliases`（本轮不管理）

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线表 | `db/baseline/001_schema.sql` |
| 2026-07 | 信托结束日期 + V1 Lite 管理端 | `db/migrations/20260704_trust_products_trust_end_date.sql` |

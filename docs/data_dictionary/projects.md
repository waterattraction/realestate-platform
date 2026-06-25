# 项目（`projects`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 证券化项目 |
| 表英文名 | `projects` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `code` UNIQUE |

## 表用途

平台顶层项目实体；通过 `project_asset_pools` 与资产包多对多关联。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 种子 / 管理录入 |
| 更新 | 预算、日期、状态 |
| 冻结 | TODO |
| 删除/归档 | 有关联资产包时禁止物理删除 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 项目 ID | BIGINT | 是 | 系统 | 主键 | |
| code | 项目编码 | VARCHAR(32) | 是 | 系统 | 唯一编码 | UNIQUE |
| name | 项目名称 | VARCHAR(200) | 是 | 系统 | 展示 | |
| description | 描述 | TEXT | 否 | 系统 | 说明 | |
| status | 状态 | VARCHAR(32) | 是 | 系统 | draft / in_progress / completed | 默认 draft |
| address | 地址 | VARCHAR(500) | 否 | 系统 | 展示 | |
| city | 城市 | VARCHAR(100) | 否 | 系统 | 展示 | |
| total_budget | 总预算 | NUMERIC(18,2) | 是 | 系统 | 预算 | ≥ 0 |
| planned_start_date | 计划开始日 | DATE | 否 | 系统 | 计划 | |
| planned_end_date | 计划结束日 | DATE | 否 | 系统 | 计划 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_projects_code` | `code` | UNIQUE |
| `idx_projects_status` | `status` | 筛选 |
| `idx_projects_city` | `city` | 筛选 |

## 上游来源

- `db/baseline/002_seed.sql`

## 下游使用模块

- `project_asset_pools` → `asset_pools` → `trust_products`
- Dashboard `GET /projects`

## 注意事项

- 非信托业务链核心表；发行/监控不直接引用。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/baseline/001_schema.sql` |

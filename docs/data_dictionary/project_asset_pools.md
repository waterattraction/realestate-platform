# 项目-资产包关联（`project_asset_pools`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 项目资产包关联 |
| 表英文名 | `project_asset_pools` |
| Schema 来源 | `db/baseline/001_schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `(project_id, asset_pool_id)` UNIQUE |

## 表用途

Project 与 AssetPool 多对多关联表。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 关联建立 |
| 更新 | 一般不变 |
| 删除/归档 | 解除关联（TODO：业务规则） |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 关联 ID | BIGINT | 是 | 系统 | 主键 | |
| project_id | 项目 ID | BIGINT | 是 | 系统 | FK → projects | |
| asset_pool_id | 资产包 ID | BIGINT | 是 | 系统 | FK → asset_pools | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_project_asset_pools` | `project_id`, `asset_pool_id` | 防重复 |
| `idx_project_asset_pools_project_id` | `project_id` | 反查 |
| `idx_project_asset_pools_asset_pool_id` | `asset_pool_id` | 反查 |

## 上游来源

- 种子 / 管理维护

## 下游使用模块

- 项目概览、资产包聚合视图

## 注意事项

- 纯关联表，无业务指标字段。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/baseline/001_schema.sql` |

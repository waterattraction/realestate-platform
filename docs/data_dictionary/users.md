# 用户（`users`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 系统用户 |
| 表英文名 | `users` |
| Schema 来源 | `db/modules/users/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `username` UNIQUE |

## 表用途

平台登录与操作审计。导入运行记录（`assetinfo_pipeline_runs`、`issuance_import_runs`）通过 `created_by` 关联本表。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 种子 / 管理创建 |
| 更新 | 密码、角色（TODO） |
| 冻结 | TODO |
| 删除/归档 | 有审计 FK 时禁止删 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 用户 ID | BIGINT | 是 | 系统 | 主键 | |
| username | 用户名 | VARCHAR(64) | 是 | 管理 | 登录名 | UNIQUE |
| password_hash | 密码哈希 | VARCHAR(255) | 是 | 管理 | 认证 | 不存明文 |
| role | 角色 | VARCHAR(32) | 是 | 管理 | `admin`/`operator` | CHECK |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `users_username_key` | `username` | UNIQUE |
| `idx_users_username` | `username` | 查询 |

## 上游来源

- 初始化种子 / 手工创建

## 下游使用模块

全站认证；`assetinfo_pipeline_runs.created_by`、`issuance_import_runs.created_by`（见 [assetinfo_pipeline_runs.md](assetinfo_pipeline_runs.md)）

## 数据质量规则

- `role` 仅允许 `admin`、`operator`

## 注意事项

- 导入审计表见 `assetinfo_pipeline_runs.md`、`issuance_import_runs.md`。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/users/schema.sql` |

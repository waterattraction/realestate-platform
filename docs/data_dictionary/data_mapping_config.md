# 字段映射配置（`data_mapping_config`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | Excel 字段映射配置 |
| 表英文名 | `data_mapping_config` |
| Schema 来源 | `db/modules/assetinfo/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | `(sheet_name, excel_column, target_table, target_column)` UNIQUE |

## 表用途

数据准入管道的可配置字段映射种子表；定义 Excel 列到目标表列的映射规则（与代码 `COL_ALIASES` 并行，TODO：统一策略）。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | `db/modules/assetinfo/seed_mapping.sql` |
| 更新 | 配置版本迭代 |
| 停用 | `active=false` |
| 删除/归档 | 一般逻辑停用 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 配置 ID | BIGINT | 是 | 系统 | 主键 | |
| config_version | 配置版本 | VARCHAR(32) | 是 | 管理 | 版本号 | 默认 v1.0 |
| sheet_name | Sheet 名模式 | VARCHAR(200) | 是 | 配置 | 匹配 Sheet | |
| sheet_type | Sheet 类型 | VARCHAR(32) | 是 | 配置 | monitor 等 | |
| excel_column | Excel 列名 | VARCHAR(200) | 是 | 配置 | 源列 | |
| target_table | 目标表 | VARCHAR(64) | 是 | 配置 | DB 表 | |
| target_column | 目标列 | VARCHAR(64) | 是 | 配置 | DB 列 | |
| field_semantic | 字段语义 | VARCHAR(32) | 是 | 配置 | asset 等 | 默认 asset |
| transform_rule | 转换规则 | VARCHAR(200) | 否 | 配置 | 清洗表达式 | TODO |
| is_required | 是否必填 | BOOLEAN | 是 | 配置 | 校验 | 默认 false |
| is_business_key | 是否业务键 | BOOLEAN | 是 | 配置 | 去重 | 默认 false |
| priority | 优先级 | INT | 是 | 配置 | 冲突解析 | 默认 100 |
| active | 是否启用 | BOOLEAN | 是 | 配置 | 开关 | 默认 true |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_data_mapping_config_key` | `sheet_name`, `excel_column`, `target_table`, `target_column` | UNIQUE |

## 上游来源

- `db/modules/assetinfo/seed_mapping.sql`

## 下游使用模块

- assetinfo 管道（TODO：与 `assetinfo_cleanse` 实际调用关系）

## 注意事项

- 运行时主路径以 Python `COL_ALIASES` 为准；本表为配置化预留。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/assetinfo/schema.sql` |

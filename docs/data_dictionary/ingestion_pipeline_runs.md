# 数据准入导入批次（`ingestion_pipeline_runs`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 数据准入导入批次 |
| 表英文名 | `ingestion_pipeline_runs` |
| Schema 来源 | `db/modules/users/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | 无（审计批次） |

## 表用途

记录 `/ingestion` 模块一次 Excel 上传与导入的批次审计：监控、还款等 Sheet 的汇总统计。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 上传开始时 INSERT |
| 更新 | 导入完成后更新计数 |
| 归档 | 只读保留 | **是** |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 批次 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入参数 | FK | |
| data_date | 快照日期 | DATE | 否 | 导入参数/Sheet | 批次维度 | 监控 scope |
| trust_plan_alias | 信托计划别名 | VARCHAR(200) | 否 | 导入 | 展示冗余 | TODO |
| source_file | 来源文件名 | VARCHAR(500) | 否 | 上传 | 审计 | |
| created_by | 操作人 | BIGINT | 是 | 会话 | FK → users | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| inserted_monitor_count | 监控插入行数 | INT | 是 | 导入结果 | 统计 | 默认 0 |
| inserted_repayment_count | 还款插入行数 | INT | 是 | 导入结果 | 统计 | 默认 0 |
| upsert_asset_count | 资产 upsert 数 | INT | 是 | 导入结果 | 统计 | 默认 0 |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_ingestion_pipeline_runs_created_by` | `created_by`, `created_at` | 审计查询 |
| `idx_ingestion_pipeline_runs_product_date` | `trust_product_id`, `data_date` | 按产品查批次 |

## 上游来源

- `assetinfo_upload.py` 上传流程

## 下游使用模块

- `ingestion_sheet_runs`（子记录）
- 导入审计查询（TODO：管理页）

## 注意事项

- Canonical 对象 `ImportRun`（ingestion 变体）。
- 无 `status` 列于基线 schema；状态可能由子表推断（TODO 与代码核对）。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/users/schema.sql` |

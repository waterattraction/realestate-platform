# 资产数据导入 Sheet 记录（`assetinfo_sheet_runs`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 数据准入 Sheet 导入记录 |
| 表英文名 | `assetinfo_sheet_runs` |
| Schema 来源 | `db/modules/assetinfo/schema_upload_v2.sql` |
| 主键 | `id` |
| 业务唯一标识 | scope：`(pipeline_run_id, source_file_name, source_sheet_name)` |

## 表用途

记录 assetinfo 批次内每个 Sheet 的类型、行数、action（import/overwrite/skip 等）及消息。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | Sheet 解析后 INSERT |
| 更新 | 一般不更新 |
| 归档 | 只读 | **是** |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| pipeline_run_id | 父批次 ID | BIGINT | 是 | 系统 | FK → assetinfo_pipeline_runs | |
| source_file_name | 来源文件名 | VARCHAR(500) | 是 | Excel | scope | |
| source_sheet_name | Sheet 名 | VARCHAR(200) | 是 | Excel | scope | |
| sheet_type | Sheet 类型 | VARCHAR(32) | 是 | 识别逻辑 | monitor / repayment 等 | |
| data_date | 快照日期 | DATE | 否 | Sheet | 监控 scope | |
| row_count | 行数 | INT | 是 | 导入 | 统计 | 默认 0 |
| amount_sum | 金额合计 | NUMERIC(18,2) | 否 | 导入 | 统计 | |
| action | 导入动作 | VARCHAR(32) | 是 | 预检 | import / overwrite / skip / failed | |
| message | 消息 | TEXT | 否 | 系统 | 错误或说明 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_assetinfo_sheet_runs_pipeline` | `pipeline_run_id` | 反查批次 |
| `idx_assetinfo_sheet_runs_source` | `source_file_name`, `source_sheet_name` | scope 查询 |

## 上游来源

- `assetinfo_upload.py`

## 下游使用模块

- 导入审计；覆盖 scope 判定

## 注意事项

- Canonical 对象 `ImportSheetRun`（assetinfo 变体）。
- `action` 枚举见 `docs/canonical/enumerations.md`。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | V2 上传 | `db/modules/assetinfo/schema_upload_v2.sql` |

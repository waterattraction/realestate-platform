# 发行 Sheet 导入记录（`issuance_import_sheet_runs`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 发行 Sheet 导入记录 |
| 表英文名 | `issuance_import_sheet_runs` |
| Schema 来源 | `db/modules/issuance/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | scope：`(trust_product_id, issue_date, source_file_name, source_sheet_name)` |

## 表用途

记录发行批次内每个 Sheet 的行数、金额合计、action 及消息。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | Sheet 导入后 INSERT |
| 更新 | 一般不更新 |
| 归档 | 只读 | **是** |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| import_run_id | 父批次 ID | BIGINT | 是 | 系统 | FK → issuance_import_runs | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入参数 | FK | |
| trust_product_name | 产品名称快照 | VARCHAR(200) | 是 | 导入 | 冗余 | |
| issue_date | 发行日期 | DATE | 是 | 导入参数 | scope | |
| source_file_name | 来源文件名 | VARCHAR(500) | 是 | Excel | scope | |
| source_sheet_name | Sheet 名 | VARCHAR(200) | 是 | Excel | scope | |
| sheet_type | Sheet 类型 | VARCHAR(32) | 是 | 识别 | 默认 issuance_asset | |
| row_count | 行数 | INT | 是 | 导入 | 统计 | 默认 0 |
| amount_sum | 金额合计 | NUMERIC(18,2) | 否 | 导入 | 统计 | |
| action | 导入动作 | VARCHAR(32) | 是 | 预检 | import / overwrite / needs_confirm / failed | |
| message | 消息 | TEXT | 否 | 系统 | 说明 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_issuance_import_sheet_runs_scope` | `trust_product_id`, `issue_date`, `source_file_name`, `source_sheet_name` | 覆盖 scope |

## 上游来源

- `issuance_upload.py`

## 下游使用模块

- 发行覆盖判定；审计

## 注意事项

- Canonical 对象 `ImportSheetRun`（issuance 变体）。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/issuance/schema.sql` |

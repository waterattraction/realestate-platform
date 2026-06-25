# 发行导入批次（`issuance_import_runs`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 发行导入批次 |
| 表英文名 | `issuance_import_runs` |
| Schema 来源 | `db/modules/issuance/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | 无（审计批次；维度 `trust_product_id` + `issue_date` + `source_file`） |

## 表用途

记录 `/issuance` 模块一次发行 Excel 上传与导入的批次审计及行级统计。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 上传确认导入时 INSERT |
| 更新 | 一般不更新 |
| 归档 | 只读保留 | **是** |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 批次 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入参数 | FK | |
| trust_product_name | 产品名称快照 | VARCHAR(200) | 是 | 导入 | 冗余展示 | |
| issue_date | 发行日期 | DATE | 是 | 导入参数 | **发行时间维度** | 非 data_date |
| source_file | 来源文件名 | VARCHAR(500) | 是 | 上传 | 审计 | |
| created_by | 操作人 | BIGINT | 是 | 会话 | FK → users | |
| inserted_row_count | 插入行数 | INT | 是 | 导入结果 | 统计 | 默认 0 |
| deleted_row_count | 删除行数 | INT | 是 | 覆盖导入 | 统计 | 默认 0 |
| skipped_sheet_count | 跳过 Sheet 数 | INT | 是 | 导入结果 | 统计 | 默认 0 |
| failed_sheet_count | 失败 Sheet 数 | INT | 是 | 导入结果 | 统计 | 默认 0 |
| error_message | 错误信息 | TEXT | 否 | 系统 | 批次失败说明 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_issuance_import_runs_product_issue` | `trust_product_id`, `issue_date` | 按产品查批次 |

## 上游来源

- `issuance_upload.py`

## 下游使用模块

- `issuance_import_sheet_runs`
- 发行导入历史（TODO：管理页）

## 注意事项

- Canonical 对象 `ImportRun`（issuance 变体）。
- 发行模块无 `data_date`。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/issuance/schema.sql` |

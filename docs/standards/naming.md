# 命名规范（初稿）

## 数据库

| 类别 | 规则 | 示例 |
|------|------|------|
| 表名 | snake_case，复数或 `_records` 后缀 | `trust_product_issuance_asset_records` |
| 列名 | snake_case，语义明确 | `custody_asset_code` |
| 主键 | `id` BIGINT IDENTITY | |
| 外键列 | `<entity>_id` | `trust_product_id` |
| 审计列 | `created_at`, `updated_at` | TIMESTAMPTZ |
| 来源追溯 | `source_file_name`, `source_sheet_name`, `source_row_number` | |

## 代码语义字段（Canonical）

- 使用 `snake_case` 英文，与 DB 列名一致
- Excel 中文列名**不得**直接作为代码变量名
- 别名仅出现在 `COL_ALIASES` 或 `docs/excel/`

## Excel 列名

- 允许多种中文表述，映射到同一 Canonical 字段
- 注意全角/半角括号：`（数值）` vs `(数值)`
- 新 Excel 列优先与现有别名合并，避免造新 synonym

## API / 文档

| 层 | 风格 |
|----|------|
| REST JSON | snake_case（与 DB 一致） |
| Canonical 对象（未来） | PascalCase 对象名 + snake_case 字段 |
| 中文展示 | 页面标签，不入库作字段名 |

## 禁止

- 新字段名：`asset_code`（除历史表）、`房源编号`（作 DB 列名）
- 根目录新增 `.sql`
- 发行模块新增 `data_date`

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2 初稿 |

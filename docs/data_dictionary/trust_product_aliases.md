# 信托产品别名（`trust_product_aliases`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 信托产品别名 |
| 表英文名 | `trust_product_aliases` |
| Schema 来源 | `db/migrations/20260624_trust_product_aliases.sql` |
| 主键 | `id` |
| 业务唯一标识 | `alias_name` UNIQUE |

## 表用途

将 Excel 中出现的非正式产品名（如「单一信托」）解析为 `trust_products.id`，用于发行 `from_trust_product_name` 解析。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | migration seed / 管理维护 |
| 更新 | 一般不更新别名文本 |
| 删除/归档 | 有历史发行引用时慎删 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 别名 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 配置 | FK → trust_products | |
| alias_name | 别名 | VARCHAR(200) | 是 | Excel/配置 | 匹配文本 | UNIQUE |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_trust_product_aliases_alias_name` | `alias_name` | 全局唯一别名 |
| `idx_trust_product_aliases_product` | `trust_product_id` | 反查产品 |

## 上游来源

- `db/migrations/20260624_trust_product_aliases.sql`（如 `单一信托` → 美润1号）

## 下游使用模块

- 发行：`issuance_upload._resolve_from_trust_product`
- `from_trust_product_id` / `migration_type=transfer` 推断

## 注意事项

- 别名全局唯一；解析顺序：alias 表 → `trust_products.name`。
- 见 `docs/canonical/alias_dictionary.md` 中 `from_trust_product_name` 相关列。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06 | 初版 | `db/migrations/20260624_trust_product_aliases.sql` |

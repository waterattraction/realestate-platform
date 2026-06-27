# Canonical Data Language（统一数据语言）

## 是什么

Canonical Data Language（CDL）是跨 **Excel、数据库、API、BI、AI Agent、MCP** 的统一语义层。它回答：

> 同一个业务概念，在全系统里应该叫什么、映射到哪里、禁止用什么同义词。

映射链路：

```
Excel 列名 / 业务口语
    ↓  alias_dictionary.md
Canonical Field（字段） / Canonical Object（对象）
    ↓  field_dictionary.md / object_dictionary.md
DB 列 / 表
    ↓
API 字段（camelCase，开放接口预留）
    ↓
AI / BI 语义标签
```

示例：

```
房源编号 / 房源编码 / 托管房源号
    → custody_asset_code
    → trust_assets.custody_asset_code
    → custodyAssetCode
    → Custody Asset Code / 托管房源号
```

## 与现有 M2 文档的区别

| 文档 | 层级 | 回答的问题 |
|------|------|-----------|
| **`docs/canonical/`** | 跨层语义 | 全系统统一叫什么？别名归谁？枚举值是什么？ |
| `docs/data_dictionary/` | 物理表 | 这张表有哪些列、索引、上下游？ |
| `docs/excel/` | 导入 | 某 Sheet 如何识别、清洗、预检？ |
| `docs/standards/` | 规范 | 编码规则、数据质量、命名约定 |
| `db/modules/*.sql` | 实现 | 数据库 DDL 真相源 |

**M2.5 不替代** `data_dictionary` / `excel` / `standards`，而是在其之上增加 **统一语言层**。

## 如何使用

### 新增 Excel 列 / 别名

1. 查 [`alias_dictionary.md`](alias_dictionary.md) — 是否已有别名
2. 查 [`field_dictionary.md`](field_dictionary.md) — 归哪个 Canonical Field
3. 无则 **先补 canonical**，再改 `issuance_cleanse` / `assetinfo_upload`

### 新增 DB 列

1. 查 `field_dictionary.md` — 是否已有 Canonical Field
2. 查 `object_dictionary.md` — 属于哪个对象
3. **先补 canonical** → migration → `data_dictionary`

### 新增 API / BI / AI 字段

1. 复用 `field_dictionary.md` 中的 Canonical Field 与 API 列
2. 不得新建同义字段（如 `houseCode`、`assetNo`）
3. 枚举查 [`enumerations.md`](enumerations.md)

### Cursor 修改前

必须先查 `docs/canonical/*`，见 [`.cursor/rules/data_model.mdc`](../../.cursor/rules/data_model.mdc)。

## 本目录文件

| 文件 | 用途 |
|------|------|
| [`field_dictionary.md`](field_dictionary.md) | Canonical 字段定义 |
| [`object_dictionary.md`](object_dictionary.md) | Canonical 业务对象 |
| [`alias_dictionary.md`](alias_dictionary.md) | Excel / 口语别名 |
| [`enumerations.md`](enumerations.md) | 枚举值 |
| [`status_dictionary.md`](status_dictionary.md) | 各模块 status 字段 |

## 变更流程

```
先补 docs/canonical/ → 评审 → 同步 data_dictionary / excel / standards → Migration → 代码
```

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.5 初稿 |

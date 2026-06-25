# M2 / M2.5 数据标准化文档

本目录为 **M2：Data Standardization** 与 **M2.5：Canonical Data Language** 文档根目录，与 M1 数据库治理（`db/`）配套使用。

## 目标

统一平台业务对象、字段定义、Excel 映射、编码规则与数据质量语言，供发行、监控、还款、逾期、风险、导入、BI、AI Agent 共用。

**M2.5** 在 M2 之上增加跨 Excel / DB / API / AI 的 **统一语义层**（`docs/canonical/`）。

## 目录

| 目录 | 用途 | 状态 |
|------|------|------|
| [`canonical/`](canonical/README.md) | **统一数据语言**（字段/对象/别名/枚举/status） | ✅ M2.5 初稿 |
| [`glossary.md`](glossary.md) | 核心术语对照 | ✅ 初稿 |
| [`data_dictionary/`](data_dictionary/README.md) | 表级数据字典（物理层） | ✅ P1 骨架 |
| [`excel/`](excel/) | Excel 导入标准 | ✅ P2 初稿 |
| [`standards/`](standards/) | 标识符、数据质量、命名 | ✅ 初稿 |
| [`_templates/`](_templates/) | 文档模板 | ✅ |
| [`architecture/`](architecture/) | 领域模型、血缘、生命周期 | ⏳ 下一批（P4） |
| [`api/`](api/) | Canonical Data Model | ⏳ 下一批（P5） |

## M2 与 M2.5 关系

| 层级 | 目录 | 回答的问题 |
|------|------|-----------|
| 语义层 | `canonical/` | 全系统统一叫什么？别名归谁？ |
| 物理层 | `data_dictionary/` | 表有哪些列？ |
| 导入层 | `excel/` | Sheet 如何清洗？ |
| 规范层 | `standards/` | 编码与命名规则 |
| 实现层 | `db/` | DDL 真相源 |

## 变更流程

```
设计 → 评审 → Migration（db/migrations/）→ 实施 → 验收 → 同步 docs/
```

新增字段、表、Excel 映射、API 字段、BI 指标、AI Agent 输出前，须先查 [`canonical/`](canonical/README.md)，并遵循 [`.cursor/rules/data_model.mdc`](../.cursor/rules/data_model.mdc)。

## 与 M1 的关系

| M1 | M2 |
|----|-----|
| `db/manifest.txt` | `data_dictionary` Schema 来源 |
| `db/README.md` SQL 评审 | `data_model.mdc` 字段级评审 |
| `db/migrations/` | 字典与 Excel 文档同步更新 |

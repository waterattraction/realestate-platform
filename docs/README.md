# M2 数据标准化文档

本目录为 **M2 数据治理** 文档根目录，与 M1 数据库治理（`db/`）配套使用。

## M2 Completion Status

| 里程碑 | 状态 |
|--------|------|
| M2 Data Standardization | **completed** |
| M2.5 Canonical Data Language | **completed** |
| P4 Architecture Docs | **completed** |
| P5 Canonical API Model | **completed** |
| M2.6 Documentation Automation | **completed** |
| M2.7 Documentation Health | **completed** |

**封版后约定**：新增字段、表、Excel alias、API/BI/AI 字段必须同步更新 `docs/` 并运行 `python3 scripts/doc_health.py`（见 [`.cursor/rules/data_model.mdc`](../.cursor/rules/data_model.mdc)）。

## 目标

统一平台业务对象、字段定义、Excel 映射、编码规则与数据质量语言，供发行、监控、还款、逾期、风险、导入、BI、AI Agent 共用。

**M2.5** 在 M2 之上增加跨 Excel / DB / API / AI 的 **统一语义层**（`docs/canonical/`）。

## 目录

| 目录 | 用途 | 状态 |
|------|------|------|
| [`canonical/`](canonical/README.md) | **统一数据语言**（字段/对象/别名/枚举/status） | ✅ |
| [`glossary.md`](glossary.md) | 核心术语对照 | ✅ |
| [`data_dictionary/`](data_dictionary/README.md) | 表级数据字典（物理层，20/20 表） | ✅ |
| [`excel/`](excel/) | Excel 导入标准 | ✅ |
| [`standards/`](standards/) | 标识符、数据质量、命名 | ✅ |
| [`architecture/`](architecture/domain_model.md) | 领域模型、血缘、生命周期 | ✅ |
| [`api/`](api/canonical_data_model.md) | Canonical API Data Model | ✅ |
| [`_templates/`](_templates/) | 文档模板 | ✅ |

## M2 文档层级

| 层级 | 目录 | 回答的问题 |
|------|------|-----------|
| 语义层 | `canonical/` | 全系统统一叫什么？别名归谁？ |
| 物理层 | `data_dictionary/` | 表有哪些列？ |
| 导入层 | `excel/` | Sheet 如何清洗？ |
| 规范层 | `standards/` | 编码与命名规则 |
| 架构层 | `architecture/` | 对象关系与数据流 |
| API 层 | `api/` | 对外对象模型 |
| 实现层 | `db/` | DDL 真相源 |

## 变更流程

```
先查 canonical/ → 设计评审 → Migration → 实施 → 同步 docs/ → scripts/doc_health.py
```

新增字段、表、Excel 映射、API 字段、BI 指标、AI Agent 输出前，须先查 [`canonical/`](canonical/README.md)，并遵循 [`.cursor/rules/data_model.mdc`](../.cursor/rules/data_model.mdc)。

## 与 M1 的关系

| M1 | M2 |
|----|-----|
| `db/manifest.txt` | `data_dictionary` Schema 来源 |
| `db/README.md` SQL 评审 | `data_model.mdc` 字段级评审 |
| `db/migrations/` | 字典与 Excel 文档同步更新 |

## 文档健康检查

```bash
python3 scripts/doc_health.py
python3 scripts/doc_health.py --strict   # CI
```

详见 [`scripts/README.md`](../scripts/README.md)。

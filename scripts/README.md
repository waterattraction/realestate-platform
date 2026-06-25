# Documentation Automation Scripts (M2.6 / M2.7)

轻量文档校验与覆盖率检查工具。**默认只读**，不修改任何文件；`--write` 预留但未实现。

## 前置

```bash
cd /opt/realestate-platform
python3 scripts/<script>.py
```

依赖：Python 3.10+ 标准库（无第三方包）。

## 脚本用途

| 脚本 | 用途 |
|------|------|
| `validate_canonical.py` | `identifiers.md` ↔ `field_dictionary.md`；`alias_dictionary.md` 映射校验 |
| `validate_glossary.py` | `glossary.md` 术语是否在 canonical / identifiers 中 |
| `schema_diff.py` | `db/manifest.txt` 表/列 vs `data_dictionary/` |
| `gen_data_dictionary_stub.py` | 同上（data dictionary 桩检查别名） |
| `gen_excel_aliases_stub.py` | `COL_ALIASES` vs `docs/excel/*.md` |
| `doc_health.py` | **总览**：汇总上述检查 + Documentation Health Summary |

内部模块：`_common.py`（解析）、`_health.py`（检查逻辑与输出格式）。

## 输出格式

```
PASS    <检查项>              <说明>
WARNING <检查项>              <说明>
FAIL    <检查项>              <说明>
         - <缺失项>
```

## Exit Code 规则（M2.7）

| 情况 | 默认 exit | `--strict` exit |
|------|-----------|-----------------|
| 全部 PASS | **0** | **0** |
| 文档覆盖率不足（WARNING） | **0** | **1** |
| SQL 解析失败 / manifest 缺失 / 路径错误 | **1** | **1** |
| canonical alias 指向不存在字段 | **1** | **1** |
| 脚本运行异常 | **1** | **1** |

`--strict` 用于未来 CI：任何 WARNING 也失败。

## M2.7 文档健康检查流程

新增字段、表、Excel 别名后：

1. 更新 `docs/canonical/`、`docs/data_dictionary/`、`docs/excel/`（见 `data_model.mdc`）
2. 运行 `python3 scripts/doc_health.py`
3. 发布前可选：`python3 scripts/doc_health.py --strict`

目标覆盖率：**Data Dictionary 100%**、**Canonical 100%**、**Glossary 100%**、**Excel Alias 100%**。

## 推荐命令

```bash
python3 scripts/validate_canonical.py
python3 scripts/validate_glossary.py
python3 scripts/schema_diff.py
python3 scripts/gen_data_dictionary_stub.py
python3 scripts/gen_excel_aliases_stub.py
python3 scripts/doc_health.py
```

Strict 模式（CI）：

```bash
python3 scripts/doc_health.py --strict
```

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.6 初版 |
| 2026-06 | M2.7 统一输出、exit code、`doc_health.py` |

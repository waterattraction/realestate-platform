# Documentation Automation Scripts (M2.6)

轻量文档校验与草案生成工具。**默认只读**，不修改任何文件；`--write` 预留但当前未实现。

## 前置

```bash
cd /opt/realestate-platform
python3 scripts/<script>.py
```

依赖：Python 3.10+ 标准库（无第三方包）。

## 脚本

| 脚本 | 用途 |
|------|------|
| `gen_data_dictionary_stub.py` | 从 `db/**/*.sql` 解析 `CREATE TABLE`，对比 `docs/data_dictionary/*.md` 缺失表/列 |
| `gen_excel_aliases_stub.py` | 从 `issuance_cleanse.py` / `ingestion_cleanse.py` 提取 `COL_ALIASES`，检查 `docs/excel/*.md` |
| `validate_canonical.py` | `identifiers.md` 关键字段是否出现在 `field_dictionary.md`；alias 是否映射到已有 canonical field |
| `validate_glossary.py` | `glossary.md` 中 canonical 字段是否在 `field_dictionary.md` 或 `identifiers.md` |
| `schema_diff.py` | `db/manifest.txt` SQL 与 `data_dictionary` 字段覆盖差异 |

## 示例

```bash
# 检查 canonical 一致性（期望 exit 0）
python3 scripts/validate_canonical.py

# 检查 glossary 覆盖
python3 scripts/validate_glossary.py

# SQL vs data_dictionary 差异（预期有缺失项，exit 1）
python3 scripts/schema_diff.py

# data_dictionary 桩检查
python3 scripts/gen_data_dictionary_stub.py

# Excel 别名提取与文档对照
python3 scripts/gen_excel_aliases_stub.py
```

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 无问题 |
| 1 | 发现差异/缺失（信息性报告） |
| 2 | 运行错误 |

## 与 M2 文档关系

校验顺序与 [`.cursor/rules/data_model.mdc`](../.cursor/rules/data_model.mdc) 一致：`canonical/` → `data_dictionary/` → `excel/` → `standards/`。

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.6 初版脚本 |

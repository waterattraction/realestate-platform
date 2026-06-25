# 逾期 / 跟进 Excel 导入标准

## 1. Sheet 类型

| sheet_type | 说明 |
|------------|------|
| — | **当前无独立 Excel 导入模板** |

## 2. 识别规则

平台**不提供**逾期跟进台账的 Excel 批量导入 Sheet 类型。

逾期相关数据主要通过：

1. **资产监控快照**（`docs/excel/monitor.md`）中的 `overdue_days` 等指标
2. **系统规则**生成 `trust_overdue_followups` 记录
3. **页面人工维护**跟进状态、计划、反馈

## 3. 必填列

不适用（无 Excel 导入）。

## 4. 可选列

不适用。

## 5. 别名列

不适用。以下术语仅作跨模块对照：

| 概念 | 落库 |
|------|------|
| 逾期跟进 | `trust_overdue_followups` |
| 风险案件（逻辑） | `trust_overdue_followups` 扩展列 + `risk_alerts` |

## 6. 数据类型与清洗

不适用 Excel；页面/API 写入时遵循 `docs/standards/data_quality.md`。

## 7. Warning / Failed 规则

不适用导入预检。

## 8. 导入 Action

不适用。

## 9. 字段映射总表

无 Excel → DB 映射。核心表见 `docs/data_dictionary/overdue.md`。

## 10. 示例值

无 Excel 样例。

## 11. 对应代码

| 模块 | 说明 |
|------|------|
| `/overdue` | 页面维护跟进台账 |
| 风险 V2 | 扩展 `trust_overdue_followups` Case 字段 |

## 注意事项

- 若未来新增逾期 Excel 导入，须先更新本文档、`data_dictionary/overdue.md` 及 `data_model.mdc` 评审流程。
- 不要将监控 Sheet 误当作逾期跟进导入。

# 还款明细 Excel 导入标准

对齐模版：`excel文件/还款明细披露信息模版.xlsx`（Sheet「还款明细」+「回款计划」）。

## 1. Sheet 类型

| sheet_type | 中文名 | 代码入口 |
|------------|--------|----------|
| `repayment_detail` | 还款明细 | `assetinfo_upload` |
| `repayment_plan` | 回款计划 | `assetinfo_upload` → `trust_repayment_plan_records` |

## 2. 识别规则

**文件名关键词：** 还款明细

**Sheet 名关键词：** 还款明细、已还款、还款披露

**回款计划：** Sheet 名含「回款计划」→ `repayment_plan`（**不再 skip**）

**表头关键列（还款明细）：**

- `托管房源编码` / `托管房源编号` → `custody_asset_code`
- `资产编号(房源)` → `source_asset_code`
- `当期实际还款金额`
- `还款日期` / `当期还款日期` → `repayment_date`（缺失时可用 Sheet 名/产品规则 fallback）

**日期：** 优先从 Sheet 名/产品名解析 fallback date（`assetinfo_date_rules`）

## 3. 模版列 vs 系统字段（还款明细）

| 模版列 | DB 字段 | 导入 | 导出 |
|--------|---------|:----:|:----:|
| 资产包编号 | `asset_pool_code` | ✅ | ✅ |
| 当前还款方 | `current_payer` | ✅ | ✅ |
| 托管房源编码 | `custody_asset_code` | ✅ | ✅ |
| 当期计划还款金额 | `planned_repayment_amount` | ✅ | ✅ |
| 初始受让装修金额 | `initial_renovation_amount` | ✅ | ✅ |
| 累计已还款金额 | `cumulative_repaid_amount` | ✅ | ✅ |
| 剩余应还款余额 | `remaining_balance` | ✅ | ✅ |
| 当期实际还款金额 | `actual_repayment_amount` | ✅ | ✅ |
| 当期逾期天数 | — | ❌ **不导入** | ✅ 取自最新监控 `overdue_days` |

系统另存业务列（非披露模版必列）：`repayment_date`、`period_no`、`source_asset_code` 等。

## 4. 回款计划（独有列不编造）

回款计划 Sheet 写入 `trust_repayment_plan_records`。模版 4 个独有列仅来自该 Sheet：

| 模版列 | DB 字段 |
|--------|---------|
| 当期账单日 | `current_bill_date` |
| 回款金额明细 | `repayment_amount_detail` |
| 后续计划每月回款金额 | `planned_monthly_repayment_amount` |
| 最后一期计划回款金额 | `final_planned_repayment_amount` |

其余列（资产包编号、资产编号、装修服务商、统计日期、金额、小区、城市等）一并导入。

## 5. 导出与列表

- 列表页：`/assetinfo/repayment-plan-records`（筛选 / 分页 / JSON）
- 导出：`GET /assetinfo/repayment-records/export` → 双 Sheet
  1. **还款明细**：披露模版 9 列；`当期逾期天数` = 最新监控 `overdue_days`
  2. **回款计划**：披露模版 13 列；无计划数据时为空表头

## 6. Warning / Failed 规则

| 条件 | 级别 |
|------|------|
| 缺托管/资产编号列 | failed |
| 资产编号与托管编码不一致 | needs_confirm |
| 无法解析 repayment_date | 行 failed |
| Sheet 内完全重复 | reject / warning |
| 跨文件 overlap | needs_confirm |
| 与库内完全一致 | skip |

## 7. 对应代码

| 文件 | 职责 |
|------|------|
| `backend/app/assetinfo_templates.py` | 模版列契约 |
| `backend/app/assetinfo_upload.py` | 预检 / 导入 / 导出 |
| `backend/app/assetinfo_cleanse.py` | 列别名与清洗 |
| `db/migrations/20260720_monitor_repayment_template_columns.sql` | 列与回款计划表 |

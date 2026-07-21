# 还款明细 Excel 导入标准

对齐模版：`excel文件/还款明细披露信息模版.xlsx`（Sheet「还款明细」+「回款计划」）。

列表页标题为「还款明细导入数据」。

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

- `托管房源编码` / `托管房源编号` → `custody_asset_code`（缺省时 = 左 12）
- `资产编号(房源)` → `asset_code`（**仅左 12**）；不再写入 `source_asset_code`
- `当期实际还款金额`
- `还款日期` / `当期还款日期` → `repayment_date`（缺失时可用 Sheet 名/产品规则 fallback）

**日期：** 优先从 Sheet 名/产品名解析 fallback date（`assetinfo_date_rules`）

**房源 ≠ 托管：** 预检 ERROR（`needs_confirm`），与监控一致。

## 3. 模版列 vs 系统字段（还款明细）

| 模版列 | DB 字段 | 导入 | 导出 | 备注 |
|--------|---------|:----:|:----:|------|
| 信托产品 | `trust_product_name` | — | ✅ | 系统关联产品名 |
| 当前还款方 | `current_payer` | ✅ | ✅ | |
| 资产编号(房源) | `asset_code` | ✅ | ✅ | **主编号（左 12）**；不再导出托管房源编码 |
| 当期计划还款金额 | `planned_repayment_amount` | ✅ | ✅ | |
| 初始受让装修金额 | `initial_renovation_amount` | ✅ | ✅ | 披露按截止日当天明细行原样带出 |
| 累计已还款金额 | `cumulative_repaid_amount` | ✅ | ✅ | 同上 |
| 剩余应还款余额 | `remaining_balance` | ✅ | ✅ | 同上 |
| 当期实际还款金额 | `actual_repayment_amount` | ✅ | ✅ | |
| 当期逾期天数 | — | ❌ **不导入** | ✅ 取自最新监控 `overdue_days` |

导入仍可读 Excel「托管房源编码」写入 `custody_asset_code`（持久化锚点），但**披露预览/导出模版不展示该列**。

系统另存业务列：`repayment_date`、`period_no` 等。

**已停用 / 已 DROP：**

| 项 | 说明 |
|----|------|
| 资产包编号 / `asset_pool_code` | 已 DROP；不再导入、不再展示 |
| `source_asset_code` | 死列；**停导入、停展示** |

**主编号策略：** 已有非空 `asset_code` 不 UPDATE；仅无主编号时回填。

### 例外：美好生活3号 ·「0612已还款」

该 Sheet 托管列历史上错位（见 ops repair [`product3_repay_0612_custody`](../../db/ops/fixes/product3_repay_0612_custody/)）。代码常量 `PRODUCT3_REPAY_0612_EXCLUDE`：**不参与主编号推导/回填**，与 repair 口径一致。

## 4. 回款计划（独有列不编造）

回款计划 Sheet 写入 `trust_repayment_plan_records`。披露预览/导出模版首列为「信托产品」，「资产编号(房源)」= `asset_code`（主编号，左 12）。

模版 4 个独有列仅来自该 Sheet：

| 模版列 | DB 字段 |
|--------|---------|
| 当期账单日 | `current_bill_date` |
| 回款金额明细 | `repayment_amount_detail` |
| 后续计划每月回款金额 | `planned_monthly_repayment_amount` |
| 最后一期计划回款金额 | `final_planned_repayment_amount` |

其余列（资产编号左 12、托管、装修服务商、统计日期、金额、小区、城市等）一并导入；不含资产包编号 / source。

**小区名称别名：** Excel 列可为「小区名称」或「小区地址」（美好生活3号/4号回款计划用「小区地址」）→ `community_name`。

## 5. 导出与列表

- 列表页：`/assetinfo/repayment-plan-records`（筛选 / 分页 / JSON）
- 导出：`GET /assetinfo/repayment-records/export` → 双 Sheet
  1. **还款明细**：披露模版列；`当期逾期天数` = 最新监控 `overdue_days`
  2. **回款计划**：披露模版列；无计划数据时为空表头

**数据披露（活数据 / 冻结）还款明细行规则**（`disclosure.fetch_repayment_live`）：

- 对齐导入明细按「数据日期」筛选：`repayment_date = 披露截止日`
- 且 `当期实际还款金额 > 0`
- 截止日当天无还款的资产不进入披露预览 / 冻结 / 导出
- 余额三列（初始受让装修金额 / 累计已还款金额 / 剩余应还款余额）随该行原样带出

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
| `db/migrations/20260721_drop_asset_pool_code.sql` | DROP `asset_pool_code` |

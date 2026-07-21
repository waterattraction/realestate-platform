# 回款计划（`trust_repayment_plan_records`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 回款计划 |
| 表英文名 | `trust_repayment_plan_records` |
| Schema 来源 | `db/migrations/20260720_monitor_repayment_template_columns.sql` |
| 主键 | `id` |
| 覆盖 scope | `trust_product_id` + `source_file_name` + `source_sheet_name` |

## 表用途

存还款披露 Excel「回款计划」Sheet 事实行。模版 4 个独有列（当期账单日、回款金额明细、后续计划每月回款金额、最后一期计划回款金额）**仅来自该 Sheet，不编造**。

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 备注 |
|-------|--------|------|:----:|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入 | FK |
| trust_asset_id | 底层资产 ID | BIGINT | 否 | 导入 | FK 可空 |
| asset_code | 资产编号 | VARCHAR(64) | 是 | Excel | |
| custody_asset_code | 托管房源号 | VARCHAR(64) | 否 | Excel | |
| source_asset_code | 资产编号(房源) | VARCHAR(64) | 否 | Excel | 导出优先 |
| asset_pool_code | 资产包编号 | VARCHAR(64) | 否 | Excel | |
| renovation_vendor | 装修服务商 | VARCHAR(200) | 否 | Excel | |
| data_date | 统计日期 | DATE | 否 | Excel | |
| initial_transfer_amount | 初始受让金额 | NUMERIC(18,2) | 否 | Excel | |
| repaid_amount | 已还款金额 | NUMERIC(18,2) | 否 | Excel | |
| remaining_amount | 剩余还款金额 | NUMERIC(18,2) | 否 | Excel | |
| community_name | 小区名称 | VARCHAR(200) | 否 | Excel | 列别名：小区名称 / 小区地址 |
| city | 城市 | VARCHAR(64) | 否 | Excel | |
| current_bill_date | 当期账单日 | DATE | 否 | Excel | 独有列 |
| repayment_amount_detail | 回款金额明细 | TEXT | 否 | Excel | 独有列 |
| planned_monthly_repayment_amount | 后续计划每月回款金额 | NUMERIC(18,2) | 否 | Excel | 独有列 |
| final_planned_repayment_amount | 最后一期计划回款金额 | NUMERIC(18,2) | 否 | Excel | 独有列 |
| source_file_name | 来源文件名 | VARCHAR(500) | 是 | 系统 | |
| source_sheet_name | 来源 Sheet | VARCHAR(200) | 是 | 系统 | |
| source_row_number | 来源行号 | INT | 否 | 系统 | |
| synced_at | 同步时间 | TIMESTAMPTZ | 是 | 系统 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | |

## 上游 / 下游

- 上游：还款明细披露 Excel「回款计划」Sheet（`/assetinfo`）
- 下游：`GET /assetinfo/repayment-records/export` 第二 Sheet

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-07-20 | 新建 | `db/migrations/20260720_monitor_repayment_template_columns.sql` |

# 信托产品发行资产明细（`trust_product_issuance_asset_records`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 信托产品发行资产明细 |
| 表英文名 | `trust_product_issuance_asset_records` |
| Schema 来源 | `db/modules/issuance/schema.sql` |
| 主键 | `id` |
| 业务唯一标识 | 无 DB 级 UNIQUE；冲突分析用 `business_asset_key`（**非唯一约束**） |

## 表用途

记录信托产品某次发行（`issue_date`）下的入池/转让资产明细，来源于发行 Excel 导入。是发行模块的唯一业务事实表。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | `/issuance/import` 导入 INSERT |
| 更新 | 同 scope 覆盖导入：先 DELETE 再 INSERT |
| 冻结 | TODO：发行定稿后是否允许修改 |
| 删除/归档 | scope DELETE：`trust_product_id + issue_date + source_file_name + source_sheet_name` |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入参数 | 产品维度 | FK |
| trust_product_name | 信托产品名称 | VARCHAR(200) | 是 | 导入快照 | 展示 | |
| from_trust_product_id | 转出产品 ID | BIGINT | 否 | 解析 | 迁移来源产品 | FK；alias 解析 |
| from_trust_product_name | 转出产品名称 | VARCHAR(200) | 否 | Excel/解析 | 迁移来源展示 | |
| planned_trust_product_id | 拟转入产品 ID | BIGINT | 否 | 解析 | 拟转入计划 | FK；alias 解析 |
| planned_trust_product_name | 拟转入产品名称 | VARCHAR(200) | 否 | Excel/解析 | 拟转入展示；未匹配保留原文 | |
| migration_type | 迁移类型 | VARCHAR(32) | 否 | Excel/推断 | `new_issuance`/`transfer` 等 | |
| trust_asset_id | 底层资产 ID | BIGINT | 否 | 系统 | 可选关联 `trust_assets` | 常为 NULL |
| issue_date | 发行日 | DATE | 是 | 导入参数 | **唯一业务时间维度** | **无 data_date** |
| business_asset_key | 发行资产标识 | VARCHAR(128) | 是 | 计算 | 冲突分析键 | 见注意事项 |
| custody_asset_code | 托管房源号 | VARCHAR(64) | 是 | Excel | 跨模块主体识别 | |
| issuance_weight | 发行权重 | NUMERIC(10,6) | 否 | Excel | TODO | |
| migration_reason | 迁移原因 | VARCHAR(500) | 否 | Excel | TODO | |
| contract_name | 合同名称 | VARCHAR(200) | 否 | Excel | | |
| debtor_name | 债务人姓名 | VARCHAR(100) | 否 | Excel | | |
| property_address | 房源地址 | TEXT | 否 | Excel | 城市解析回退 | |
| city | 城市 | VARCHAR(64) | 否 | Excel/解析 | 北京/上海等 | |
| contractor_name | 施工方名称 | VARCHAR(200) | 否 | Excel | | |
| brand | 品牌 | VARCHAR(100) | 否 | Excel | | |
| product_style | 产品风格 | VARCHAR(100) | 否 | Excel | | |
| property_status | 房屋状态 | VARCHAR(100) | 否 | Excel | | |
| original_creditor | 原始债权人 | VARCHAR(200) | 否 | Excel | | |
| receivable_contract_amount | 应收账款合同金额 | NUMERIC(18,2) | 是 | Excel | 必填金额 | ≥ 0 |
| asset_transfer_discount_rate | 资产转让折扣率 | NUMERIC(10,6) | 否 | Excel | 0~1 小数 | |
| receivable_transfer_amount | 应收账款转让价款 | NUMERIC(18,2) | 是 | Excel | 必填金额 | ≥ 0 |
| min_institution_transferable_amount | 机构可转让最小额 | NUMERIC(18,2) | 否 | Excel | | |
| remaining_unpaid_amount_beike_not_withheld | 贝壳未代扣剩余 | NUMERIC(18,2) | 否 | Excel | | |
| rental_price | 出房价格 | NUMERIC(18,2) | 否 | Excel | | |
| total_rent_withholding_amount | 总租金代扣金额 | NUMERIC(18,2) | 否 | Excel | | |
| rent_withheld_amount_before_pooling | 封包前已代扣租金 | NUMERIC(18,2) | 否 | Excel | | |
| withholding_periods_at_pooling | 封包时代扣期数 | INT | 否 | Excel | | |
| initial_expected_withholding_cycle | 预计代扣周期 | VARCHAR(64) | 否 | Excel | | |
| renovation_payment_method | 装修付款形式 | VARCHAR(100) | 否 | Excel | | |
| rent_withholding_ratio | 租金代扣比例 | NUMERIC(10,6) | 否 | Excel | 0~1 | |
| calculated_rent_withholding_per_period | 每期代扣金额 | NUMERIC(18,2) | 否 | Excel | | |
| agreed_repayment_periods | 约定还款期数 | INT | 否 | Excel | | |
| installment_payable_amount | 每期应付金额 | NUMERIC(18,2) | 否 | Excel | | |
| withheld_unpaid_amount | 已代扣未付款 | NUMERIC(18,2) | 否 | Excel | | |
| withheld_repaid_amount | 已代扣已回款 | NUMERIC(18,2) | 否 | Excel | | |
| transferred_receipt_total | 已转让收款合计 | NUMERIC(18,2) | 否 | Excel | | |
| rent_withholding_received_total | 已租金代扣到账合计 | NUMERIC(18,2) | 否 | Excel | | |
| first_rent_withholding_date | 首次租金代扣日 | DATE | 否 | Excel | | |
| signing_date | 签约日期 | DATE | 否 | Excel | | |
| rental_contract_end_date | 出房合同结束日 | DATE | 否 | Excel | | |
| expected_last_rent_payment_date_initial | 预计最后一期租金支付日 | DATE | 否 | Excel | | |
| expected_receivable_due_date | 预计应收账款到期日 | DATE | 否 | Excel | | |
| source_file_name | 来源文件名 | VARCHAR(500) | 是 | 系统 | 覆盖 scope | |
| source_sheet_name | 来源 Sheet | VARCHAR(200) | 是 | 系统 | 覆盖 scope | |
| source_row_number | Excel 行号 | INT | 否 | 系统 | 追溯 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_issuance_product` | `trust_product_id` | 按产品 |
| `idx_issuance_product_issue` | `trust_product_id, issue_date` | 按产品+发行日 |
| `idx_issuance_source_scope` | `trust_product_id, issue_date, source_file_name, source_sheet_name` | 覆盖删除 scope |
| `idx_issuance_business_key` | `business_asset_key` | 冲突查询（非唯一） |
| `idx_issuance_cross_file_check` | `trust_product_id, issue_date, custody_asset_code` | 跨文件重复 |
| `idx_issuance_from_product` | `from_trust_product_id` | 转出产品 |
| `idx_issuance_planned_product` | `planned_trust_product_id` | 拟转入产品 |
| `idx_issuance_migration_type` | `migration_type` | 迁移类型 |
| `idx_issuance_custody` | `trust_product_id, custody_asset_code` | 按托管号 |

## 上游来源

- 发行 Excel：`/issuance/upload` → `issuance_cleanse` → `issuance_upload`
- 用户指定 `trust_product_id`、`issue_date`

## 下游使用模块

发行记录查询（`/issuance/records`）、Dashboard 发行数据区；TODO：BI / 核对链路

## 数据质量规则

- 必填：`custody_asset_code`、`receivable_contract_amount`、`receivable_transfer_amount`
- 金额非负（CHECK 约束）
- 同 scope 覆盖导入，禁止重复 INSERT 变 2 倍行数

## 注意事项

- **本模块无 `data_date` 字段**；业务时间维度**仅为 `issue_date`**。禁止在发行逻辑中引入 `data_date`。
- **`business_asset_key`** = `{trust_product_id}:{issue_date}:{custody_asset_code}`（ISO 日期）。用于 precheck 跨文件/同 Sheet 冲突分析，**不是 UNIQUE 约束**，同一 key 可有多行（业务允许多笔时 warning）。
- 转出产品名通过 `trust_product_aliases` 优先匹配，再精确匹配 `trust_products.name`。
- 关联表：`issuance_import_runs`、`issuance_import_sheet_runs`（审计，另见 TODO 扩写）。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线表 | `db/modules/issuance/schema.sql` |
| — | migration_type | `db/migrations/20250620_issuance_migration_type.sql` |
| 2026-07-19 | 全列导入：拟转入 + 结算/首期业务列 | `db/migrations/20260719_issuance_full_columns.sql` |

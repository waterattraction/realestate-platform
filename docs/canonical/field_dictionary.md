# Canonical Field Dictionary

全系统 **Canonical Field** 定义。新增 Excel、DB、API、BI、AI 字段前必须先查本表；已存在则 **必须复用**，不得新增同义字段。

> 当前 REST API 多使用 `snake_case`；**开放 API / BI / Agent 预留** 使用 `camelCase` API 列。

## 字段总表

| Canonical Field | 中文名 | DB 字段 | Excel 别名 | API 字段 | AI/BI 语义 | 备注 |
|-----------------|--------|---------|------------|----------|------------|------|
| `trust_product_id` | 信托产品 ID | `trust_products.id` 及各表 FK | —（导入参数） | `trustProductId` | Trust Product Identifier | 产品维度主键 |
| `trust_product_name` | 信托产品名称 | `*.trust_product_name` | — | `trustProductName` | Trust Product Name | 导入快照冗余 |
| `from_trust_product_id` | 转出产品 ID | `from_trust_product_id` | — | `fromTrustProductId` | Source Trust Product Id | 发行迁移 |
| `from_trust_product_name` | 转出信托产品 | `from_trust_product_name` | 见 alias_dictionary | `fromTrustProductName` | Source Trust Product Name | 经 alias 表解析 |
| `trust_asset_id` | 底层资产 ID | `trust_assets.id` 及 FK | — | `trustAssetId` | Trust Asset Identifier | 监控/还款/逾期/风险 |
| `custody_asset_code` | **托管房源主体号** | `custody_asset_code` | 房源编码/托管房源号等 | `custodyAssetCode` | Custody Asset Code / 托管房源号 | **跨模块主体标识** |
| `source_asset_code` | **资产分笔号** | `source_asset_code` | 资产编号(房源)等 | `sourceAssetCode` | Source Asset Code / 资产分笔号 | 分笔粒度 |
| `asset_code` | 资产编号（历史） | `asset_code` | **非推荐 Excel 别名** | `assetCode` | Legacy Asset Code | **历史兼容，勿扩散** |
| `business_asset_key` | 发行资产标识 | `business_asset_key` | —（计算） | `businessAssetKey` | Issuance Conflict Key | **不唯一**，非 UNIQUE |
| `issue_date` | **发行日期** | `issue_date` | —（导入参数） | `issueDate` | Issuance Date | **仅发行模块** |
| `data_date` | 快照日期 | `data_date` | 统计日期 | `dataDate` | Snapshot Date | 监控/还款/逾期/风险；**不用于发行** |
| `repayment_date` | **实际回款日期** | `repayment_date` | 还款日期等 | `repaymentDate` | Repayment Date | 还款业务日 |
| `source_file_name` | 来源文件名 | `source_file_name` | 文件名/所属文件名称 | `sourceFileName` | Source File Name | 覆盖 scope |
| `source_sheet_name` | 来源 Sheet | `source_sheet_name` | 所属Sheet名称 | `sourceSheetName` | Source Sheet Name | 覆盖 scope |
| `source_row_number` | 来源行号 | `source_row_number` | — | `sourceRowNumber` | Source Row Number | 发行追溯 |
| `migration_type` | 迁移类型 | `migration_type` | 迁移类型等 | `migrationType` | Migration Type | 见 enumerations |
| `asset_transfer_discount_rate` | 资产转让折扣率 | `asset_transfer_discount_rate` | 资产转让折扣率(%)等 | `assetTransferDiscountRate` | Transfer Discount Rate | 0~1 小数 |
| `receivable_contract_amount` | 应收账款合同金额 | `receivable_contract_amount` | 实际成交价等 | `receivableContractAmount` | Receivable Contract Amount | 发行必填 |
| `receivable_transfer_amount` | 应收账款转让价款 | `receivable_transfer_amount` | 应收账款转让价款 | `receivableTransferAmount` | Receivable Transfer Amount | 发行必填 |
| `total_rent_withholding_amount` | 总租金代扣金额 | `total_rent_withholding_amount` | 总租金代扣金额/租金代扣金额 | `totalRentWithholdingAmount` | Total Rent Withholding | |
| `first_rent_withholding_date` | 首次租金代扣日 | `first_rent_withholding_date` | 首次付款日期等 | `firstRentWithholdingDate` | First Rent Withholding Date | |
| `city` | 城市 | `city` | 所属城市/所属区域/城市 | `city` | City | 北京/上海等 |
| `risk_level` | 风险等级 | `risk_level` | — | `riskLevel` | Risk Level | DB 现用 A/B/C/D/ES；见 enumerations |
| `risk_score` | 风险评分 | `risk_score` | — | `riskScore` | Risk Score | 整数分值 |
| `overdue_days` | 逾期天数 | `overdue_days` | — | `overdueDays` | Overdue Days | 监控计算 |
| `remaining_amount` | 剩余还款金额 | `remaining_amount` | 剩余还款金额等 | `remainingAmount` | Remaining Balance | 监控 |
| `repaid_amount` | 已还款金额 | `repaid_amount` | 已还款金额 | `repaidAmount` | Repaid Amount | 监控 |
| `actual_repayment_amount` | 当期实际还款金额 | `actual_repayment_amount` | 当期实际还款金额 | `actualRepaymentAmount` | Actual Repayment Amount | 还款 |
| `period_no` | 还款期数 | `period_no` | 还款期数 | `periodNo` | Period Number | 防重维度 |

## 关键语义（强制）

| Canonical Field | 定义要点 |
|-----------------|----------|
| `custody_asset_code` | **托管房源主体号**；跨发行/监控/还款/逾期/风险 |
| `source_asset_code` | **资产分笔号**；如 `101127075900-001` |
| `asset_code` | **历史 DB 字段**；`UNIQUE(product, asset_code)` 仍存在；新逻辑勿扩散 |
| `business_asset_key` | `{trust_product_id}:{issue_date}:{custody_asset_code}`；**不唯一** |
| `issue_date` | **发行日期**；发行模块唯一时间维度 |
| `data_date` | 监控/还款/逾期/风险快照日；**禁止用于发行** |
| `repayment_date` | **实际回款日期**；金额核对应用此字段，非 `data_date` |

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.5 首批 30 字段 |

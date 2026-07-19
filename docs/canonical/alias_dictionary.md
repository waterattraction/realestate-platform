# Alias Dictionary

集中管理 **Excel 列名、业务口语、历史字段别名** → **Canonical Field** 映射。

> **`asset_code` 是历史 DB 字段，不是推荐 Excel Alias。** 新 Excel 应使用 `custody_asset_code` / `source_asset_code` 对应列名。

## 别名总表

| Alias | Canonical Field | 来源场景 | 是否推荐继续使用 | 说明 |
|-------|-----------------|----------|------------------|------|
| 房源编号 | `custody_asset_code` | 发行/监控 Excel | 是 | 归托管房源主体号 |
| 房源编码 | `custody_asset_code` | 发行/监控 Excel | 是 | 同义 |
| 托管房源号 | `custody_asset_code` | 发行/监控/还款 | **推荐** | 标准口语 |
| 托管房源编码 | `custody_asset_code` | 发行 Excel | 是 | |
| 资产编号 | `source_asset_code` | 发行 Excel | 是 | 分笔号语境 |
| 资产编号(房源) | `source_asset_code` | 发行 Excel | **推荐** | 标准列名 |
| 资产分笔号 | `source_asset_code` | 业务口语 | 是 | |
| 当前信托计划（已发行） | `from_trust_product_name` | 发行 Excel | 是 | 经 `trust_product_aliases` 解析 |
| 原信托计划 | `from_trust_product_name` | 发行 Excel | 是 | |
| 转出信托计划 | `from_trust_product_name` | 发行 Excel | 是 | |
| 拟转入计划（未发行） | `planned_trust_product_name` | 发行 Excel | 是 | 独立字段，不再映射转出产品 |
| 资产转让折扣率(%) | `asset_transfer_discount_rate` | 发行 Excel | 是 | |
| 资产转让折扣率（数值）(%) | `asset_transfer_discount_rate` | 发行 Excel | **推荐** | 美润1号等 |
| 资产转让折扣率(数值)(%) | `asset_transfer_discount_rate` | 发行 Excel | 是 | 无空格变体 |
| 总租金代扣金额 | `total_rent_withholding_amount` | 发行 Excel | **推荐** | |
| 租金代扣金额 | `total_rent_withholding_amount` | 发行 Excel | 是 | 简写 |
| 代扣金额 | `total_rent_withholding_amount` | 发行 Excel | 是 | 结算底表短名 |
| 贝壳已租金代扣金额合计 | `rent_withheld_amount_before_pooling` | 发行 Excel | 是 | |
| 已租金代扣金额合计-封包前 | `rent_withheld_amount_before_pooling` | 发行 Excel | **推荐** | |
| 预计代扣周期-最初 | `initial_expected_withholding_cycle` | 发行 Excel | 是 | |
| 预计代扣支付周期-最初 | `initial_expected_withholding_cycle` | 发行 Excel | **推荐** | |
| 基础交易合同名称 | `contract_name` | 发行 Excel | 是 | 美润首期 |
| 品牌 | `brand` | 发行 Excel | 是 | |
| 产品风格 | `product_style` | 发行 Excel | 是 | |
| 房屋状态 | `property_status` | 发行 Excel | 是 | |
| 预计最后一期 租金支付日-最初 | `expected_last_rent_payment_date_initial` | 发行 Excel | 是 | |
| 约定还款期数 | `agreed_repayment_periods` | 发行 Excel | 是 | |
| 每期应付金额 | `installment_payable_amount` | 发行 Excel | 是 | |
| 已代扣未付款 | `withheld_unpaid_amount` | 发行 Excel | 是 | |
| 已代扣已回款（新） | `withheld_repaid_amount` | 发行 Excel | 是 | |
| 已代扣已回款 | `withheld_repaid_amount` | 发行 Excel | 是 | |
| 已转让收款合计 | `transferred_receipt_total` | 发行 Excel | 是 | |
| 已租金代扣到账合计 | `rent_withholding_received_total` | 发行 Excel | 是 | |
| 原始债权人 | `original_creditor` | 发行 Excel | 是 | |
| 预计应收账款到期日（日期） | `expected_receivable_due_date` | 发行 Excel | 是 | |
| 预计应收账款到期日 | `expected_receivable_due_date` | 发行 Excel | 是 | |
| 首次付款日期 | `first_rent_withholding_date` | 发行 Excel | 是 | |
| 首次租金代扣日期 | `first_rent_withholding_date` | 发行 Excel | **推荐** | |
| 所属城市 | `city` | 发行 Excel | 是 | |
| 所属区域 | `city` | 发行 Excel | 是 | 归城市 |
| 城市 | `city` | 通用 | 是 | |
| 还款日期 | `repayment_date` | 还款 Excel | 是 | |
| 实际还款日期 | `repayment_date` | 还款 Excel | **推荐** | |
| 当期实际还款金额 | `actual_repayment_amount` | 还款 Excel | **推荐** | |
| 还款期数 | `period_no` | 还款 Excel | **推荐** | |
| 统计日期 | `data_date` | 监控/还款 Excel | 是 | 非发行 |
| 所属文件名称 | `source_file_name` | 监控 Excel | 是 | |
| 所属Sheet名称 | `source_sheet_name` | 监控 Excel | 是 | |
| 实际成交价 | `receivable_contract_amount` | 发行 Excel | 是 | |
| 应收账款转让价款 | `receivable_transfer_amount` | 发行 Excel | 是 | |
| 迁移类型 | `migration_type` | 发行 Excel | 是 | |
| 剩余还款金额 | `remaining_amount` | 监控 Excel | 是 | |
| 已还款金额 | `repaid_amount` | 监控 Excel | 是 | |

## 历史字段（非推荐 Excel Alias）

| 名称 | 类型 | 说明 |
|------|------|------|
| `asset_code` | DB 列 `trust_assets.asset_code` | 历史兼容；**勿作为新 Excel 列别名** |
| 资产编号（无括号） | 歧义 | 可能指 `custody_asset_code` 或 `source_asset_code`；应使用明确列名 |

## 维护规则

1. 新 Excel 列名 **必须先登记本表**，再写入 `issuance_cleanse` / `assetinfo_cleanse` 的 `COL_ALIASES`
2. 同一 Alias 只映射一个 Canonical Field
3. 废弃 Alias 标「否」，保留追溯

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.5 首批别名 |
| 2026-07 | 发行 6 文件全列：拟转入独立字段；代扣/合同/结算底表别名与新业务列 |

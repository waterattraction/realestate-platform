# 数据术语表

Canonical 字段名以英文 snake_case 为准；中文仅作 Excel 别名或展示用语。

| 中文术语 | Canonical / DB 字段 | 禁止混用为 | 说明 |
|----------|----------------------|-----------|------|
| 托管房源号 / 托管房源主体号 | `custody_asset_code` | `asset_code`（新逻辑） | 跨发行、监控、还款、逾期、风险识别房源主体；12 位数字为主 |
| 房源编码 / 房源编号 | `custody_asset_code` | 独立字段名 | Excel 别名，映射到 `custody_asset_code` |
| 资产分笔号 / 资产编号(房源) | `source_asset_code` | `custody_asset_code` | 分笔粒度，如 `101127075900-001` |
| 资产主编号 | `asset_code` | 唯一业务键 | 信托号左 12 位；**同一产品可对应多个托管编号**（多行 trust_assets） |
| 资产编号（历史展示） | `asset_code` | custody 锚点 | 与主编号同列；新逻辑 upsert 以 `custody_asset_code` 为首要键 |
| 发行资产标识 | `business_asset_key` | 主键 / UNIQUE | `{trust_product_id}:{issue_date}:{custody_asset_code}`；**非唯一约束** |
| 发行日 | `issue_date` | `data_date` | **仅发行模块**业务时间维度 |
| 快照日期 / 统计日期 | `data_date` | `issue_date` | 监控、还款、逾期、风险快照维度 |
| 还款日期 / 还款业务日 | `repayment_date` | `data_date`（金额核对） | 单笔还款实际发生日 |
| 信托产品 ID | `trust_product_id` | — | 产品维度外键 |
| 信托产品名称 | `trust_product_name` | — | 冗余展示字段，导入时快照 |
| 底层资产 ID | `trust_asset_id` | — | `trust_assets.id`，监控/还款/逾期/风险 FK |
| 迁移类型 | `migration_type` | — | 发行：`new_issuance` / `transfer` 等 |
| 转出信托产品 | `from_trust_product_name` | — | 发行迁移来源；可经 `trust_product_aliases` 解析 |
| 单一信托 | `trust_product_aliases.alias_name` | 产品正式名 | 别名，映射至 `trust_products.name`（如美润1号） |
| 资产转让折扣率 | `asset_transfer_discount_rate` | 百分数字面量 | 库内 0~1 小数；Excel 可为 0.83 或 83 |
| 应收账款合同金额 | `receivable_contract_amount` | — | 发行必填金额 |
| 应收账款转让价款 | `receivable_transfer_amount` | — | 发行必填金额 |
| 剩余还款金额 | `remaining_amount` | — | 监控快照字段 |
| 当期实际还款金额 | `actual_repayment_amount` | — | 还款明细金额 |
| 还款期数 | `period_no` | — | 还款明细；V1 导入可能为空 |

## 模块时间维度速查

| 模块 | 时间字段 | 不用 |
|------|----------|------|
| 发行 | `issue_date` | `data_date` |
| 监控 | `data_date` | `issue_date` |
| 还款 | `repayment_date`（业务日）；`data_date`（遗留） | 用 `data_date` 做金额核对 |
| 逾期 / 风险 | `data_date` | — |

# 发行资产明细 Excel 导入标准

## 1. Sheet 类型

| sheet_type | 中文名 | 代码入口 |
|------------|--------|----------|
| `issuance_asset` | 发行资产明细 | `issuance_upload.classify_issuance_sheet` |

## 2. 识别规则

**文件名关键词：** 发行资产、已发行、入池、基础资产清单、房源明细

**Sheet 名关键词：** 发行、入池、合同、资产明细

**表头核心列（缺一不可）：**

- `custody_asset_code` 对应列（房源编码等）
- `receivable_contract_amount`
- `receivable_transfer_amount`

**互斥：** 若同时像监控表或还款表 → `ambiguous_sheet_type` → failed

## 3. 必填列

| 语义字段 | DB 字段 | Excel 主列名 | 缺失时 |
|----------|---------|-------------|--------|
| 托管房源号 | `custody_asset_code` | 房源编码 | 行 failed |
| 应收账款合同金额 | `receivable_contract_amount` | 实际成交价（应收账款合同金额） | 行 failed |
| 应收账款转让价款 | `receivable_transfer_amount` | 应收账款转让价款 | 行 failed |

**导入参数必填：** `trust_product_id`、`issue_date`（**非 Excel 列**）

## 4. 可选列

见第 9 节字段映射总表。

## 5. 核心别名列（跨模块统一）

| 语义字段 | 别名（优先级从高到低） |
|----------|------------------------|
| `custody_asset_code` | 房源编码、房源编号、托管房源编码、托管房源号 |
| `source_asset_code` | （发行模块不使用；见还款/监控） | 
| `asset_transfer_discount_rate` | 资产转让折扣率(%)、资产转让折扣率（数值）(%)、资产转让折扣率(数值)(%)、资产转让折扣率 |
| `total_rent_withholding_amount` | 总租金代扣金额、租金代扣金额 |
| `first_rent_withholding_date` | 首次付款日期、首次租金代扣日期 |
| `city` | 所属城市、所属区域、城市 |
| `from_trust_product_name` | 当前信托计划（已发行）、原信托计划、转出信托计划、当前信托计划、拟转入计划（未发行） |

完整别名见 `issuance_cleanse.COL_ALIASES`。

## 6. 数据类型与清洗

| 语义字段 | 类型 | 清洗 | 示例 |
|----------|------|------|------|
| 金额 | NUMERIC | `to_numeric_value` | `1000000` |
| 比例 | 0~1 | `to_rate_value`：0.83→0.83；83→0.83 | `0.83` |
| 日期 | DATE | `to_optional_date` | `2026-04-28` |
| 字符串 | TEXT | trim | |
| Excel 错误 | — | `#NAME?` 等 → 置空 + warning | |

**城市：** 京北/京南→北京；上海；地址区县回退（见 `resolve_city`）。

**转出产品：** 逗号/顿号多 token，首个命中；先 `trust_product_aliases`，再 `trust_products.name`。

## 7. Warning / Failed 规则

| 条件 | 级别 | 说明 |
|------|------|------|
| 缺核心列 / 无法识别 Sheet | failed | 不可导入 |
| 缺托管号 / 金额无效 | failed | 行级错误 |
| Excel 错误值 | warning | 可选字段置空 |
| 转出产品未匹配 | warning | `from_trust_product_*` 为空 |
| 城市无法识别 | warning | `city_blank_count` |
| 折扣率为空（列已映射） | warning | `asset_transfer_discount_rate_blank_count` |
| 同 Sheet 同 business_asset_key 多行 | warning | 不阻止 |
| 跨文件同 key 金额冲突 | needs_confirm | 需人工确认 |
| 同 scope 已有数据 | overwrite | 覆盖导入 |

## 8. 导入 Action

| action | 触发条件 | 用户操作 |
|--------|----------|----------|
| `import` | 新 scope，无冲突 | 直接导入 |
| `overwrite` | 同 `product+issue_date+file+sheet` 已有行 | 确认覆盖 |
| `needs_confirm` | 跨文件重复 key 或金额冲突 / 完全重复 | 勾选 confirm 后导入 |
| `failed` | 解析错误 / 未确认 | 不可导入 |

> 发行模块**无 `data_date`**；时间维度仅为用户指定的 `issue_date`。

## 9. 字段映射总表

| Excel 列名 / 语义 | 别名 | DB 字段 | 类型 | 必填 | 清洗规则 | 失败规则 |
|-------------------|------|---------|------|:----:|----------|----------|
| 房源编码 | 房源编号、托管房源编码、托管房源号 | `custody_asset_code` | 字符串 | 是 | `clean_custody_code` | 空→行失败 |
| 实际成交价（应收账款合同金额） | 应收账款合同金额 | `receivable_contract_amount` | 金额 | 是 | `to_optional_amount` | 无效→行失败 |
| 应收账款转让价款 | — | `receivable_transfer_amount` | 金额 | 是 | 同上 | 同上 |
| 资产转让折扣率（数值）(%) | 见第 5 节 | `asset_transfer_discount_rate` | 比例 | 否 | `to_rate_value` | — |
| 总租金代扣金额 | 租金代扣金额 | `total_rent_withholding_amount` | 金额 | 否 | `to_numeric` | 错误值→空 |
| 首次付款日期 | 首次租金代扣日期 | `first_rent_withholding_date` | 日期 | 否 | `to_optional_date` | — |
| 所属城市 | 所属区域、城市 | `city` | 字符串 | 否 | `resolve_city` | 空→warning |
| 当前信托计划（已发行） | 原信托计划、转出信托计划… | `from_trust_product_name` | 字符串 | 否 | alias 解析 | 未匹配→warning |
| 迁移类型 | 资产迁移类型 | `migration_type` | 枚举 | 否 | `resolve_migration_type` | 未知→warning+transfer |

（其余列见 `issuance_cleanse.COL_ALIASES`，TODO 补全逐列行）

## 10. 示例值

| custody_asset_code | issue_date（参数） | receivable_contract_amount | asset_transfer_discount_rate |
|--------------------|-------------------|---------------------------|---------------------------|
| `101128210944` | `2026-03-20` | `1000000.00` | `0.83` |

## 11. 对应代码

| 文件 | 职责 |
|------|------|
| `backend/app/issuance_cleanse.py` | `COL_ALIASES`、清洗、城市、迁移类型 |
| `backend/app/issuance_upload.py` | 预检、导入、scope DELETE |

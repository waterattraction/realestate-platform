# 资产监控快照 Excel 导入标准

对齐模版：`excel文件/资产监控表模版.xlsx`（17 列）。

## 1. Sheet 类型

| sheet_type | 中文名 | 代码入口 |
|------------|--------|----------|
| `asset_monitor` | 资产监控快照 | `assetinfo_upload` |

## 2. 识别规则

**文件名关键词：** 资产监控

**Sheet 名关键词：** 资产监控、监控表、监控快照

**表头标记列（`MONITOR_FIXED_COLUMNS` + 剩余还款）：**

- `统计日期`
- `初始受让金额`
- `已还款金额`
- `剩余还款金额` / `剩余应还款余额`

**与还款表互斥：** 名称与表头冲突 → `ambiguous_sheet_type`

## 3. 模版列 vs 系统字段

| 模版列 | DB 字段 | 导入 | 导出 |
|--------|---------|:----:|:----:|
| 资产包编号 | `asset_pool_code` | ✅ | ✅ |
| 资产编号(房源) | `source_asset_code` | ✅ | ✅ |
| 装修服务商 | `renovation_vendor` | ✅ | ✅ |
| 统计日期 | `data_date` | ✅ | ✅ |
| 初始受让金额 | `initial_transfer_amount` | ✅ | ✅ |
| 已还款金额 | `repaid_amount` | ✅ | ✅ |
| 剩余还款金额 | `remaining_amount` | ✅ | ✅ |
| 资产状态 | `asset_status` | ✅ | ✅ |
| 最后一期装修款付款时间 | `last_renovation_payment_date` | ✅ | ✅ |
| 小区名称 | `community_name` | ✅ | ✅ |
| 城市 | `city` | ✅ | ✅ |
| 收房合同编码 | `collection_contract_code` | ✅ | ✅ |
| 托管协议签署日期 | `custody_agreement_sign_date` | ✅ | ✅ |
| 收房合同签约年数 | `collection_contract_years` | ✅ | ✅ |
| 业主代码 | `owner_code` | ✅ | ✅ |
| 代扣比例 | `withholding_ratio` | ✅ | ✅ |
| 实际出房月租金 | `actual_monthly_rent` | ✅ | ✅ |

系统另有计算/关联列（不在披露模版内，列表页仍展示）：`overdue_days`、`risk_*`、发行折扣率等。

> 还款披露模版中的「当期逾期天数」**不从还款 Excel 导入**；导出还款明细时从本表最新快照 `overdue_days` 取值。

## 4. 必填 / 可选

**必填：** 统计日期、初始受让金额、已还款金额、剩余还款金额；托管房源编码或资产编号至少其一。

**可选：** 上表模版扩展列 + 托管房源编码（可从分笔号推导）。

## 5. 导出

`GET /assetinfo/monitor-records/export` → 按监控模版 17 列导出 Sheet「资产监控表」。

## 6. 对应代码

| 文件 | 职责 |
|------|------|
| `backend/app/assetinfo_templates.py` | `MONITOR_TEMPLATE_COLUMNS` |
| `backend/app/assetinfo_upload.py` | 预检 / 导入 / 导出 |
| `backend/app/assetinfo_cleanse.py` | `MONITOR_FIXED_COLUMNS`、别名 |
| `db/migrations/20260720_monitor_repayment_template_columns.sql` | 模版扩展列 |

# 资产监控快照 Excel 导入标准

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

## 3. 必填列

| 语义字段 | DB 字段 | Excel 列名 | 缺失时 |
|----------|---------|-----------|--------|
| 监控快照日期 | `data_date` | 统计日期 | failed |
| 托管房源号 | `custody_asset_code` | 托管房源编码 | failed |
| 初始受让金额 | `initial_transfer_amount` | 初始受让金额 | 行/Sheet failed |
| 已还款金额 | `repaid_amount` | 已还款金额 | 同上 |
| 剩余还款金额 | `remaining_amount` | 剩余还款金额 / 剩余应还款余额 | 同上 |

## 4. 可选列

| 语义字段 | DB 字段 | Excel 列名 |
|----------|---------|-----------|
| 资产分笔号 | `source_asset_code` / `asset_code` | 资产编号(房源) |
| 信托计划过滤 | — | 当前信托计划（已发行） |

## 5. 核心别名列

| 语义字段 | 别名 |
|----------|------|
| `custody_asset_code` | 托管房源编码（监控）；与发行「房源编码/托管房源号」同语义 |
| `source_asset_code` | 资产编号(房源) |
| `remaining_amount` | 剩余还款金额、剩余应还款余额 |

## 6. 数据类型与清洗

| 类型 | 规则 |
|------|------|
| 日期 | `统计日期` → `data_date`（**监控快照日期**） |
| 金额 | `to_numeric_value`，默认非负 |
| 托管号 | `clean_custody_code` |
| 分笔号 | `clean_asset_code`；可推导 custody |

## 7. Warning / Failed 规则

| 条件 | 级别 |
|------|------|
| 缺监控核心列 | failed |
| 同 Sheet 同房源多行 | warning |
| 一主编号多托管 | 正常：同一 `asset_code` 可对应多行、多个 `custody_asset_code` |
| 跨批次重复 | needs_confirm / overwrite（见 precheck） |
| Sheet 名不含监控关键词 | failed |

## 8. 导入 Action

| action | 说明 |
|--------|------|
| `import` | 新批次 |
| `overwrite` | 同 scope 覆盖 |
| `needs_confirm` | 重复需确认 |
| `skip` | 与库内完全一致可跳过 |
| `failed` / `reject` | 不可导入 |

## 9. 字段映射总表

| Excel 列名 | 别名 | DB 字段 | 类型 | 必填 | 清洗规则 | 失败规则 |
|------------|------|---------|------|:----:|----------|----------|
| 统计日期 | — | `data_date` | DATE | 是 | `to_date_value` | 解析失败→failed |
| 托管房源编码 | 托管房源编号 | `custody_asset_code` | 字符串 | 是 | `to_custody_code` | 缺失→failed |
| 资产编号(房源) | — | `source_asset_code` / `asset_code` | 字符串 | 视模板 | `clean_asset_code` | TODO |
| 初始受让金额 | — | `initial_transfer_amount` | 金额 | 是 | `to_numeric` | |
| 已还款金额 | — | `repaid_amount` | 金额 | 是 | `to_numeric` | |
| 剩余还款金额 | 剩余应还款余额 | `remaining_amount` | 金额 | 是 | `to_numeric` | |
| 当前信托计划（已发行） | — | 过滤用 alias | 字符串 | 否 | `filter_alias` | |

配置种子：`db/modules/assetinfo/seed_mapping.sql`（Sheet `2更新的资产数据表`）

## 10. 示例值

| data_date | custody_asset_code | initial_transfer_amount | remaining_amount |
|-----------|-------------------|------------------------|------------------|
| `2026-06-12` | `101127075900` | `500000.00` | `120000.00` |

## 11. 对应代码

| 文件 | 职责 |
|------|------|
| `backend/app/assetinfo_upload.py` | `COL_*`、`precheck_monitor_sheet` |
| `backend/app/assetinfo_cleanse.py` | `MONITOR_FIXED_COLUMNS`、清洗 |

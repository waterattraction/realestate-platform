# 还款明细 Excel 导入标准

## 1. Sheet 类型

| sheet_type | 中文名 | 代码入口 |
|------------|--------|----------|
| `repayment_detail` | 还款明细 | `ingestion_upload` |

## 2. 识别规则

**文件名关键词：** 还款明细

**Sheet 名关键词：** 还款明细、已还款、还款披露

**跳过：** Sheet 名含「回款计划」→ skip

**表头必填列：**

- `托管房源编码` / `托管房源编号` → `custody_asset_code`
- `资产编号(房源)` → `source_asset_code`
- `当期实际还款金额`
- `还款日期` / `当期还款日期` → `repayment_date`

**日期：** 优先从 Sheet 名/产品名解析 fallback date（`ingestion_date_rules`）

## 3. 必填列

| 语义字段 | DB 字段 | Excel 列名 | 缺失时 |
|----------|---------|-----------|--------|
| 托管房源号 | `custody_asset_code` | 托管房源编码、托管房源编号 | Sheet failed |
| 资产分笔号 | `source_asset_code` | 资产编号(房源) | Sheet failed |
| 还款金额 | `actual_repayment_amount` | 当期实际还款金额 | 行 failed |
| 还款业务日 | `repayment_date` | 还款日期、当期还款日期 | 行 failed |

## 4. 可选列

| 语义字段 | DB 字段 | Excel 列名 |
|----------|---------|-----------|
| 还款期数 | `period_no` | 还款期数 |
| 来源文件 | `source_file_name` | 所属文件名称 |
| 来源 Sheet | `source_sheet_name` | 所属Sheet名称 |

## 5. 核心别名列

| 语义字段 | 别名 |
|----------|------|
| `custody_asset_code` | 托管房源编码、托管房源编号；与「房源编码/托管房源号」同语义 |
| `source_asset_code` | 资产编号(房源)、资产分笔号 |
| `repayment_date` | 还款日期、当期还款日期 |

## 6. 数据类型与清洗

| 字段 | 说明 |
|------|------|
| `repayment_date` | **还款业务日期** |
| `data_date` | 导入时写入，常与 `repayment_date` 相同；**历史遗留，不用于新核对逻辑** |
| 金额 | `to_numeric_value` |
| 期数 | `clean_period_no` |

防重指纹：`custody + source + repayment_date + amount + period_no`

## 7. Warning / Failed 规则

| 条件 | 级别 |
|------|------|
| 缺托管/资产编号列 | failed |
| 无法解析 repayment_date | 行 failed |
| period_no 全缺失 | warning |
| Sheet 内完全重复 | reject / warning |
| 跨文件 overlap | needs_confirm |
| 与库内完全一致 | skip |

## 8. 导入 Action

| action | 说明 |
|--------|------|
| `import` | 新 scope |
| `overwrite` | 同 file+sheet 覆盖 |
| `needs_confirm` | 跨文件疑似重复 |
| `skip` | 数据完全一致 |
| `reject` / `failed` | 不可导入 |

## 9. 字段映射总表

| Excel 列名 | 别名 | DB 字段 | 类型 | 必填 | 清洗规则 | 失败规则 |
|------------|------|---------|------|:----:|----------|----------|
| 托管房源编码 | 托管房源编号 | `custody_asset_code` | 字符串 | 是 | `to_custody_code` | 缺列→Sheet失败 |
| 资产编号(房源) | 资产分笔号 | `source_asset_code` | 字符串 | 是 | `clean_asset_code` | 缺列→Sheet失败 |
| 当期实际还款金额 | — | `actual_repayment_amount` | 金额 | 是 | `to_numeric` | 无效→行失败 |
| 还款日期 | 当期还款日期 | `repayment_date` | DATE | 是 | 日期解析 | 失败→行失败 |
| 还款期数 | — | `period_no` | 字符串 | 否 | `clean_period_no` | — |
| （导入逻辑写入） | — | `data_date` | DATE | 是 | 同 repayment_date | 遗留字段 |

配置种子：`db/modules/ingestion/seed_mapping.sql`（Sheet `1全量还款明细汇总`）

## 10. 示例值

| custody_asset_code | source_asset_code | repayment_date | actual_repayment_amount | period_no |
|--------------------|-------------------|----------------|------------------------|-----------|
| `101127075900` | `101127075900-001` | `2026-05-15` | `5000.00` | `3` |

## 11. 对应代码

| 文件 | 职责 |
|------|------|
| `backend/app/ingestion_upload.py` | `COL_CUSTODY`、`COL_ASSET_CODE`、`precheck_repayment_sheet` |
| `backend/app/ingestion_cleanse.py` | 清洗、防重 |

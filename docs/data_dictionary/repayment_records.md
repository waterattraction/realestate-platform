# 还款明细（`trust_repayment_detail_records`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 还款明细 |
| 表英文名 | `trust_repayment_detail_records` |
| Schema 来源 | `db/modules/overdue/schema.sql` + `db/migrations/20250302_asset_code_semantics_v2.sql` |
| 主键 | `id` |
| 业务唯一标识 | 业务上：托管房源 + 分笔 + `repayment_date` + 金额 + `period_no`（防重） |

## 表用途

记录信托产品下各底层资产的逐笔还款明细，来源于还款 Excel 导入。用于监控汇总、金额核对与逾期分析。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | `/assetinfo` 还款 Sheet 导入 INSERT |
| 更新 | 同 scope 覆盖（DELETE + INSERT） |
| 冻结 | 历史明细一般不改 |
| 删除/归档 | scope 按文件+Sheet；ops 去重 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入 | 产品维度 | FK |
| trust_asset_id | 底层资产 ID | BIGINT | 是 | 导入 upsert | 关联资产 | FK |
| asset_code | 资产编号（历史） | VARCHAR(64) | 是 | 导入 | **历史字段** | |
| data_date | 快照日期（遗留） | DATE | 是 | 导入逻辑 | **历史遗留** | 见注意事项 |
| period_no | 还款期数 | VARCHAR(32) | 否 | Excel | 防重维度 | V1 可能全 NULL |
| actual_repayment_amount | 当期实际还款金额 | NUMERIC(18,2) | 是 | Excel | 还款金额 | ≥ 0 |
| repayment_date | 还款业务日期 | DATE | 否 | Excel | **单笔还款发生日** | 业务主日期 |
| source_file_name | 来源文件名 | VARCHAR(500) | 否 | 系统 | 覆盖 scope | |
| source_sheet_name | 来源 Sheet | VARCHAR(200) | 否 | 系统 | 覆盖 scope | |
| synced_at | 同步时间 | TIMESTAMPTZ | 是 | 系统 | | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |
| custody_asset_code | 托管房源号 | VARCHAR(64) | 否 | Excel | 主体识别 | V2 |
| source_asset_code | 资产分笔号 | VARCHAR(64) | 否 | Excel | 分笔识别 | V2 |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_trust_repayment_product_date` | `trust_product_id, data_date DESC` | 按产品+日期 |
| `idx_trust_repayment_asset_date` | `trust_asset_id, data_date` | 按资产 |
| `idx_repayment_custody_source` | `trust_product_id, repayment_date, custody_asset_code, source_asset_code` | V2 查询 |
| `idx_repayment_import_scope` | scope 列 | 导入覆盖 |

## 上游来源

- 还款明细 Excel（`/assetinfo`）
- 列：`托管房源编码/编号`、`资产编号(房源)`、`还款日期`、`当期实际还款金额`

## 下游使用模块

监控汇总重算、金额核对、逾期、Dashboard

## 数据质量规则

- 防重：`custody + source + repayment_date + amount + period_no`
- 缺 `repayment_date` → 行级 failed
- 缺托管/资产编号列 → Sheet failed

## 注意事项

- **`repayment_date` 是还款业务日期**（Excel「还款日期」/「当期还款日期」），表示该笔还款实际发生日。
- **`data_date` 是历史遗留字段**：当前导入逻辑中常与 `repayment_date` 同步写入，**不应再用于金额核对或新业务逻辑的时间维度**；金额核对应以 `repayment_date` 及监控的 `data_date` 为准（TODO：核对规则文档化）。
- `asset_code` 历史兼容；优先使用 `custody_asset_code` + `source_asset_code`。
- V1 导入 `period_no` 可能全为 NULL，跨文件防重需注意。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/overdue/schema.sql` |
| — | custody/source | `db/migrations/20250302_asset_code_semantics_v2.sql` |

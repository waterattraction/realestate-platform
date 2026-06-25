# 资产监控快照（`trust_asset_monitor_records`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 资产监控快照 |
| 表英文名 | `trust_asset_monitor_records` |
| Schema 来源 | `db/modules/overdue/schema.sql` + `db/modules/risk/schema.sql` + migrations |
| 主键 | `id` |
| 业务唯一标识 | TODO：同一 `(trust_product_id, data_date, trust_asset_id)` 应唯一；历史存在重复需清理 |

## 表用途

按 **`data_date`（监控快照日期）** 记录信托产品下各底层资产的监控指标（受让、已还、剩余、逾期天数等），来源于资产监控 Excel 导入。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | `/ingestion` 监控 Sheet 导入 |
| 更新 | 同批次覆盖；逾期天数等可重算 |
| 冻结 | 历史快照一般不修改 |
| 删除/归档 | scope 覆盖；ops 去重脚本 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 导入 | 产品维度 | FK |
| trust_asset_id | 底层资产 ID | BIGINT | 是 | 导入 upsert | 关联 `trust_assets` | FK |
| asset_code | 资产编号（历史） | VARCHAR(64) | 是 | 导入 | **历史字段** | 与 trust_assets 一致 |
| data_date | 监控快照日期 | DATE | 是 | Excel「统计日期」 | **本表核心时间维度** | 非 issue_date |
| initial_transfer_amount | 初始受让金额 | NUMERIC(18,2) | 是 | Excel | 监控指标 | |
| repaid_amount | 已还款金额 | NUMERIC(18,2) | 是 | Excel | 监控指标 | |
| remaining_amount | 剩余还款金额 | NUMERIC(18,2) | 是 | Excel | 监控指标 | |
| overdue_days | 逾期天数 | INT | 是 | 计算/导入 | 逾期展示 | 默认 0 |
| last_payment_date | 最近还款日 | DATE | 否 | 计算 | TODO | |
| max_payment_date | 最大还款日 | DATE | 否 | 计算 | TODO | |
| source_file_name | 来源文件名 | VARCHAR(500) | 否 | 系统 | 追溯 | |
| source_sheet_name | 来源 Sheet | VARCHAR(200) | 否 | 系统 | 追溯 | |
| synced_at | 同步时间 | TIMESTAMPTZ | 是 | 系统 | 导入时间 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | | |
| custody_asset_code | 托管房源号 | VARCHAR(64) | 否 | Excel/回填 | 主体识别 | V2 列 |
| source_asset_code | 资产分笔号 | VARCHAR(64) | 否 | Excel/回填 | 分笔识别 | V2 列 |
| risk_score | 风险评分 | INT | 否 | 风险计算 | 风险展示 | risk_v2 |
| risk_level | 风险等级 | VARCHAR(2) | 否 | 风险计算 | 风险展示 | risk_v2 |
| updated_at | 更新时间 | TIMESTAMPTZ | 否 | 系统 | 重算标记 | migration |
| overdue_days_as_of | 逾期天数截止日 | DATE | 否 | 系统 | 逾期重算 | migration |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_trust_asset_monitor_product_date` | `trust_product_id, data_date DESC` | 按产品+快照日 |
| `idx_trust_asset_monitor_asset_date` | `trust_asset_id, data_date DESC` | 按资产+快照日 |
| `idx_trust_asset_monitor_risk_level` | `risk_level` | 风险筛选 |
| `idx_monitor_custody_source` | `trust_product_id, data_date, custody_asset_code, source_asset_code` | V2 查询 |
| `idx_monitor_import_scope` | scope 列 | 导入覆盖 |

## 上游来源

- 资产监控 Excel（`/ingestion`）
- 核心列：`统计日期` → `data_date`

## 下游使用模块

监控展示、逾期计算、风险评分、Dashboard、金额核对（TODO 明细）

## 数据质量规则

- **`data_date` 为监控快照日期**，必填
- 金额字段默认非负
- 同 Sheet 同房源多行 → warning

## 注意事项

- **`data_date` 是监控快照日期**（Excel「统计日期」），与发行的 `issue_date` **完全不同**。
- `asset_code` 为历史兼容；新逻辑优先 `custody_asset_code` / `source_asset_code`。
- 历史可能存在同 `(product, data_date, asset)` 多行，见 ops 清理脚本。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/overdue/schema.sql` |
| — | risk 列 | `db/modules/risk/schema.sql` |
| — | custody/source | `db/migrations/20250302_asset_code_semantics_v2.sql` |
| — | overdue 重算列 | `db/migrations/20250501_overdue_recalc_columns.sql` |

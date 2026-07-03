# 信托底层房源（`trust_assets`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 信托底层房源 |
| 表英文名 | `trust_assets` |
| Schema 来源 | `db/modules/overdue/schema.sql` + `db/modules/assetinfo/schema.sql` + `db/migrations/20250302_asset_code_semantics_v2.sql` |
| 主键 | `id` |
| 业务唯一标识 | `(trust_product_id, custody_asset_code)` 与 `(trust_product_id, source_asset_code)` 部分唯一；`asset_code`（主编号）可重复 |

## 表用途

信托产品下的底层资产主表，连接监控快照、还款明细、逾期跟进与风险预警。是「资产分笔」与「托管房源」的归集点。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 监控/还款导入时 upsert；或种子数据 |
| 更新 | `initial_transfer_amount`、`custody_asset_code` 等可更新 |
| 冻结 | TODO |
| 删除/归档 | 有子表 FK 时禁止随意删除 |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 底层资产 ID | BIGINT | 是 | 系统 | 主键；`trust_asset_id` | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 系统/导入 | 产品维度 | FK |
| asset_code | 资产主编号 | VARCHAR(64) | 是 | 导入/历史 | 信托号左 12 位；**同一产品可有多行** | 见注意事项 |
| asset_name | 资产名称 | VARCHAR(200) | 否 | 导入 | 展示 | TODO |
| initial_transfer_amount | 初始受让金额 | NUMERIC(18,2) | 是 | 导入/计算 | 资产初始规模 | ≥ 0 |
| custody_asset_code | 托管房源号 | VARCHAR(64) | 否 | Excel/推导 | **主体识别号** | 部分 UNIQUE |
| source_asset_code | 资产分笔号 | VARCHAR(64) | 否 | 导入回填 | 分笔粒度标识 | V2 迁移列 |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_trust_assets_product_asset_code` | `trust_product_id, asset_code` | 主编号聚合查询（非唯一） |
| `uq_trust_assets_product_custody` | `trust_product_id, custody_asset_code` | custody 非空时唯一 |
| `uq_trust_assets_product_source` | `trust_product_id, source_asset_code` | source 非空时唯一 |
| `idx_trust_assets_trust_product_id` | `trust_product_id` | 按产品查询 |

## 上游来源

- 监控/还款/发行 Excel 导入（`/assetinfo`、`/issuance`）

## 下游使用模块

监控、还款、逾期、风险；发行表 `trust_asset_id` 可空关联。

## 数据质量规则

- **一主编号多托管**：同一 `asset_code`（主编号）下允许多个 `custody_asset_code`（多行 `trust_assets`）
- `custody_asset_code` 非空时在同一产品下唯一（持久化锚点）
- `source_asset_code` 非空时在同一产品下唯一（分笔号 1:1 托管）

## 注意事项

- **`asset_code` 表示资产主编号**（信托号左 12 位）：同一产品内**可重复**；导入 upsert 以 `custody_asset_code` 为首要匹配键。
- 新逻辑应使用 `custody_asset_code` + `source_asset_code`；**禁止在新功能中继续扩散对 `asset_code` 单独唯一性的依赖**。
- `source_asset_code` 回填规则：默认等于历史 `asset_code`（分笔号）。
- `custody_asset_code` 可从分笔号推导：`101127075900-001` → `101127075900`（见 `assetinfo_cleanse.derive_custody_from_source`）。
- 与发行模块的 `custody_asset_code` 语义一致，但发行记录不强制 FK 到本表。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线表 | `db/modules/overdue/schema.sql` |
| — | 新增 custody | `db/modules/assetinfo/schema.sql` |
| — | 新增 source_asset_code | `db/migrations/20250302_asset_code_semantics_v2.sql` |
| 2026-07-05 | 一主编号多托管；移除 asset_code 唯一 | `db/migrations/20260705_trust_assets_multi_custody_per_primary.sql` |

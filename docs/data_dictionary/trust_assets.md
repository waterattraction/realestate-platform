# 信托底层房源（`trust_assets`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 信托底层房源 |
| 表英文名 | `trust_assets` |
| Schema 来源 | `db/modules/overdue/schema.sql` + `db/modules/ingestion/schema.sql` + `db/migrations/20250302_asset_code_semantics_v2.sql` |
| 主键 | `id` |
| 业务唯一标识 | `(trust_product_id, asset_code)` UNIQUE；另有 `(trust_product_id, custody_asset_code)` 部分唯一 |

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
| asset_code | 资产编号（历史） | VARCHAR(64) | 是 | 导入/历史 | **历史兼容字段**；唯一约束仍用此列 | 见注意事项 |
| asset_name | 资产名称 | VARCHAR(200) | 否 | 导入 | 展示 | TODO |
| initial_transfer_amount | 初始受让金额 | NUMERIC(18,2) | 是 | 导入/计算 | 资产初始规模 | ≥ 0 |
| custody_asset_code | 托管房源号 | VARCHAR(64) | 否 | Excel/推导 | **主体识别号** | 部分 UNIQUE |
| source_asset_code | 资产分笔号 | VARCHAR(64) | 否 | 导入回填 | 分笔粒度标识 | V2 迁移列 |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_trust_assets_product_code` | `trust_product_id, asset_code` | 历史唯一 |
| `uq_trust_assets_product_custody` | `trust_product_id, custody_asset_code` | custody 非空时唯一 |
| `idx_trust_assets_trust_product_id` | `trust_product_id` | 按产品查询 |

## 上游来源

- 监控/还款 Excel 导入（`/ingestion`）
- 种子：`db/modules/overdue/seed.sql`

## 下游使用模块

监控、还款、逾期、风险；发行表 `trust_asset_id` 可空关联。

## 数据质量规则

- `asset_code` 在同一产品下唯一
- `custody_asset_code` 非空时在同一产品下唯一

## 注意事项

- **`asset_code` 是历史兼容字段**：DB 唯一约束仍为 `(trust_product_id, asset_code)`；新逻辑应使用 `custody_asset_code` + `source_asset_code`，**禁止在新功能中继续扩散对 `asset_code` 的依赖**。
- `source_asset_code` 回填规则：默认等于历史 `asset_code`（分笔号）。
- `custody_asset_code` 可从分笔号推导：`101127075900-001` → `101127075900`（见 `ingestion_cleanse.derive_custody_from_source`）。
- 与发行模块的 `custody_asset_code` 语义一致，但发行记录不强制 FK 到本表。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线表 | `db/modules/overdue/schema.sql` |
| — | 新增 custody | `db/modules/ingestion/schema.sql` |
| — | 新增 source_asset_code | `db/migrations/20250302_asset_code_semantics_v2.sql` |

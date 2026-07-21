# Canonical Object Dictionary

系统统一 **Canonical Object** 名称。用于 API、BI、AI Agent、MCP 的对象建模。

## 对象总表

| Canonical Object | 中文名 | 主要 DB 表 | 主键 | 业务标识 | 下游模块 | 说明 |
|------------------|--------|-----------|------|----------|----------|------|
| `TrustProduct` | 信托产品 | `trust_products` | `id` | `code` | 全模块 | 物理表 |
| `AssetPool` | 资产包 | `asset_pools` | `id` | `code` | 基础、信托 | 物理表 |
| `TrustAsset` | 信托底层资产 | `trust_assets` | `id` | `(product, asset_code)` / `custody_asset_code` | 监控/还款/逾期/风险 | 物理表 |
| `IssuanceAsset` | 发行资产明细 | `trust_product_issuance_asset_records` | `id` | `business_asset_key`（非唯一） | 发行 | 物理表 |
| `MonitorSnapshot` | 资产监控快照 | `trust_asset_monitor_records` | `id` | `(product, data_date, trust_asset_id)` | 监控/风险/逾期 | 物理表 |
| `RepaymentRecord` | 还款明细 | `trust_repayment_detail_records` | `id` | custody+source+date+amount+period | 还款/核对 | 物理表 |
| `OverdueFollowup` | 逾期跟进 | `trust_overdue_followups` | `id` | TODO | 逾期 | 物理表 |
| `RiskAlert` | 风险预警 | `risk_alerts` | `id` | 开放规则唯一 | 风险 | 物理表 |
| `RiskCase` | 风险案件 | `trust_risk_cases` | `id` | 逻辑案件 | 风险/逾期 | 物理表 |
| `ImportRun` | 导入批次 | `assetinfo_pipeline_runs` / `issuance_import_runs` | `id` | 按模块 | 导入 | 物理表（多表） |
| `ImportSheetRun` | Sheet 导入记录 | `issuance_import_sheet_runs` 等 | `id` | scope | 导入 | 物理表 |
| `User` | 用户 | `users` | `id` | `username` | 认证/审计 | 物理表 |
| `AssetRepurchaseUnit` | 回购单位 | `asset_repurchase_units` | `id` | `company_name` | 资产回购 | 物理表 |
| `AssetRepurchaseOrder` | 资产回购单 | `asset_repurchase_orders` | `id` | — | 资产回购 | 物理表；含单位快照 |
| `AssetRepurchaseAsset` | 回购资产（含冻结监控快照） | `asset_repurchase_assets` | `(repurchase_order_id, asset_code)` | 资产主编号 | 资产回购 | 物理表；`historical_property_codes` 留档全部 custody/source 编号 |
| `ManualSettlement` | 手工结算 | `trust_asset_manual_settlements` | `id` | `(product, asset_code, settlement_date, id)` | 资产管理工作台 / 披露读路径 | 物理表；独立账本，不写还款/监控事实 |
| `ManualSettlementAttachment` | 手工结算附件 | `trust_asset_manual_settlement_attachments` | `id` | — | 资产管理工作台 | 物理表 |
| `DisclosureSnapshot` | 数据披露快照 | `disclosure_snapshots` | `id` | `(snapshot_type, as_of_date, frozen_at)` | 还款/监控披露 | 物理表；还款可含 `as_of_start_date` |

## 对象详情

### TrustProduct

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是（预留） |

### AssetPool

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | TODO |

### TrustAsset

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是 |
| 备注 | 历史 `asset_code` 与 `custody_asset_code` 并存 |

### IssuanceAsset

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是 |
| 备注 | 无 `data_date`；时间维度 `issue_date` |

### MonitorSnapshot

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是 |
| 备注 | 核心时间 `data_date` |

### RepaymentRecord

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是 |

### OverdueFollowup

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是 |
| 备注 | 无独立 Excel 导入 |

### RiskAlert

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 逻辑对象 | 否 |
| 开放 API / AI | 是 |

### RiskCase

| 项 | 值 |
|----|-----|
| 物理表 | **否**（映射 `trust_overdue_followups` + SLA/风险扩展列） |
| 逻辑对象 | **是** |
| 开放 API / AI | 是（案件视图） |
| 备注 | 无独立 `risk_cases` 表 |

### ImportRun / ImportSheetRun

| 项 | 值 |
|----|-----|
| 物理表 | 是（`/assetinfo` 与 `/issuance` 各有一套） |
| 开放 API / AI | TODO（审计查询） |

### User

| 项 | 值 |
|----|-----|
| 物理表 | 是 |
| 开放 API / AI | 否（内部） |

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.5 首批 12 对象 |
| 2026-07-21 | 新增资产回购域 3 对象（`AssetRepurchaseUnit` / `AssetRepurchaseOrder` / `AssetRepurchaseAsset`）；回购域以资产主编号为业务标识（identifiers 例外见 `docs/data_dictionary/asset_repurchase.md`） |
| 2026-07-21 | 新增手工结算域 2 对象（`ManualSettlement` / `ManualSettlementAttachment`）；读路径 overlay，不写还款/监控事实表 |
| 2026-07-21 | 补充 `DisclosureSnapshot`（还款披露日期范围 `as_of_start_date`） |

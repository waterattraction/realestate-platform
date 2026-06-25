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
| `RiskCase` | 风险案件 | `trust_overdue_followups`（扩展） | `id` | 逻辑案件 | 风险/逾期 | **逻辑对象** |
| `ImportRun` | 导入批次 | `ingestion_pipeline_runs` / `issuance_import_runs` | `id` | 按模块 | 导入 | 物理表（多表） |
| `ImportSheetRun` | Sheet 导入记录 | `issuance_import_sheet_runs` 等 | `id` | scope | 导入 | 物理表 |
| `User` | 用户 | `users` | `id` | `username` | 认证/审计 | 物理表 |

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
| 物理表 | 是（`/ingestion` 与 `/issuance` 各有一套） |
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

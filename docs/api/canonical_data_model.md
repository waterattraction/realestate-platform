# Canonical API Data Model

面向 **BI / AI Agent / OpenAPI / MCP** 的统一对象模型。与 [`docs/canonical/`](../canonical/README.md) 对齐；物理细节见 [`docs/data_dictionary/`](../data_dictionary/README.md)。

> 当前 REST 实现多为 HTML + `snake_case` 内网路由；本文定义 **对外语义模型**（对象名 PascalCase，字段 camelCase）。

## 设计原则

| 原则 | 说明 |
|------|------|
| 复用 Canonical | 字段名来自 `field_dictionary.md`，禁止同义词 |
| 对象稳定 | API 对象名 = `object_dictionary.md` Canonical Object |
| 时间分离 | Issuance 用 `issueDate`；Monitor/Risk 用 `dataDate`；Repayment 用 `repaymentDate` |
| 逻辑对象 | `RiskCase` 无独立表，API 可作为聚合资源暴露 |

## 对象索引

| API 对象 | 中文 | 物理/逻辑 | 开放 API / AI |
|----------|------|-----------|:-------------:|
| [TrustProduct](#trustproduct) | 信托产品 | 物理 | 是 |
| [AssetPool](#assetpool) | 资产包 | 物理 | TODO |
| [IssuanceAsset](#issuanceasset) | 发行资产明细 | 物理 | 是 |
| [TrustAsset](#trustasset) | 信托底层资产 | 物理 | 是 |
| [MonitorSnapshot](#monitorsnapshot) | 监控快照 | 物理 | 是 |
| [RepaymentRecord](#repaymentrecord) | 还款明细 | 物理 | 是 |
| [OverdueFollowup](#overduefollowup) | 逾期跟进 | 物理 | 是 |
| [RiskAlert](#riskalert) | 风险预警 | 物理 | 是 |
| [RiskCase](#riskcase) | 风险案件 | **逻辑** | 是 |
| [ImportRun](#importrun) | 导入批次 | 物理 | TODO |
| [ImportSheetRun](#importsheetrun) | Sheet 导入 | 物理 | TODO |
| [User](#user) | 用户 | 物理 | 否 |

---

## TrustProduct

| 项 | 值 |
|----|-----|
| API 名称 | `TrustProduct` |
| 中文名 | 信托产品 |
| 物理表 | `trust_products` |
| 主键 | `id` → `trustProductId` |

### 核心字段

| API 字段 | Canonical | DB 来源 | 含义 |
|----------|-----------|---------|------|
| `trustProductId` | `trust_product_id` | `trust_products.id` | 产品 ID |
| `assetPoolId` | — | `asset_pool_id` | 所属资产包 |
| `code` | — | `code` | 产品编码 |
| `name` | `trust_product_name` | `name` | 产品名称 |
| `status` | — | `status` | draft / raising / active / … |
| `targetAmount` | — | `target_amount` | 目标规模 |
| `raisedAmount` | — | `raised_amount` | 已募集 |

### 业务含义

证券化信托产品主数据，全模块外键维度。

### 开放

**是** — 产品目录、Agent 上下文根对象。

---

## AssetPool

| 项 | 值 |
|----|-----|
| API 名称 | `AssetPool` |
| 中文名 | 资产包 |
| 物理表 | `asset_pools` |
| 主键 | `id` → `assetPoolId` |

### 核心字段

| API 字段 | DB 来源 | 含义 |
|----------|---------|------|
| `assetPoolId` | `id` | 资产包 ID |
| `code` | `code` | 编码 |
| `name` | `name` | 名称 |
| `status` | `status` | pending / active |

### 业务含义

入池资产集合，关联 Project 与 TrustProduct。

### 开放

**TODO** — 基础模块，优先级低于信托链。

---

## IssuanceAsset

| 项 | 值 |
|----|-----|
| API 名称 | `IssuanceAsset` |
| 中文名 | 发行资产明细 |
| 物理表 | `trust_product_issuance_asset_records` |
| 主键 | `id` → `issuanceAssetId` |

### 核心字段

| API 字段 | Canonical | DB 来源 | 含义 |
|----------|-----------|---------|------|
| `issuanceAssetId` | — | `id` | 行 ID |
| `trustProductId` | `trust_product_id` | `trust_product_id` | 产品 |
| `trustAssetId` | `trust_asset_id` | `trust_asset_id` | 底层资产（可空） |
| `custodyAssetCode` | `custody_asset_code` | `custody_asset_code` | 托管房源主体号 |
| `issueDate` | `issue_date` | `issue_date` | **发行日** |
| `businessAssetKey` | `business_asset_key` | `business_asset_key` | 冲突分析键（非唯一） |
| `migrationType` | `migration_type` | `migration_type` | new_issuance / transfer / … |
| `fromTrustProductId` | `from_trust_product_id` | `from_trust_product_id` | 转出产品 |
| `receivableContractAmount` | `receivable_contract_amount` | `receivable_contract_amount` | 合同金额 |
| `receivableTransferAmount` | `receivable_transfer_amount` | `receivable_transfer_amount` | 转让价款 |
| `assetTransferDiscountRate` | `asset_transfer_discount_rate` | `asset_transfer_discount_rate` | 折扣率 0~1 |
| `city` | `city` | `city` | 城市 |
| `sourceRowNumber` | `source_row_number` | `source_row_number` | Excel 行号 |

### 业务含义

某产品在某发行日的入池资产明细；**无 `dataDate`**。

### 开放

**是** — 发行分析、转让链、BI 入池报表。

---

## TrustAsset

| 项 | 值 |
|----|-----|
| API 名称 | `TrustAsset` |
| 中文名 | 信托底层资产 |
| 物理表 | `trust_assets` |
| 主键 | `id` → `trustAssetId` |

### 核心字段

| API 字段 | Canonical | DB 来源 | 含义 |
|----------|-----------|---------|------|
| `trustAssetId` | `trust_asset_id` | `id` | 资产 ID |
| `trustProductId` | `trust_product_id` | `trust_product_id` | 产品 |
| `custodyAssetCode` | `custody_asset_code` | `custody_asset_code` | 托管房源主体号 |
| `assetCode` | `asset_code` | `asset_code` | **历史兼容**，勿扩散 |
| `city` | `city` | `city` | 城市 |

### 业务含义

监控/还款/逾期/风险的资产锚点。

### 开放

**是** — Agent 查房源、BI 资产维度。

---

## MonitorSnapshot

| 项 | 值 |
|----|-----|
| API 名称 | `MonitorSnapshot` |
| 中文名 | 资产监控快照 |
| 物理表 | `trust_asset_monitor_records` |
| 主键 | `id` → `monitorSnapshotId` |

### 核心字段

| API 字段 | Canonical | DB 来源 | 含义 |
|----------|-----------|---------|------|
| `monitorSnapshotId` | — | `id` | 快照 ID |
| `trustProductId` | `trust_product_id` | `trust_product_id` | 产品 |
| `trustAssetId` | `trust_asset_id` | `trust_asset_id` | 资产 |
| `custodyAssetCode` | `custody_asset_code` | `custody_asset_code` | 主体号 |
| `sourceAssetCode` | `source_asset_code` | `source_asset_code` | 分笔号 |
| `dataDate` | `data_date` | `data_date` | **快照日** |
| `remainingAmount` | `remaining_amount` | `remaining_amount` | 剩余还款 |
| `repaidAmount` | `repaid_amount` | `repaid_amount` | 已还款 |
| `overdueDays` | `overdue_days` | `overdue_days` | 逾期天数 |
| `delinquencyBucket` | — | `delinquency_bucket` | ES / M1 / M2 / … |
| `riskLevel` | `risk_level` | `risk_level` | A/B/C/D 或 canonical 映射 |
| `riskScore` | `risk_score` | `risk_score` | 风险分 |
| `sourceFileName` | `source_file_name` | `source_file_name` | 来源文件 |
| `sourceSheetName` | `source_sheet_name` | `source_sheet_name` | 来源 Sheet |

### 业务含义

某日资产状态快照；风险与逾期计算的输入。

### 开放

**是** — BI 仪表板、风险 Agent 主数据源。

---

## RepaymentRecord

| 项 | 值 |
|----|-----|
| API 名称 | `RepaymentRecord` |
| 中文名 | 还款明细 |
| 物理表 | `trust_repayment_detail_records` |
| 主键 | `id` → `repaymentRecordId` |

### 核心字段

| API 字段 | Canonical | DB 来源 | 含义 |
|----------|-----------|---------|------|
| `repaymentRecordId` | — | `id` | 明细 ID |
| `trustProductId` | `trust_product_id` | `trust_product_id` | 产品 |
| `trustAssetId` | `trust_asset_id` | `trust_asset_id` | 资产 |
| `custodyAssetCode` | `custody_asset_code` | `custody_asset_code` | 主体号 |
| `sourceAssetCode` | `source_asset_code` | `source_asset_code` | 分笔号 |
| `repaymentDate` | `repayment_date` | `repayment_date` | **实际回款日** |
| `actualRepaymentAmount` | `actual_repayment_amount` | `actual_repayment_amount` | 当期还款额 |
| `periodNo` | `period_no` | `period_no` | 期数 |
| `dataDate` | `data_date` | `data_date` | 导入批次日（非核对主维） |

### 业务含义

单笔还款事实；与 MonitorSnapshot 做金额核对。

### 开放

**是** — 回款分析、对账 Agent。

---

## OverdueFollowup

| 项 | 值 |
|----|-----|
| API 名称 | `OverdueFollowup` |
| 中文名 | 逾期跟进 |
| 物理表 | `trust_overdue_followups` |
| 主键 | `id` → `overdueFollowupId` |

### 核心字段

| API 字段 | DB 来源 | 含义 |
|----------|---------|------|
| `overdueFollowupId` | `id` | 跟进 ID |
| `trustProductId` | `trust_product_id` | 产品 |
| `custodyAssetCode` | `custody_asset_code` | 房源 |
| `dataDate` | `data_date` | 关联快照日 |
| `status` | `status` | open / in_progress / resolved / closed |
| `overdueDays` | `overdue_days` | 逾期天数 |

### 业务含义

逾期台账与人工跟进；无独立 Excel 导入。

### 开放

**是** — 催收工作流、Agent 任务队列。

---

## RiskAlert

| 项 | 值 |
|----|-----|
| API 名称 | `RiskAlert` |
| 中文名 | 风险预警 |
| 物理表 | `risk_alerts` |
| 主键 | `id` → `riskAlertId` |

### 核心字段

| API 字段 | DB 来源 | 含义 |
|----------|---------|------|
| `riskAlertId` | `id` | 预警 ID |
| `trustProductId` | `trust_product_id` | 产品 |
| `trustAssetId` | `trust_asset_id` | 资产（可空） |
| `status` | `status` | open / acknowledged / resolved / ignored |
| `riskLevel` | `risk_level` | 等级 |
| `dataDate` | `data_date` | 触发快照日 |

### 业务含义

规则或人工触发的风险信号。

### 开放

**是** — 告警订阅、Agent 推理输入。

---

## RiskCase

| 项 | 值 |
|----|-----|
| API 名称 | `RiskCase` |
| 中文名 | 风险案件 |
| 物理表 | **无**（逻辑：基于 `trust_overdue_followups` + 风险扩展） |
| 主键 | `overdueFollowupId` 或合成 `riskCaseId` |

### 核心字段

| API 字段 | 来源 | 含义 |
|----------|------|------|
| `riskCaseId` | 逻辑合成 | 案件 ID |
| `overdueFollowupId` | `trust_overdue_followups.id` | 关联跟进 |
| `trustProductId` | 跟进表 | 产品 |
| `custodyAssetCode` | 跟进表 | 房源 |
| `status` | 跟进 `status` | 案件状态 |
| `slaDeadline` | 扩展列 TODO | SLA |
| `riskAlerts` | 关联 `RiskAlert[]` | 关联预警 |

### 业务含义

面向信托/风控的 **案件视图**，聚合逾期跟进与预警。

### 开放

**是** — 案件工作台、AI 摘要与建议。

---

## ImportRun

| 项 | 值 |
|----|-----|
| API 名称 | `ImportRun` |
| 中文名 | 导入批次 |
| 物理表 | `ingestion_pipeline_runs` / `issuance_import_runs` |
| 主键 | `id` → `importRunId` |

### 核心字段

| API 字段 | DB 来源 | 含义 |
|----------|---------|------|
| `importRunId` | `id` | 批次 ID |
| `module` | 逻辑 | `ingestion` / `issuance` |
| `trustProductId` | `trust_product_id` | 产品 |
| `status` | `status` | pending / running / completed / failed |
| `createdAt` | `created_at` | 创建时间 |
| `createdBy` | `created_by` | 操作人 |

### 业务含义

一次 Excel 上传与导入的审计根对象。

### 开放

**TODO** — 内部审计优先；可只读开放给运维 Agent。

---

## ImportSheetRun

| 项 | 值 |
|----|-----|
| API 名称 | `ImportSheetRun` |
| 中文名 | Sheet 导入记录 |
| 物理表 | `issuance_import_sheet_runs` 等 |
| 主键 | `id` → `importSheetRunId` |

### 核心字段

| API 字段 | DB 来源 | 含义 |
|----------|---------|------|
| `importSheetRunId` | `id` | Sheet 记录 ID |
| `importRunId` | `import_run_id` | 父批次 |
| `sheetName` | `sheet_name` | Sheet 名 |
| `action` | `action` | import / overwrite / skip / … |
| `status` | `status` | pending / completed / failed |
| `rowCount` | `row_count` | 行数（若有） |

### 业务含义

批次内单 Sheet 的处理结果与 action。

### 开放

**TODO** — 与 ImportRun 一并开放。

---

## User

| 项 | 值 |
|----|-----|
| API 名称 | `User` |
| 中文名 | 用户 |
| 物理表 | `users` |
| 主键 | `id` → `userId` |

### 核心字段

| API 字段 | DB 来源 | 含义 |
|----------|---------|------|
| `userId` | `id` | 用户 ID |
| `username` | `username` | 登录名 |
| `displayName` | `display_name` | 展示名 |

### 业务含义

认证与导入审计；不含密码哈希。

### 开放

**否** — 仅内部会话；不暴露给外部 Agent。

---

## MCP / OpenAPI 预留

| 资源路径（建议） | 对象 |
|------------------|------|
| `/trust-products` | TrustProduct |
| `/trust-products/{id}/issuance-assets` | IssuanceAsset |
| `/trust-products/{id}/monitor-snapshots` | MonitorSnapshot |
| `/trust-products/{id}/repayment-records` | RepaymentRecord |
| `/trust-products/{id}/overdue-followups` | OverdueFollowup |
| `/risk-alerts` | RiskAlert |
| `/risk-cases` | RiskCase |

查询参数统一：`dataDate`、`issueDate`、`custodyAssetCode`。

## 相关文档

- [`../canonical/field_dictionary.md`](../canonical/field_dictionary.md)
- [`../architecture/domain_model.md`](../architecture/domain_model.md)
- [`../architecture/data_lineage.md`](../architecture/data_lineage.md)

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2 P5 初稿 |

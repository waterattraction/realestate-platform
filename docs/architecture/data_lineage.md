# Data Lineage（数据血缘）

描述 **Excel → cleanse → preview → import → DB → 页面/API/计算** 全链路。与 [`docs/excel/`](../excel/) 模块文档互补。

> 只读文档；代码入口见 `backend/app/*_upload.py`、`*_cleanse.py`。

## 总览

```text
Excel 文件
  → 上传 (UploadFile)
  → Sheet 识别 (is_*_sheet)
  → cleanse (COL_ALIASES / 类型转换 / 推导)
  → preview / precheck (冲突、缺失、统计)
  → confirm import (action: import | overwrite | skip | needs_confirm | failed)
  → DB 写入 (UPSERT / scope 覆盖)
  → 页面列表 / API / 派生计算 (逾期、风险、核对)
```

## 发行（Issuance）

| 阶段 | 组件 | 输入 | 输出 |
|------|------|------|------|
| 上传 | `issuance_upload.py` | `.xlsx` + `trust_product_id` + `issue_date` | 临时解析 |
| 识别 | `issuance_cleanse.is_issuance_sheet` | DataFrame | 是否发行 Sheet |
| 清洗 | `issuance_cleanse.COL_ALIASES` | Excel 列名 | Canonical 字段 |
| 推导 | `build_business_asset_key`, `resolve_migration_type` | 行数据 | `business_asset_key`, `migration_type` |
| 别名解析 | `trust_product_aliases` + `_resolve_from_trust_product` | `from_trust_product_name` | `from_trust_product_id` |
| 预检 | precheck stats | 行集合 | 冲突、折扣率、转出产品匹配 |
| 导入 | SQL INSERT/UPSERT | 确认行 | `trust_product_issuance_asset_records` |
| 审计 | `issuance_import_runs` / `issuance_import_sheet_runs` | 批次 | action, status |
| 下游 | 发行列表页 | DB | HTML `/issuance` |

**时间维度**：仅 `issue_date`；禁止写入 `data_date`。

**关键表**：`trust_product_issuance_asset_records`、`trust_product_aliases`。

## 监控（Monitor / Ingestion）

| 阶段 | 组件 | 输入 | 输出 |
|------|------|------|------|
| 上传 | `ingestion_upload.py` | `.xlsx` + `trust_product_id` | 管道批次 |
| 识别 | `ingestion_cleanse.is_monitor_sheet` | 固定列 + alias | 监控 Sheet |
| 清洗 | 列名 + `COL_ALIASES`（如 `remaining_amount`） | Excel | `data_date`, amounts |
| 推导 | `derive_custody_from_source` | `source_asset_code` | `custody_asset_code` |
| 预检 | scope 冲突 | `(product, data_date, file, sheet)` | overwrite / skip |
| 导入 | UPSERT | 行 | `trust_assets`, `trust_asset_monitor_records` |
| 审计 | `ingestion_pipeline_runs` | 批次 | status |
| 下游 | 托管列表、风险 Hub | `data_date` 最新快照 | HTML + SQL 聚合 |

**时间维度**：`data_date`（统计日期）。

**覆盖 scope**：`source_file_name` + `source_sheet_name` + `data_date`。

## 还款（Repayment）

| 阶段 | 组件 | 输入 | 输出 |
|------|------|------|------|
| 识别 | `issuance_cleanse.is_repayment_like_sheet` 或 ingestion 路径 | 含「当期实际还款金额」等 | 还款 Sheet |
| 清洗 | Excel 列 | `repayment_date`, `actual_repayment_amount`, `period_no` | Canonical 行 |
| 关联 | `trust_asset_id` lookup | `custody_asset_code` / `source_asset_code` | FK |
| 导入 | INSERT + scope 索引 | 行 | `trust_repayment_detail_records` |
| 下游 | 还款明细页 | DB | HTML |

**业务日**：`repayment_date`；批次可能带 `data_date` 作导入 scope，**不作金额核对主维度**。

## 金额核对（Reconciliation）

| 阶段 | 组件 | 输入 | 输出 |
|------|------|------|------|
| 触发 | `main.py` 核对路由 | `trust_product_id` + `data_date` | 核对结果 |
| 监控侧 | `trust_asset_monitor_records` | `repaid_amount`, `remaining_amount` | 快照余额 |
| 还款侧 | `SUM(trust_repayment_detail_records)` | 全量明细至快照日 | `repayment_detail_total` |
| 规则 | `RECONCILIATION_TOLERANCE` | 差额 | balance_pass / cross_pass |
| 展示 | 核对页 HTML | items + summary | 异常标红 |

**依据**：`监控快照日 + 全量还款明细`（`RECONCILIATION_BASIS_LABEL`）。

## 逾期（Overdue）

| 阶段 | 组件 | 输入 | 输出 |
|------|------|------|------|
| 来源 | 监控快照 | `overdue_days`, `delinquency_bucket`, `remaining_amount` | 逾期候选 |
| 生成 | 系统逻辑 / 种子 | M2+ 资产 | `trust_overdue_followups` |
| 人工 | 跟进页 | status 更新 | open → in_progress → resolved/closed |
| 标记 | `trust_asset_trust_marks` | `internal_status`（中文） | 托管列表展示 |
| 下游 | 逾期台账页 | DB | HTML |

**无独立 Excel 导入**；数据血缘起自 MonitorSnapshot。

## 风险（Risk）

| 阶段 | 组件 | 输入 | 输出 |
|------|------|------|------|
| 快照输入 | MonitorSnapshot | `risk_level`, `risk_score`, `delinquency_bucket` | 风险视图 |
| 预警 | 规则引擎 / 种子 | 条件匹配 | `risk_alerts` |
| 案件 | 逻辑聚合 | OverdueFollowup + SLA 列 | RiskCase 视图（`risk_hub`） |
| 展示 | `/risk` Hub | SQL JOIN | HTML |

**risk_level**：DB 现用 A/B/C/D/ES；Canonical 映射见 [`enumerations.md`](../canonical/enumerations.md)。

## 跨模块血缘图

```text
                    ┌─────────────┐
                    │ Excel 发行  │
                    └──────┬──────┘
                           │ issue_date
                           ▼
              ┌────────────────────────┐
              │ IssuanceAsset (DB)       │
              └────────────┬─────────────┘
                           │ custody_asset_code
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌────────────┐    ┌──────────────┐   ┌──────────────┐
│ Excel 监控 │    │ Excel 还款   │   │ (无Excel逾期) │
└─────┬──────┘    └──────┬───────┘   └──────┬───────┘
      │ data_date        │ repayment_date   │ 衍生
      ▼                  ▼                  ▼
 MonitorSnapshot    RepaymentRecord    OverdueFollowup
      │                  │                  │
      └────────┬─────────┘                  │
               ▼                            ▼
        金额核对 (main)              RiskAlert / RiskCase
               │
               ▼
         托管列表 / 风险 Hub (页面)
```

## 文档与代码对照

| 文档 | 代码 |
|------|------|
| `docs/excel/issuance.md` | `issuance_cleanse.py`, `issuance_upload.py` |
| `docs/excel/monitor.md` | `ingestion_cleanse.py`, `ingestion_upload.py` |
| `docs/excel/repayment.md` | ingestion + issuance 还款识别 |
| `docs/canonical/alias_dictionary.md` | `COL_ALIASES` |
| `docs/data_dictionary/*.md` | `db/modules/*.sql` |

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2 P4 初稿 |

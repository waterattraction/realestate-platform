# 数据字典

## 覆盖范围

本目录描述 **manifest 全部业务表** 的字段、索引、来源与质量规则。Schema 真相源为 `db/manifest.txt` 所列 SQL。

## 表索引

| 文档 | 表名 | 模块 |
|------|------|------|
| [projects.md](projects.md) | `projects` | 基础 |
| [asset_pools.md](asset_pools.md) | `asset_pools` | 基础 |
| [project_asset_pools.md](project_asset_pools.md) | `project_asset_pools` | 基础 |
| [trust_products.md](trust_products.md) | `trust_products` | 信托 |
| [investors.md](investors.md) | `investors` | 基础 |
| [investments.md](investments.md) | `investments` | 基础 |
| [trust_assets.md](trust_assets.md) | `trust_assets` | 底层资产 |
| [issuance_assets.md](issuance_assets.md) | `trust_product_issuance_asset_records` | 发行 |
| [issuance_import_runs.md](issuance_import_runs.md) | `issuance_import_runs` | 发行审计 |
| [issuance_import_sheet_runs.md](issuance_import_sheet_runs.md) | `issuance_import_sheet_runs` | 发行审计 |
| [monitor_records.md](monitor_records.md) | `trust_asset_monitor_records` | 监控 |
| [repayment_records.md](repayment_records.md) | `trust_repayment_detail_records` | 还款 |
| [ingestion_pipeline_runs.md](ingestion_pipeline_runs.md) | `ingestion_pipeline_runs` | 导入审计 |
| [ingestion_sheet_runs.md](ingestion_sheet_runs.md) | `ingestion_sheet_runs` | 导入审计 |
| [data_mapping_config.md](data_mapping_config.md) | `data_mapping_config` | 导入配置 |
| [trust_product_aliases.md](trust_product_aliases.md) | `trust_product_aliases` | 发行 |
| [trust_asset_trust_marks.md](trust_asset_trust_marks.md) | `trust_asset_trust_marks` | 托管标记 |
| [overdue.md](overdue.md) | `trust_overdue_followups` | 逾期 |
| [risk.md](risk.md) | `risk_alerts` | 风险 |
| [users.md](users.md) | `users` | 用户 |

**覆盖率**：20/20 manifest 表（由 `scripts/schema_diff.py` 校验）。

## 填写规范

每张表文档须包含：表用途、字段清单、索引说明、上游来源、下游使用模块、生命周期、注意事项。

字段表格式：

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |

不确定的业务语义写 `TODO`，勿编造。

## 变更流程

1. 设计评审（见 `data_model.mdc`）
2. 新增 `db/migrations/YYYYMMDD_*.sql` 并更新 `db/manifest.txt`
3. 更新本目录对应表文档
4. 如涉及 Excel，同步 `docs/excel/` 与 `docs/canonical/`
5. 运行 `python scripts/doc_health.py`

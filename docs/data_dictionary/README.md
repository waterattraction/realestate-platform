# 数据字典

## 覆盖范围

本目录描述平台核心业务表的字段、索引、来源与质量规则。Schema 真相源为 `db/` 目录。

## 表索引

| 文档 | 表名 | 模块 |
|------|------|------|
| [trust_products.md](trust_products.md) | `trust_products` | 基础 |
| [trust_assets.md](trust_assets.md) | `trust_assets` | 逾期/监控 |
| [issuance_assets.md](issuance_assets.md) | `trust_product_issuance_asset_records` | 发行 |
| [monitor_records.md](monitor_records.md) | `trust_asset_monitor_records` | 监控 |
| [repayment_records.md](repayment_records.md) | `trust_repayment_detail_records` | 还款 |
| [overdue.md](overdue.md) | `trust_overdue_followups` | 逾期 |
| [risk.md](risk.md) | `risk_alerts` + 扩展列 | 风险 |
| [users.md](users.md) | `users` | 用户 |

## 填写规范

每张表文档须包含：表用途、字段清单、索引说明、上游来源、下游使用模块、注意事项。

字段表格式：

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |

不确定的业务语义写 `TODO`，勿编造。

## 变更流程

1. 设计评审（见 `data_model.mdc`）
2. 新增 `db/migrations/YYYYMMDD_*.sql` 并更新 `db/manifest.txt`
3. 更新本目录对应表文档
4. 如涉及 Excel，同步 `docs/excel/`

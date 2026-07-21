# 资产回购（`asset_repurchase_*`）

确认回购后**仅写入本域新表**，不修改 `trust_asset_monitor_records`、`trust_product_issuance_asset_records` 与还款表。

全程以**资产主编号（`asset_code`）**贯穿：选择、预览、落库、查重均不使用托管资产编号入口。

## 表

| 表 | 用途 |
|----|------|
| `asset_repurchase_units` | 回购单位主数据：公司名称（唯一）+ 一套联系人/邮箱 |
| `asset_repurchase_orders` | 回购单头：产品、单位快照、业务日、金额合计、状态、执行人 |
| `asset_repurchase_assets` | 资产明细 + 冻结监控快照（合并单表），联合主键 `(repurchase_order_id, asset_code)` |

Migration：`db/migrations/20260721_asset_repurchase.sql`

## `asset_repurchase_units`

| Field | 中文名 | 类型 | 必填 | 备注 |
|-------|--------|------|------|------|
| `company_name` | 公司名称 | VARCHAR(200) | 是 | UNIQUE |
| `contact_name` | 联系人 | VARCHAR(100) | 是 | 每单位仅一套 |
| `contact_email` | 邮箱 | VARCHAR(200) | 是 | 服务端做格式校验 |
| `status` | 状态 | VARCHAR(16) | 是 | `active` / `inactive`；停用单位不可用于新回购 |

## `asset_repurchase_orders`

| Field | 中文名 | 类型 | 必填 | 备注 |
|-------|--------|------|------|------|
| `trust_product_id` / `trust_product_name` | 信托产品 | BIGINT / VARCHAR | 是 | FK `trust_products` |
| `repurchase_unit_id` | 回购单位 | BIGINT | 是 | FK `asset_repurchase_units` |
| `unit_company_name` / `unit_contact_name` / `unit_contact_email` | 单位快照 | VARCHAR | 公司必填 | 执行时冻结，后续单位修改不影响已成单 |
| `repurchase_business_date` | 回购业务日 | DATE | 是 | 人工选择，默认当日 |
| `asset_count` | 资产数 | INT | 是 | 按主编号计数 |
| `total_remaining` | 剩余金额合计 | NUMERIC(18,2) | 否 | 聚合监控剩余 |
| `total_repurchase_amount` | 实际回购金额合计 | NUMERIC(18,2) | 否 | 默认=剩余，确认前可改 |
| `status` | 状态 | VARCHAR(32) | 是 | `completed` / `voided` |
| `executed_at/by`、`voided_at/by` | 审计 | — | — | 与置换域一致 |

## `asset_repurchase_assets`（明细 + 冻结快照合并）

联合主键 `(repurchase_order_id, asset_code)`：同一单内主编号唯一；失效后允许在新单中再次出现。

| Field | 中文名 | 类型 | 备注 |
|-------|--------|------|------|
| `asset_code` | 资产主编号 | VARCHAR(64) | 贯穿全流程的唯一标识 |
| `historical_property_codes` | 历史房源号 | TEXT | 该资产在监控全历史与 `trust_assets` 中出现过的全部 distinct **`custody_asset_code`**（不含 source），去重后逗号分隔 |
| `monitor_data_date` | 数据日期 | DATE | 最新快照层 `MAX(data_date)` |
| `initial_transfer_amount` / `repaid_amount` / `remaining_amount` | 金额（聚合） | NUMERIC | 按主编号 SUM |
| `repurchase_amount` | 实际回购金额 | NUMERIC | 默认=剩余金额，确认前可改，≥ 0 |
| `overdue_days` | 逾期天数 | INT | 按主编号 MAX |
| `delinquency_bucket` | M级 | VARCHAR(16) | 见 `docs/canonical/enumerations.md` `delinquency_bucket` |
| `asset_status` / `split_count` / `city` / `community_name` | 监控快照列 | — | 城市取发行最新记录 |
| `source_monitor_record_ids` | 溯源 | TEXT | 来源监控记录 ID 列表（软引用，逗号分隔） |

快照字段在确认时一次性写入，此后不随监控导入变化，作为审计证据。

## 规则

| 项 | 说明 |
|----|------|
| 资产口径 | 最新监控快照层按 `asset_code` 聚合（与逾期工作台口径一致） |
| 查重 | 同产品下已存在 `completed` 回购单的主编号不可再选/再回购 |
| 流程 | 选资产 → 选单位 → **预览** → **确认回购**；改动资产/单位/金额/日期即预览失效 |
| 预览监控数据 | 在主编号聚合汇总之外，按最新监控快照逐分笔展示标准监控列（对齐 `MONITOR_COLUMN_ORDER` / `MONITOR_PREVIEW_COLUMNS`）；**不含** `asset_pool_code`、`source_asset_code`；不修改监控事实表 |
| 执行 | 服务端重建预览重校验后，单事务写 orders + assets |
| 失效 | 可将 `completed` 标为 `voided`；若 `executed_at` 之后该产品有 `assetinfo_pipeline_runs.inserted_monitor_count > 0`，不可失效；失效后资产可重新回购；不物理删除 |
| 标识例外 | `docs/standards/identifiers.md` 约定新功能优先 `custody_asset_code`；本域按业务要求以资产主编号为准（本文档即例外登记） |

## 页面 / API

- 页面：`/asset-repurchase`（主页 §3「资产置换和回购」入口）
- API：`GET /asset-repurchase/assets`、`GET/POST/PUT /asset-repurchase/units*`、
  `POST /asset-repurchase/preview`、`POST /asset-repurchase/execute`、
  `GET /asset-repurchase/orders*`、`POST /asset-repurchase/orders/{id}/void`
- 代码：`backend/app/asset_repurchase.py` + `asset_repurchase_html.py`；测试 `tests/test_asset_repurchase.py`

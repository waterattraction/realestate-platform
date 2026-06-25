# Canonical Enumerations

统一枚举值，避免同一状态在不同模块写成不同值。

## migration_type

发行资产迁移类型（`trust_product_issuance_asset_records.migration_type`）。

| Value | 中文 | 含义 | 使用表 |
|-------|------|------|--------|
| `new_issuance` | 新发行 | 首次进入信托产品 | `trust_product_issuance_asset_records` |
| `transfer` | 产品间转让 | 从其他信托产品转入 | `trust_product_issuance_asset_records` |
| `replenishment` | 补充发行 | 预留 | `trust_product_issuance_asset_records` |
| `rollover` | 续发/展期 | 预留 | `trust_product_issuance_asset_records` |
| `repackage` | 重新封包 | 预留 | `trust_product_issuance_asset_records` |

## import action

导入 Sheet 行级动作（`issuance_import_sheet_runs.action` / ingestion 同类字段）。

| Value | 中文 | 含义 |
|-------|------|------|
| `import` | 导入 | 新增写入 |
| `overwrite` | 覆盖 | 覆盖已有 scope |
| `skip` | 跳过 | 不写入 |
| `needs_confirm` | 待确认 | 需人工确认 |
| `failed` | 失败 | 行级失败 |

## risk_level

### Canonical（跨模块 / BI / AI 推荐）

| Value | 中文 | 含义 |
|-------|------|------|
| `low` | 低 | 低风险 |
| `medium` | 中 | 中风险 |
| `high` | 高 | 高风险 |
| `critical` | 严重 | 极高风险 |

### 当前 DB / UI 映射（`trust_asset_monitor_records.risk_level` 等）

风险页面与监控现使用 **字母等级**，须映射到 Canonical：

| DB/UI 值 | 中文（UI） | Canonical 映射 |
|----------|-----------|----------------|
| `A` | A 级 | `low` |
| `B` | B 级 | `medium` |
| `C` | C 级 | `high` |
| `D` | D 级 | `critical` |
| `ES` | ES（提前结清） | 非风险等级；见 `delinquency_bucket` |

> **TODO**：开放 API / BI 统一输出 Canonical `risk_level`；写入 DB 前可保留 A/B/C/D。

## delinquency_bucket

逾期分桶（`trust_asset_monitor_records.delinquency_bucket`）。

| Value | 中文 | 含义 |
|-------|------|------|
| `ES` | ES（提前结清） | 提前结清 |
| `M1` | M1 | 0–35 天（含 0 天正常在贷） |
| `M2` | M2 | 36–63 天 |
| `M3` | M3 | 64–91 天 |
| `M3_PLUS` | M3+ | ≥92 天 |

## followup status

逾期跟进状态（`trust_overdue_followups.status`）。

| Value | 中文 | 含义 |
|-------|------|------|
| `open` | 待处理 | 新建 |
| `in_progress` | 跟进中 | 处理中 |
| `resolved` | 已解决 | 已解决 |
| `closed` | 已关闭 | 终态 |

## trust product status

`trust_products.status`（seed + `STATUS_LABELS`）。

| Value | 中文 | 含义 | 备注 |
|-------|------|------|------|
| `draft` | 草稿 | 未发布 | seed 存在 |
| `raising` | 募集中 | 募集期 | seed 存在 |
| `active` | 生效中 | 运行中 | `STATUS_LABELS` 有；seed TODO |
| `completed` | 已完成 | 已结束 | `STATUS_LABELS` 有；seed TODO |
| `closed` | 已关闭 | 终态 | TODO 确认是否使用 |

## asset pool status

`asset_pools.status`。

| Value | 中文 | 含义 | 备注 |
|-------|------|------|------|
| `pending` | 待激活 | 待生效 | seed |
| `active` | 生效中 | 运行中 | seed |

## project status

`projects.status`（基础模块，非信托核心）。

| Value | 中文 | 含义 |
|-------|------|------|
| `in_progress` | 进行中 | |
| `completed` | 已完成 | |

## trust asset internal status

`trust_asset_trust_marks.internal_status`（中文值，非英文枚举）。

| Value | 中文 |
|-------|------|
| `待跟进` | 待跟进 |
| `跟进中` | 跟进中 |
| `已解决` | 已解决 |
| `已关闭` | 已关闭 |

> 与 `followup status` **不同字段、不同表**；勿混用。

## risk alert status

`risk_alerts.status`。

| Value | 中文 | 含义 |
|-------|------|------|
| `open` | 开放 | 待处理 |
| `acknowledged` | 已确认 | 已知晓 |
| `resolved` | 已解决 | 已处理 |
| `closed` | 已关闭 | 终态（若使用） |
| `ignored` | 已忽略 | 忽略 |

> **TODO**：确认 `closed` 是否在代码路径中使用。

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.5 首批枚举 |

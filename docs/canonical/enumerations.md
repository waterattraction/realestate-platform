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

导入 Sheet 行级动作（`issuance_import_sheet_runs.action` / assetinfo 同类字段）。

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

逾期分桶（运行时由 `overdue_days` + 剩余本金计算，**非** DB 列）。

公式：`逾期天数 = 重算日 −（锚点日的下月同日）`（可为负）。  
锚点 = `MAX(导入还款最大还款日, 未作废且 settlement_date≤重算日 的最大结算日)`；仅有手工结算也算有还款。  
有效剩余 = `max(0, 监控剩余 − Σ结算)`；≈0 时逾期置空（不写回金额列）。无还款/结算时锚点取最早发行日。

| Value | 中文 | 含义 |
|-------|------|------|
| `ES` | ES（提前结清） | 剩余本金 ≈ 0 |
| `M0` | M0（正常） | 有余额且逾期天数 ≤ 0 |
| `M0_5` | M0.5 | 有余额且 0 < 逾期天数 ≤ 15 |
| `M1` | M1 | 有余额且 15 < 逾期天数 ≤ 30 |
| `M1_PLUS` | M1+ | 有余额且逾期天数 > 30 |
| `M0_PLUS` | M0+（筛选） | M0.5 ∪ M1 ∪ M1+（不含 ES / M0） |

> 过渡期筛选项兼容：`M2`→`M0_5`，`M3`→`M1`，`M2_PLUS`→`M0_PLUS`，`M3_PLUS`→`M1_PLUS`（裸 `M1` 不映射，避免与新 M1 冲突）。

## followup status

逾期跟进状态（`trust_overdue_followups.status`，legacy）。

| Value | 中文 | 含义 |
|-------|------|------|
| `open` | 待处理 | 新建 |
| `in_progress` | 跟进中 | 处理中 |
| `resolved` | 已解决 | 已解决 |
| `closed` | 已关闭 | 终态 |

## followup case status

跟进事项状态（`trust_overdue_followup_cases.status`）。

| Value | 中文 | 含义 |
|-------|------|------|
| `open` | 待跟进 | 新建默认 |
| `in_progress` | 跟进中 | 处理中 |
| `settled_week` | 本周结算 | 本周内结算；仍可写跟进记录 |
| `resolved` | 已解决 | 终态 |
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

## trust asset trust marker

`trust_asset_trust_marks.trust_marker`（中文值）。

| Value | 中文 |
|-------|------|
| `无标记` | 无标记 |
| `已关注` | 已关注 |
| `重点关注` | 重点关注 |

## trust asset internal status

`trust_asset_trust_marks.internal_status`（中文值，**由跟进事项派生**）。

| Value | 中文 | 含义 |
|-------|------|------|
| `正常` | 正常 | 无问题态 / 本周结算事项 |
| `待跟进(N)` | 待跟进(N) | N = open/in_progress（优先于本周结算） |
| `本周结算(M)` | 本周结算(M) | 无问题态且 M = settled_week |

> 列表筛选「待跟进」/「本周结算」分别匹配前缀。与事项 `status` 不同字段；勿混用。

## followup case category

`trust_overdue_followup_cases.category`。

| Value | 中文 |
|-------|------|
| `轻度逾期` | 轻度逾期 |
| `重度逾期` | 重度逾期 |
| `回购` | 回购 |
| `置换` | 置换 |
| `潜在风险` | 潜在风险 |

## asset repurchase order status

`asset_repurchase_orders.status`（`asset_swap_orders.status` 同枚举）。

| Value | 中文 | 含义 |
|-------|------|------|
| `completed` | 已完成 | 确认回购后写入 |
| `voided` | 已失效 | 可失效条件见 `docs/data_dictionary/asset_repurchase.md` |

## asset repurchase unit status

`asset_repurchase_units.status`。

| Value | 中文 | 含义 |
|-------|------|------|
| `active` | 启用 | 可用于新回购单 |
| `inactive` | 停用 | 不可选择，历史订单不受影响 |

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
| 2026-07-21 | 新增资产回购枚举：`asset repurchase order status`、`asset repurchase unit status` |

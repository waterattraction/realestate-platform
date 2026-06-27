# Status Dictionary

专门解释系统各类 **status** 字段，避免同名 status 跨表混用。

> **同名 `status` 在不同表中含义不同，不允许跨表复用语义。**

## 覆盖索引

| 表/模块 | 字段 | 文档章节 |
|---------|------|----------|
| `trust_products` | `status` | [信托产品状态](#trust_productsstatus) |
| `trust_assets` | `status` | [底层资产状态](#trust_assetsstatus) |
| `trust_asset_trust_marks` | `internal_status` | [内部跟进状态](#trust_asset_trust_marksinternal_status) |
| `trust_overdue_followups` | `status` | [逾期跟进状态](#trust_overdue_followupsstatus) |
| `risk_alerts` | `status` | [风险预警状态](#risk_alertsstatus) |
| assetinfo | sheet `action` / `status` | [Assetinfo 导入状态](#assetinfo-sheet-action--status) |
| issuance | sheet `action` / `status` | [Issuance 导入状态](#issuance-sheet-action--status) |

---

## trust_products.status

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `trust_products` | `status` | `draft` | 草稿 | 未正式发布 | 否 |
| `trust_products` | `status` | `raising` | 募集中 | 募集期 | 否 |
| `trust_products` | `status` | `active` | 生效中 | 产品运行中 | 否 |
| `trust_products` | `status` | `completed` | 已完成 | 正常结束 | 是 |
| `trust_products` | `status` | `closed` | 已关闭 | 强制/异常关闭 | 是 |

> seed 现主要为 `draft` / `raising`；`active` / `completed` / `closed` 见 `STATUS_LABELS`，使用待业务确认（TODO）。

---

## trust_assets.status

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `trust_assets` | `status` | — | — | **当前 schema 无此列** | — |

> 底层资产生命周期由 `trust_asset_monitor_records` 快照与 `delinquency_bucket` 表达，非独立 `status` 列。若未来新增列，须先补 canonical。

---

## trust_asset_trust_marks.internal_status

> 用户文档中「`trust_asset_monitor_records.internal_status`」为 **UI 联结字段**；物理列在 `trust_asset_trust_marks.internal_status`。

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `trust_asset_trust_marks` | `internal_status` | `待跟进` | 待跟进 | 默认，需关注 | 否 |
| `trust_asset_trust_marks` | `internal_status` | `跟进中` | 跟进中 | 正在处理 | 否 |
| `trust_asset_trust_marks` | `internal_status` | `已解决` | 已解决 | 问题已处理 | 是 |
| `trust_asset_trust_marks` | `internal_status` | `已关闭` | 已关闭 | 不再跟进 | 是 |

---

## trust_overdue_followups.status

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `trust_overdue_followups` | `status` | `open` | 待处理 | 新建跟进 | 否 |
| `trust_overdue_followups` | `status` | `in_progress` | 跟进中 | 处理中 | 否 |
| `trust_overdue_followups` | `status` | `resolved` | 已解决 | 已解决 | 是 |
| `trust_overdue_followups` | `status` | `closed` | 已关闭 | 关闭 | 是 |

---

## risk_alerts.status

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `risk_alerts` | `status` | `open` | 开放 | 待处理 | 否 |
| `risk_alerts` | `status` | `acknowledged` | 已确认 | 已知晓 | 否 |
| `risk_alerts` | `status` | `resolved` | 已解决 | 已处理 | 是 |
| `risk_alerts` | `status` | `ignored` | 已忽略 | 忽略 | 是 |

---

## Assetinfo sheet action / status

### action（行级，见 `enumerations.md` import action）

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| assetinfo sheet run | `action` | `import` | 导入 | 新增 | 是 |
| assetinfo sheet run | `action` | `overwrite` | 覆盖 | 覆盖 scope | 是 |
| assetinfo sheet run | `action` | `skip` | 跳过 | 不写入 | 是 |
| assetinfo sheet run | `action` | `needs_confirm` | 待确认 | 人工确认 | 否 |
| assetinfo sheet run | `action` | `failed` | 失败 | 行失败 | 是 |

### status（批次/Sheet 级）

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `assetinfo_pipeline_runs` | `status` | `pending` | 待处理 | 已创建 | 否 |
| `assetinfo_pipeline_runs` | `status` | `running` | 运行中 | 执行中 | 否 |
| `assetinfo_pipeline_runs` | `status` | `completed` | 已完成 | 成功结束 | 是 |
| `assetinfo_pipeline_runs` | `status` | `failed` | 失败 | 失败结束 | 是 |

> **TODO**：与代码中实际枚举逐条核对。

---

## Issuance sheet action / status

### action

同 Assetinfo import action（`import` / `overwrite` / `skip` / `needs_confirm` / `failed`）。

### status

| 表/模块 | 字段 | 值 | 中文 | 含义 | 是否终态 |
|---------|------|-----|------|------|----------|
| `issuance_import_runs` | `status` | `pending` | 待处理 | 已创建 | 否 |
| `issuance_import_runs` | `status` | `running` | 运行中 | 执行中 | 否 |
| `issuance_import_runs` | `status` | `completed` | 已完成 | 成功 | 是 |
| `issuance_import_runs` | `status` | `failed` | 失败 | 失败 | 是 |
| `issuance_import_sheet_runs` | `status` | `pending` | 待处理 | Sheet 待处理 | 否 |
| `issuance_import_sheet_runs` | `status` | `completed` | 已完成 | Sheet 完成 | 是 |
| `issuance_import_sheet_runs` | `status` | `failed` | 失败 | Sheet 失败 | 是 |

> **TODO**：与 `issuance_upload.py` 实际写入值核对。

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2.5 首批 status 字段 |

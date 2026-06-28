# Lifecycle（对象生命周期）

说明核心对象的 **创建、更新、冻结、归档** 规则。与 [`domain_model.md`](domain_model.md) 对象一一对应。

> 只读文档；`status` 枚举见 [`docs/canonical/status_dictionary.md`](../canonical/status_dictionary.md)。

## 通则

| 原则 | 说明 |
|------|------|
| 物理删除 | 有下游业务数据时 **禁止** 物理删除主数据 |
| 覆盖导入 | 监控/还款按 `scope`（产品 + 日期 + 文件/Sheet）可 **overwrite** |
| 发行追加 | 发行按 `issue_date` 批次追加；冲突由 precheck 处理 |
| 终态 | `status` 终态后仅允许审计字段更新（TODO：细化权限） |

---

## TrustProduct

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | seed / 管理录入 | `status` 默认 `draft` | 否 |
| 更新 | 状态等 | `status`, `expected_return_rate` 等可改 | 否 |
| 激活 | 业务操作 | `draft` → `raising` → `active` | 否 |
| 冻结 | 停止新发 | 不可新发行批次（TODO：代码约束） | 否 |
| 归档 | 产品结束 | `completed` / `closed` | **是** |

**关联**：删除产品前须无 `IssuanceAsset` / `MonitorSnapshot` 等（外键保护）。

---

## IssuanceAsset

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 发行 Excel import | INSERT `trust_product_issuance_asset_records` | 否 |
| 更新 | 同 `issue_date` 重导 | overwrite scope（若确认） | 否 |
| 冻结 | 产品归档后 | 禁止新增发行行（TODO） | — |
| 归档 | 无独立归档 | 随产品只读保留 | **是**（逻辑只读） |

**时间键**：`issue_date` + `trust_product_id` + `custody_asset_code`。

**标识**：`business_asset_key` 可重复，不作唯一约束。

---

## TrustAsset

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 监控导入 upsert | `trust_assets` 按 `(product, asset_code)` 或 custody | 否 |
| 更新 | 后续导入 | `custody_asset_code` 补全；历史 `asset_code` 保留 | 否 |
| 冻结 | 提前结清 | `remaining_amount` ≈ 0 → `delinquency_bucket=ES` | 否 |
| 归档 | 产品关闭 | 只读；不再新快照（TODO） | **是**（逻辑） |

**备注**：表无独立 `status` 列；生命周期由 MonitorSnapshot 表达。

---

## MonitorSnapshot

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 监控 Excel import | 按 `data_date` 插入快照行 | 否 |
| 更新 | 同 scope overwrite | 替换同 `(product, data_date, file, sheet)` 数据 | 否 |
| 冻结 | 历史日期 | 旧 `data_date` 不可变（仅 overwrite 同 scope） | **是**（快照语义） |
| 归档 | 保留全量 | 不删除；核对/风险取指定 `data_date` | **是** |

**派生**：逾期列表、风险 Hub、托管列表均取 **最新或选定** `data_date` 快照。

---

## RepaymentRecord

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 还款 Excel import | INSERT 明细 | 否 |
| 更新 | 同 scope 重导 | overwrite（按 migration 索引） | 否 |
| 冻结 | — | 明细行一般不修改 | — |
| 归档 | — | 永久保留用于核对 | **是**（不可删） |

**核对**：全量还款明细聚合至监控 `data_date`，见 [`data_lineage.md`](data_lineage.md)。

---

## OverdueFollowup

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 系统根据监控生成 / seed | `status=open` | 否 |
| 更新 | 人工跟进 | `in_progress` | 否 |
| 解决 | 业务确认 | `resolved` | **是** |
| 关闭 | 不再跟进 | `closed` | **是** |
| 归档 | — | 记录保留 | **是** |

**关联**：`trust_asset_trust_marks.internal_status`（中文）与跟进并行，勿与 `status` 混用。

---

## RiskAlert

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 规则命中 / 人工 | `status=open` | 否 |
| 确认 | 操作员 | `acknowledged` | 否 |
| 解决 | 处理完成 | `resolved` | **是** |
| 忽略 | 误报 | `ignored` | **是** |
| 归档 | — | 历史预警只读 | **是** |

---

## RiskCase（逻辑对象）

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 逾期升级 / 风险关联 | 视图聚合 | 否 |
| 更新 | SLA、指派（扩展列） | 更新跟进记录 | 否 |
| 关闭 | 同 OverdueFollowup | `closed` / `resolved` | **是** |

无独立表；生命周期绑定 `trust_overdue_followups` 及风险扩展字段。

---

## ImportRun / ImportSheetRun

| 阶段 | 触发 | 行为 | 终态 |
|------|------|------|------|
| 创建 | 上传 | `pending` | 否 |
| 运行 | 解析导入 | `running` | 否 |
| 完成 | 成功 | `completed` | **是** |
| 失败 | 异常 | `failed` | **是** |

Sheet 级 `action`：`import` / `overwrite` / `skip` / `needs_confirm` / `failed`。

---

## 生命周期总览

```text
TrustProduct:  draft → raising → active → completed/closed
IssuanceAsset: import(issue_date) → [overwrite] → read-only
TrustAsset:    upsert → snapshots accumulate → ES/settled
MonitorSnapshot: per data_date → frozen snapshot → archived
RepaymentRecord: append → overwrite(scope) → permanent
OverdueFollowup: open → in_progress → resolved/closed
RiskAlert:     open → acknowledged → resolved/ignored
```

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2 P4 初稿 |

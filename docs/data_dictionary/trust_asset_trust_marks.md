# 托管房源信托标记（`trust_asset_trust_marks`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 托管房源信托标记 |
| 表英文名 | `trust_asset_trust_marks` |
| Schema 来源 | `db/modules/trust/schema_marks.sql` |
| 主键 | `id` |
| 业务唯一标识 | `(trust_product_id, asset_code)` UNIQUE |

## 表用途

按产品 + 资产主编号记录信托侧标记与派生内部状态；**与监控快照日无关**。资产组合列表、工作台摘要联结展示。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 用户更新信托标记或跟进事项首次派生内部状态时 upsert 一行 |
| 更新 | 仅 `trust_marker` 可由用户写入；`internal_status` 由跟进事项派生回写 |
| 审计 | `data_date` 为最近一次写入时关联的监控日，不参与唯一键与列表 JOIN |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 页面 | FK | |
| asset_code | 资产主编号 | VARCHAR(128) | 是 | 页面 | 业务键 | |
| custody_asset_code | 托管房源主体号 | VARCHAR(128) | 否 | 系统 | 冗余 | |
| data_date | 关联监控日 | DATE | 是 | 页面/系统 | 审计 | 非业务键 |
| trust_marker | 信托标记 | VARCHAR(64) | 是 | 用户 | 信托侧标记 | 无标记 / 已关注 / 重点关注 |
| internal_status | 内部状态 | VARCHAR(32) | 是 | 派生 | 跟进事项汇总 | `正常` / `待跟进(N)` / `本周结算(M)`；只读 |
| marker_note | 备注 | TEXT | 否 | 用户 | 说明 | |
| created_by | 创建人 | VARCHAR(64) | 否 | 会话 | 审计 | |
| updated_by | 更新人 | VARCHAR(64) | 否 | 会话 | 审计 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_trust_asset_trust_marks` | `trust_product_id`, `asset_code` | UNIQUE |
| `idx_trust_asset_trust_marks_lookup` | `trust_product_id`, `asset_code` | 列表 JOIN |

## 上游来源

- 资产组合管理列表用户操作（`upsert_asset_trust_mark`）
- 跟进事项开闭时 `FollowupRepo.sync_internal_status`

## 下游使用模块

- 资产组合管理列表；工作台摘要

## 注意事项

- `trust_marker` 仅三值；历史「已反馈信托」「信托要求说明」等已迁移为「已关注」。
- `internal_status` 禁止 API 人工写入。
- 每个资产主编号仅一行；换监控日不得新建 marks 行。
- 见 `docs/canonical/status_dictionary.md`、`enumerations.md`。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/trust/schema_marks.sql` |
| 2026-07-14 | 标记三值化；内部状态改为派生 | `20260714_followup_cases_multi_and_entry_slim.sql` |
| 2026-07-14 | 业务键去掉 data_date | `20260714_trust_marks_asset_level.sql` |

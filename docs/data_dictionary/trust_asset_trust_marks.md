# 托管房源信托标记（`trust_asset_trust_marks`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 托管房源信托标记 |
| 表英文名 | `trust_asset_trust_marks` |
| Schema 来源 | `db/modules/trust/schema_marks.sql` |
| 主键 | `id` |
| 业务唯一标识 | `(trust_product_id, custody_asset_code, data_date)` UNIQUE |

## 表用途

按产品、托管房源号、快照日记录信托侧标记与内部跟进状态；托管列表 UI 联结展示（非 `trust_asset_monitor_records` 物理列）。

## 生命周期

| 阶段 | 说明 |
|------|------|
| 创建 | 用户更新标记时 upsert |
| 更新 | `trust_marker`、`internal_status`、`marker_note` |
| 归档 | 随 `data_date` 历史只读 | **是** |

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 记录 ID | BIGINT | 是 | 系统 | 主键 | |
| trust_product_id | 信托产品 ID | BIGINT | 是 | 页面 | FK | |
| custody_asset_code | 托管房源主体号 | VARCHAR(128) | 是 | 页面 | 业务键 | |
| data_date | 快照日期 | DATE | 是 | 页面 | 维度 | |
| trust_marker | 信托标记 | VARCHAR(64) | 是 | 用户 | 信托侧标记 | 默认「未标记」 |
| internal_status | 内部状态 | VARCHAR(32) | 是 | 用户 | 中文四态 | 待跟进/跟进中/已解决/已关闭 |
| marker_note | 备注 | TEXT | 否 | 用户 | 说明 | |
| created_by | 创建人 | VARCHAR(64) | 否 | 会话 | 审计 | |
| updated_by | 更新人 | VARCHAR(64) | 否 | 会话 | 审计 | |
| created_at | 创建时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | |
| updated_at | 更新时间 | TIMESTAMPTZ | 是 | 系统 | 审计 | trigger |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `uq_trust_asset_trust_marks` | `trust_product_id`, `custody_asset_code`, `data_date` | UNIQUE |
| `idx_trust_asset_trust_marks_lookup` | `trust_product_id`, `custody_asset_code`, `data_date DESC` | 列表查询 |

## 上游来源

- 托管列表页用户操作（`main.py` `upsert_custody_trust_mark`）

## 下游使用模块

- 托管列表展示；与 `trust_overdue_followups.status` **不同字段**

## 注意事项

- `internal_status` 为中文值；勿与英文 `followup status` 混用。
- 见 `docs/canonical/status_dictionary.md`。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| — | 基线 | `db/modules/trust/schema_marks.sql` |

# 逾期跟进附件（`trust_overdue_followup_attachments`）

## 基本信息

| 项 | 值 |
|----|-----|
| 表中文名 | 逾期跟进附件 |
| 表英文名 | `trust_overdue_followup_attachments` |
| Schema 来源 | `db/migrations/20260625_overdue_followup_attachments.sql` |
| 主键 | `id` |
| 归属 | `entry_id` → `trust_overdue_followup_entries` |

## 表用途

跟进 entry 的图片/文件附件元数据；文件落盘于 `{ASSET_UPLOAD_DIR}/followups/{case_id}/{entry_id}/`。

## 字段清单

| Field | 中文名 | 类型 | 必填 | 来源 | 用途 | 备注 |
|-------|--------|------|:----:|------|------|------|
| id | 附件 ID | BIGINT | 是 | 系统 | 主键；下载路由 | |
| entry_id | 跟进记录 ID | BIGINT | 是 | 系统 | FK | |
| file_name | 原始文件名 | VARCHAR(500) | 是 | 上传 | 展示/下载 | |
| stored_path | 相对存储路径 | VARCHAR(1000) | 是 | 系统 | 相对 `ASSET_UPLOAD_DIR` | |
| content_type | MIME | VARCHAR(128) | 否 | 上传 | | |
| file_size | 字节大小 | BIGINT | 否 | 系统 | | 单文件 ≤10MB |
| attachment_type | 类型 | VARCHAR(16) | 是 | 系统 | image / file | |
| uploaded_by | 上传人 | VARCHAR(64) | 否 | 登录用户 | | |
| created_at | 上传时间 | TIMESTAMPTZ | 是 | 系统 | | |

## 索引说明

| 索引名 | 列 | 用途 |
|--------|-----|------|
| `idx_followup_attachments_entry` | `entry_id` | 按 entry 列表 |

## API

| 方法 | 路径 |
|------|------|
| POST | multipart 随 `POST .../followups/entries` 的 `files[]` |
| GET | `/overdue/workbench/attachments/{id}`（需登录） |

## 注意事项

- 禁止直接暴露绝对路径；下载走鉴权路由。
- 单次最多 10 个文件。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06-25 | 初版 | `20260625_overdue_followup_attachments.sql` |

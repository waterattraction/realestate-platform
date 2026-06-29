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
| file_name | 原始文件名 | VARCHAR(500) | 是 | 上传 | 展示/下载 | 用户可见原名 |
| stored_path | 相对存储路径 | VARCHAR(1000) | 是 | 系统 | 相对 `ASSET_UPLOAD_DIR` | 磁盘文件名为 UUID + 扩展名 |
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

## 上传交互（V1）

逾期工作台「记录跟进」表单使用统一组件 **AttachmentUploader**：

- 支持点击选择、拖拽、Ctrl+V / ⌘+V 粘贴截图或文件
- 前端预览：图片缩略图 + 文件 chip，可删除待上传项
- 仍通过 `multipart/form-data` 的 `files[]` 随跟进保存提交，无独立上传 API

## 限制与存储

- 单条跟进 entry **最多 10 个附件**（含编辑时追加；后端按 DB 已有数 + 本次上传校验）
- 单文件 **最大 10MB**
- 扩展名：`.jpg` `.jpeg` `.png` `.gif` `.webp` `.pdf` `.doc` `.docx` `.xls` `.xlsx` `.csv` `.txt`
- 磁盘存储文件名：**UUID + 扩展名**（不覆盖同名文件）
- `file_name` 保留用户原始文件名（含粘贴截图自动命名）
- 点击打开：待上传用 blob 新标签预览；已上传链至 `GET /overdue/workbench/attachments/{id}`（图片/PDF `inline` 预览，其他附件下载）

## 注意事项

- 禁止直接暴露绝对路径；下载走鉴权路由。
- 本轮不支持删除已上传附件（仅可删除本次待提交选择）。

## 变更记录

| 日期 | 变更 | Migration |
|------|------|-----------|
| 2026-06-25 | 初版 | `20260625_overdue_followup_attachments.sql` |
| 2026-06 | AttachmentUploader V1：拖拽/粘贴、UUID 存储名 | — |

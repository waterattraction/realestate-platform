# 手工结算（`trust_asset_manual_settlements`）

工作台「手工结算录入」的独立账本。确认保存后**仅写入本域表**，不修改 `trust_repayment_detail_records`、`trust_asset_monitor_records`。

读路径（资产组合、管理工作台、披露活数据）按 `(trust_product_id, asset_code)` 汇总金额做 overlay：已还 += Σ结算；剩余 = max(0, 剩余 − Σ结算)。

**逾期天数重算**（首页「重新计算逾期天数」/ 监控导入后重算，`overdue.recalc_monitor`）：
- 仅 `voided_at IS NULL` 且 `settlement_date ≤ as_of` 的结算参与
- 锚点 = `MAX(导入还款最大还款日, 结算最大结算日)`；仅有结算也算有还款
- 有效剩余 = `max(0, remaining − Σ结算)`；≤容差则 `overdue_days` 置空
- **不写回**监控事实表 `remaining_amount` / `repaid_amount`；可写回 `last_payment_date` / `max_payment_date` / `overdue_days`

还款明细披露活数据：
- **当期实际还款金额**：叠加披露区间 `[开始日, 截止日]` 内结算（有截止日事实行则并入该行；否则按资产汇总虚拟行）
- **累计已还款 / 剩余应还款**、回款计划 **已还款 / 剩余还款**：叠加**全部**未作废结算
- 虚拟行字段：`当前还款方`=`repayer`（还款方）；`当期计划还款金额`=`当期实际还款金额`；`初始受让装修金额`取自该资产回款计划 `initial_transfer_amount`
- 回购 / 置换归属仍按**截止日**，不受开始日影响

资产监控披露：统计日不变；**已还款金额 / 剩余还款金额**叠加全部未作废结算。

## 表

| 表 | 用途 |
|----|------|
| `trust_asset_manual_settlements` | 结算主记录 |
| `trust_asset_manual_settlement_attachments` | 结算附件 |

Migration：`db/migrations/20260721_manual_settlements.sql`

## `trust_asset_manual_settlements`

| Field | 中文名 | 类型 | 必填 | 备注 |
|-------|--------|------|------|------|
| `trust_product_id` | 信托产品 | BIGINT | 是 | FK `trust_products` |
| `asset_code` | 资产主编号 | VARCHAR(128) | 是 | 读路径合并键 |
| `custody_asset_code` | 托管资产编号 | VARCHAR(128) | 否 | 创建时尽量解析，失败则回退主编号 |
| `settlement_date` | 结算日期 | DATE | 是 | 还款披露「当期」按区间过滤；累计/监控按全部 |
| `settled_by` | 结算人 | VARCHAR(100) | 是 | |
| `payer` | 结算主体 | VARCHAR(100) | 是 | 原「付款方」字段名保留 |
| `repayer` | 还款方 | VARCHAR(200) | 是 | 下拉；虚拟还款行 `current_payer` |
| `amount` | 结算金额 | NUMERIC(18,2) | 是 | `> 0` |
| `description` | 结算说明 | TEXT | 否 | |
| `created_by` / `created_at` / `updated_at` | 审计 | — | — | |
| `voided_at` / `voided_by` | 作废 | — | — | 作废后不参与 overlay |

## `trust_asset_manual_settlement_attachments`

| Field | 中文名 | 备注 |
|-------|--------|------|
| `settlement_id` | 结算 ID | ON DELETE CASCADE |
| `file_name` / `stored_path` / `content_type` / `file_size` | 文件元数据 | 目录 `{ASSET_UPLOAD_DIR}/manual_settlements/{id}/` |
| `attachment_type` | 类型 | `image` / `file` |

## 规则

| 项 | 说明 |
|----|------|
| 写路径 | `POST /overdue/workbench/manual-settlements` 新建；`POST .../{id}` 修改（含附件增删）；`POST .../{id}/delete` 软删除（`voided_at`） |
| 读路径 | Application / disclosure 层叠加；冻结快照不回写结算；`voided` 不参与 overlay |
| 工作台核对 | 监控已还/剩余与还款合计**两侧**均叠加手工结算后再比「还款✓/⚠」，避免单侧叠加假异常 |
| 附件上限 | 与跟进一致：最多 10 个，单文件 ≤10MB |

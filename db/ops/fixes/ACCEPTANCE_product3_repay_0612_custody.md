# 任务验收记录：美好生活3号 · 0612已还款 · 托管编码归属修正

| 项 | 值 |
|----|-----|
| **状态** | **已完成并验收通过** |
| **完成日期** | 2026-06-25 |
| **产品** | 美好生活3号（`trust_product_id = 3`） |
| **数据范围** | `美好生活3号-还款明细披露信息_20260612.xlsx` / Sheet `0612已还款` |
| **修复行数** | **71**（`custody_asset_code` ≠ `source_asset_code` 且 `trust_asset_id` 错挂） |
| **导入批次** | `pipeline_run_id = 8`（UUID `09250fa1-ef5b-4fb2-bc46-7776bd33dbc7`） |

---

## 1. 问题与根因

| 项 | 说明 |
|----|------|
| **现象** | 0612已还款 111 行中 71 行：`托管房源编码` 与 `资产编号(房源)` 列值不一致（列偏移）；导入时分别映射，`_upsert_trust_asset` 曾优先按 custody 匹配 → `trust_asset_id` 错挂 |
| **权威字段** | Excel `资产编号(房源)` → `source_asset_code` = `custody_asset_code` = `asset_code` |
| **修正字段** | `custody_asset_code`、`trust_asset_id`（`asset_code` 已与 source 一致，UPDATE 幂等） |
| **不改字段** | 金额、期次、`repayment_date`、`source_file_name`、`source_sheet_name`、`synced_at`、`created_at`、`source_asset_code` |
| **范围外** | 106 户严格倍数规则失败为既有业务数据，非本次修复范围 |

---

## 2. 交付物索引

### 2.1 Runbook

| 文件 | 说明 |
|------|------|
| [`README_product3_repay_0612_custody.md`](./README_product3_repay_0612_custody.md) | 执行顺序、回滚、审计表、asset_code 全局结论、防复发说明 |
| **本文件** | 任务验收记录（check / dry-run / apply / verify / 回归） |

### 2.2 脚本与 SQL

| 文件 | 子命令 / 用途 |
|------|----------------|
| [`scripts/ops/fix_product3_repay_0612_custody.py`](../../../scripts/ops/fix_product3_repay_0612_custody.py) | `check` · `dry-run` · `apply` · `verify` · `rollback` |
| [`scripts/checks/check_product3_repay_0612_custody.sql`](../../../scripts/checks/check_product3_repay_0612_custody.sql) | 只读 SQL 检查（行数、唯一性、错挂 `trust_asset_id`） |
| [`db/ops/fixes/20250624_fix_product3_repay_0612_custody.sql`](./20250624_fix_product3_repay_0612_custody.sql) | SQL 变体（默认末尾 `ROLLBACK`；人工审阅后改 `COMMIT`） |

**编排脚本要点**

- `EXPECTED_MISMATCH = 71`
- `apply` 在事务内执行；`UPDATE rowcount ≠ 71` 自动 `ROLLBACK`
- apply 前断言：`trust_assets` 无 `source_asset_code` 重复分组；错挂行均有目标 `trust_assets`
- apply 后断言：不可变字段变化数 = 0
- Dry-run / 严格倍数基线输出目录：`/data/uploads/ops/product3_repay_0612/`（容器可写卷）

### 2.3 导入防复发（代码）

| 文件 | 变更摘要 |
|------|----------|
| [`backend/app/ingestion_upload.py`](../../../backend/app/ingestion_upload.py) | `_resolve_asset_fields` 权威字段；`_excel_custody_source_mismatch_rows`；预检 `[ERROR]` + `needs_confirm`；`_upsert_trust_asset` 查找顺序调整 |
| [`docs/standards/identifiers.md`](../../../docs/standards/identifiers.md) | `asset_code` 历史字段、不可扩散修改（规范依据） |

### 2.4 单元测试

| 文件 | 覆盖 |
|------|------|
| [`tests/test_ingestion_asset_codes.py`](../../../tests/test_ingestion_asset_codes.py) | 权威解析、0612 回归、预检 ERROR、`upsert` 查找顺序、asset_code 不可覆写 |

```bash
docker compose exec -T backend sh -c 'cd /data/repo && python3 -m unittest tests.test_ingestion_asset_codes -v'
# 结果：Ran 19 tests — OK
```

---

## 3. 执行记录

### 3.1 check（只读，apply 前）

| 指标 | 结果 | 预期 |
|------|------|------|
| `sheet_total` | 111 | 111 |
| `mismatch_rows` | 71 | 71 |
| `wrong_trust_asset_id` | 71 | 71 |
| `missing target trust_assets` | 0 | 0 |
| `trust_assets duplicate source_asset_code groups` | 0 | 0 |
| `strict_rule_pass` / `strict_rule_fail` | 301/407 · 106/407 | 基线 |

### 3.2 dry-run（只读，已审阅通过）

| 项 | 结果 |
|----|------|
| 成功 | 是 |
| 预计 UPDATE 行数 | **71** |
| CSV | `/data/uploads/ops/product3_repay_0612/product3_repay_0612_custody_dry_run_20260625T070621Z.csv` |
| JSON | `/data/uploads/ops/product3_repay_0612/product3_repay_0612_custody_dry_run_20260625T070621Z.json` |
| 严格倍数基线 | `/data/uploads/ops/product3_repay_0612/strict_fail_baseline_p3.txt`（106 行） |

Dry-run 样例（id=25466）：`trust_asset_id` 2063→2052；`custody` 107114502274→107114177883（对齐 `auth_source`）；金额/日期不变。

### 3.3 apply（已授权执行）

| 项 | 结果 |
|----|------|
| 成功 | **是** |
| COMMIT | **已完成**（`conn.begin()` 事务成功提交） |
| 实际 UPDATE 行数 | **71** |
| 不可变字段变化 | **0** |
| `asset_code` 实质变化 | **0**（幂等） |

### 3.4 verify（apply 后立即执行）

| 验收项 | 结果 |
|--------|------|
| 0612 Sheet 编码一致 | **111/111** |
| 原 71 行 `trust_asset_id` 纠正 | `backup_rows_with_wrong_trust_asset_id=0` |
| 不可变字段 | **0** 变化 |
| `strict_rule_pass` / `strict_rule_fail` | **301/407** · **106/407**（无新增失败户） |
| 跨表核对失败户数 | **79 → 0**（下降） |
| 备份表 / 日志表 | 已生成 |

---

## 4. 功能回归（apply 后，只读）

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | 还款明细页 · 美好生活3号 0612已还款 | API `total=111`，页内 mismatch=0；HTML 200 |
| 2 | 逾期/风险页面 | `/overdue`、`/overdue/reconciliation`、`/overdue/workbench`、`/risk/workbench`、`/risk/alerts`、`/risk/cases` 均 HTTP 200；`fetch_risk_workbench` queue=407 |
| 3 | 跨表核对 | `cross_fail_count=0`，`cross_pass_count=407` |
| 4 | 导入预检不一致 | 还款/监控：`[ERROR]` + `action=needs_confirm`；列一致时 `import` |
| 5 | 审计表保留 | 见 §5 |

**回归结论：全部通过。未再执行 apply 或 rollback。**

---

## 5. 审计表保留策略

| 表 | 当前状态 | 策略 |
|----|----------|------|
| `_ops_p3_repay_0612_custody_fix_backup` | **71 行** | **暂时保留，勿删除** |
| `_ops_p3_repay_0612_custody_fix_log` | **1 条**（`updated_count=71`，`operator=ops`，`executed_at=2026-06-25 07:09:24+00`） | **暂时保留，勿删除** |

回滚命令（仅在需要时手动执行）：

```bash
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py rollback
```

---

## 6. 常用命令速查

```bash
# 只读检查
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py check

# Dry-run（不写库）
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py dry-run

# 复验（可重复）
docker compose exec -T backend python3 /data/repo/scripts/ops/fix_product3_repay_0612_custody.py verify

# 单元测试
docker compose exec -T backend sh -c 'cd /data/repo && python3 -m unittest tests.test_ingestion_asset_codes -v'
```

---

## 7. 验收签字

| 角色 | 结论 | 日期 |
|------|------|------|
| 业务/数据审阅 | dry-run 71 行对照审阅通过 | 2026-06-25 |
| 执行授权 | apply 已授权并成功 | 2026-06-25 |
| 功能回归 | 五项回归全部通过 | 2026-06-25 |
| **任务状态** | **关闭（备份表与日志表保留）** | 2026-06-25 |

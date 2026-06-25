# 生产数据修复规范（Production Data Repair Standard）

**版本**：1.0  
**适用范围**：房地产资产证券化平台 — 所有涉及生产 PostgreSQL 的数据修复（资产、资产包、信托产品、还款、监控、风险、投资人、募集等）

> 本规范将「一次性 SQL 修补」升级为可审计、可回滚、可重复验证的工程能力。  
> **参考实现（首个完整案例）**：[`db/ops/fixes/product3_repay_0612_custody/`](../../db/ops/fixes/product3_repay_0612_custody/)

---

## 1. 修复原则

### 1.1 什么情况下允许 UPDATE

| 条件 | 说明 |
|------|------|
| 根因已明确 | 有 Proposal 文档：问题范围、权威字段、修正字段、不改字段 |
| 程序已修复或无需程序变更 | 若为导入/计算逻辑缺陷，**必须先合入防复发代码**，再修历史数据 |
| 范围可三元界定 | `trust_product_id` + `source_file_name` + `source_sheet_name`（或等价业务键） |
| 行数可预期 | `EXPECTED_ROWS` 已知；apply 时 `rowcount` 断言 |
| 可备份可回滚 | 备份表 + 统一 `repair_log` |
| 风险等级已评审 | P0~P3 对应审批人（见 §3） |

典型场景：字段归属错挂（如 custody / trust_asset_id）、幂等编码对齐、FK 指向纠正。

### 1.2 什么情况下必须重新导入

| 条件 | 说明 |
|------|------|
| 大范围数据错误 | 影响整文件 / 整 Sheet，且 DELETE+重导比 UPDATE 更安全 |
| 金额 / 期次 / 日期本身错误 | 不属于「归属修正」，禁止静默 UPDATE 金额 |
| 无法精确圈定行集 | 无稳定 WHERE，或预期行数不确定 |
| 缺少权威来源 | 无法从 Excel 或审计批次复现正确值 |

重新导入仍须走完整流程（Check → Dry Run → Approval → …），且保留旧批次备份。

### 1.3 什么情况下禁止直接修改数据库

- 无 Proposal、无 Dry Run 审阅记录
- 无备份策略、无回滚 SQL / rollback 子命令
- 在生产库执行未审阅的 ad-hoc `UPDATE` / `DELETE` / `COMMIT`
- 修复可由程序正确处理的新导入数据，却选择改库「省事」
- 风险等级 P0 未经书面审批

**Cursor / AI 辅助开发**：禁止生成可直接在生产执行的 `UPDATE`/`DELETE`/`COMMIT` 终稿；必须输出 Check + Dry Run 方案，待人工 Approval（见 [`.cursor/rules/production_repair.mdc`](../../.cursor/rules/production_repair.mdc)）。

### 1.4 必须先修复程序，再修复数据

1. 定位根因（导入、计算、匹配顺序等）
2. 合入防复发逻辑 + **单元测试**
3. 再对历史脏数据执行 Repair Job

否则会出现：数据修了、下次导入继续产生同类问题。

---

## 2. 标准流程

```
Proposal（方案：范围、根因、风险等级、不改字段）
    ↓
Check（只读：行数、前置条件、基线指标）
    ↓
Dry Run（修正前后对照导出，不写库）
    ↓
Approval（人工审阅 Dry Run 产物，书面授权）
    ↓
Apply（事务 + 行数断言 + 备份 + repair_log）
    ↓
Verify（数据验收：对齐率、不可变字段、业务指标）
    ↓
Regression（功能回归：相关页面 / API / 核对口径）
    ↓
Acceptance（验收记录归档，任务关闭）
```

| 阶段 | 产出物 |
|------|--------|
| Proposal | Repair 目录下 `README.md` 初稿（问题与方案） |
| Check | `check` 子命令 / `check.sql` 输出 |
| Dry Run | CSV/JSON 对照表（`/data/uploads/ops/<repair_name>/`） |
| Approval | README 或 ACCEPTANCE 中记录审阅人与日期 |
| Apply | `repair_log` 行、`backup` 表 |
| Verify | `verify` 子命令输出 |
| Regression | ACCEPTANCE § 功能回归 |
| Acceptance | `ACCEPTANCE.md` 定稿 |

**门禁**：无 Dry Run 与 Verify 设计，不得进入 Apply 授权。

---

## 3. 风险等级（P0 ~ P3）

| 等级 | 定义 | 示例 | 审批 |
|------|------|------|------|
| **P0** | 全库 / 多产品 / 不可逆；影响募集或投资人资金 | 批量改金额、删投资记录 | 业务负责人 + DBA + 书面签字 |
| **P1** | 单产品大量行；核心 FK 或编码体系 | 数百行 trust_asset_id 错挂 | 业务负责人 + 技术负责人 |
| **P2** | 单产品有限行；可精确圈定；可回滚 | 本次 Product3 0612 · 71 行 | 技术负责人 |
| **P3** | 单行或演示环境；只读验证即可 | 单条测试数据修正 | 执行人自审 + 同僚 Review |

等级写在 Repair `README.md` 头部元数据表中。

---

## 4. 审计要求

### 4.1 统一日志表 `repair_log`

所有**新** Repair 使用统一表（DDL：`db/ops/schema/repair_log.sql`），**禁止**每个 Repair 自建 `*_fix_log` 表。

| 字段 | 说明 |
|------|------|
| `repair_name` | 目录名，如 `product3_repay_0612_custody` |
| `operator` | 执行人（`$USER` 或登录用户） |
| `start_time` / `finish_time` | 事务起止 |
| `status` | `check` / `dry_run` / `applied` / `verified` / `rolled_back` / `failed` |
| `rows_checked` | Check 阶段关键计数 |
| `rows_updated` | Apply 实际 UPDATE 行数 |
| `rows_rollback` | Rollback 恢复行数 |
| `verify_result` | JSON 或简短文本 |
| `remark` | 备注 |
| `backup_table` | 备份表名 |

> **历史案例**：`product3_repay_0612_custody` 在规范建立前已写入 `_ops_p3_repay_0612_custody_fix_log`，保留不删；后续 Repair 一律用 `repair_log`。

### 4.2 备份表命名

```
_ops_backup_<repair_name>
```

示例：`_ops_backup_product3_repay_0612_custody`（新 Repair）；历史：`_ops_p3_repay_0612_custody_fix_backup` 保留。

备份表须包含 `backed_up_at TIMESTAMPTZ`，且在 Acceptance 关闭前**不得删除**。

### 4.3 Operator 与 Timestamp

- Operator：`os.environ.get("REPAIR_OPERATOR")` 或 `USER`，写入 `repair_log`
- Timestamp：数据库 `NOW()` / `TIMESTAMPTZ`，禁止手写本地时间

---

## 5. 回滚要求

- 每个 Repair 包必须提供 **`rollback` 子命令** 或 **`rollback.sql`**
- Rollback 从 `_ops_backup_<repair_name>` 恢复**仅备份行**涉及的列
- Rollback 须写 `repair_log`（`status=rolled_back`，`rows_rollback`）
- Rollback 后必须再跑 `verify`（或等价检查）确认恢复

---

## 6. 验收要求

`ACCEPTANCE.md` 必须包含：

1. 问题与根因摘要  
2. 交付物索引（README、SQL、Python、测试）  
3. Check / Dry Run / Apply / Verify 量化结果  
4. 功能回归表（相关页面与 API）  
5. 审计表保留策略与回滚命令  
6. 验收签字（审阅人、日期、任务状态）

---

## 7. 文档要求

每个 Repair **独立目录**（见 §9），至少包含：

| 文件 | 职责 |
|------|------|
| `README.md` | Runbook：范围、命令、风险、不改字段 |
| `ACCEPTANCE.md` | 验收记录（完成后归档） |
| `repair.sql` | 可选 SQL 路径（默认 `ROLLBACK`） |
| `rollback.sql` | 可选独立回滚脚本 |
| `check.sql` | 只读检查 |
| `repair.py` | 继承 `RepairJob` 的编排脚本 |

从 [`db/ops/templates/`](../ops/templates/) 复制生成，勿空白起草。

---

## 8. 单元测试要求

- 若 Repair 伴随**程序防复发**，必须有单元测试（如 `tests/test_ingestion_asset_codes.py`）
- 测试须覆盖：根因场景、预检/匹配逻辑、回归用例
- CI 通过 `scripts/checks/check_repair_package.py` 校验 Repair 包完整性

---

## 9. 目录规范

```
db/ops/
  schema/
    repair_log.sql              # 统一审计表 DDL
  templates/                    # 新 Repair 模板
  fixes/
    <repair_name>/              # 每个 Repair 独立目录
      README.md
      ACCEPTANCE.md
      repair.sql
      rollback.sql
      check.sql
      repair.py
scripts/ops/
  framework/                    # RepairJob 基类
  fix_<legacy>.py               # 可选：向后兼容入口 shim
scripts/checks/
  check_repair_package.py       # CI 包结构检查
docs/engineering/
  production_data_repair_standard.md   # 本文件
```

**禁止**将多个 Repair 的 SQL 混放在 `db/ops/fixes/*.sql` 根级（历史文件可保留，新 Repair 必须进子目录）。

---

## 10. 参考实现：Product3 0612 编码归属修复

| 资源 | 路径 |
|------|------|
| Runbook | [`db/ops/fixes/product3_repay_0612_custody/README.md`](../../db/ops/fixes/product3_repay_0612_custody/README.md) |
| 验收记录 | [`db/ops/fixes/product3_repay_0612_custody/ACCEPTANCE.md`](../../db/ops/fixes/product3_repay_0612_custody/ACCEPTANCE.md) |
| Repair 脚本 | [`db/ops/fixes/product3_repay_0612_custody/repair.py`](../../db/ops/fixes/product3_repay_0612_custody/repair.py) |
| 入口 shim | [`scripts/ops/fix_product3_repay_0612_custody.py`](../../scripts/ops/fix_product3_repay_0612_custody.py) |
| Check SQL | [`db/ops/fixes/product3_repay_0612_custody/check.sql`](../../db/ops/fixes/product3_repay_0612_custody/check.sql) |
| 单元测试 | [`tests/test_ingestion_asset_codes.py`](../../tests/test_ingestion_asset_codes.py) |

**已验收结果摘要**（2026-06-25）：71 行 UPDATE；111/111 编码对齐；跨表核对 79→0 失败；严格倍数基线 301/407 不变。

后续 Repair **参照该案例的流程与包结构**，从模板生成，继承 `RepairJob`，而非复制粘贴后改常量。

---

## 11. 相关文档

- [`.cursor/rules/production_repair.mdc`](../../.cursor/rules/production_repair.mdc) — AI 辅助开发约束  
- [`docs/standards/identifiers.md`](../standards/identifiers.md) — 编码字段规范  
- [`scripts/ops/framework/README.md`](../../scripts/ops/framework/README.md) — Framework API

# 任务验收记录：美好生活3号 · 0612已还款 · 托管编码归属修正

| 项 | 值 |
|----|-----|
| **repair_name** | `product3_repay_0612_custody` |
| **状态** | **已完成并验收通过**（项目首个完整生产数据修复案例） |
| **完成日期** | 2026-06-25 |
| **风险等级** | P2 |
| **修复行数** | **71** |

规范依据：[`docs/engineering/production_data_repair_standard.md`](../../../docs/engineering/production_data_repair_standard.md)

---

## 1. 问题与根因

| 项 | 说明 |
|----|------|
| **现象** | 0612已还款 111 行中 71 行：托管列与资产编号列不一致（列偏移）→ `trust_asset_id` 错挂 |
| **权威字段** | `资产编号(房源)` → `source_asset_code` |
| **修正字段** | `custody_asset_code`、`trust_asset_id` |
| **不改字段** | 金额、期次、日期、源文件、Sheet、审计时间戳、`source_asset_code` |

---

## 2. 交付物索引

| 文件 | 说明 |
|------|------|
| [`README.md`](./README.md) | Runbook |
| [`repair.py`](./repair.py) | `RepairJob` 参考实现 |
| [`repair.sql`](./repair.sql) | SQL 变体 |
| [`check.sql`](./check.sql) | 只读检查 |
| [`rollback.sql`](./rollback.sql) | 回滚 SQL |
| [`tests/test_assetinfo_asset_codes.py`](../../../tests/test_assetinfo_asset_codes.py) | 防复发单元测试（19 OK） |

---

## 3. 执行记录（摘要）

| 阶段 | 关键结果 |
|------|----------|
| Check | 111 / 71 mismatch；duplicate=0；missing=0 |
| Dry Run | 71 行对照导出 |
| Apply | UPDATE **71**；COMMIT 成功 |
| Verify | 111/111 对齐；跨表失败 79→0 |
| Regression | 五项全通过 |

---

## 4. 审计表保留

| 表 | 策略 |
|----|------|
| `_ops_p3_repay_0612_custody_fix_backup` | **保留**（71 行） |
| `_ops_p3_repay_0612_custody_fix_log` | **保留**（1 条） |

---

## 5. 验收签字

| 角色 | 结论 | 日期 |
|------|------|------|
| 全流程 | Check → Dry Run → Apply → Verify → Regression → Acceptance | 2026-06-25 |
| **任务状态** | **关闭** | 2026-06-25 |

详细量化数据见完整归档 [`../ACCEPTANCE_product3_repay_0612_custody.md`](../ACCEPTANCE_product3_repay_0612_custody.md)。

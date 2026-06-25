# Ops Repair Runbook：{{REPAIR_TITLE}}

| 元数据 | 值 |
|--------|-----|
| **repair_name** | `{{REPAIR_NAME}}` |
| **风险等级** | P?_（P0 最高） |
| **状态** | `proposal` / `approved` / `applied` / `accepted` |
| **类型** | `ops/fix` |
| **产品 / 范围** | {{SCOPE_DESCRIPTION}} |
| **预期修正行数** | {{EXPECTED_ROWS}} |

## 概述

| 项 | 值 |
|----|-----|
| 修正字段 | {{FIELDS_TO_UPDATE}} |
| 不改字段 | {{IMMUTABLE_FIELDS}} |
| 权威字段 / 根因 | {{ROOT_CAUSE_SUMMARY}} |

## 前置条件

- [ ] 程序防复发已合入（如适用）+ 单元测试通过
- [ ] `repair_log` 表已存在（`db/ops/schema/repair_log.sql`）
- [ ] Check 通过：行数、唯一性、目标行存在性

## 执行顺序

```bash
REPAIR=db/ops/fixes/{{REPAIR_NAME}}

# 1. 只读检查
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py check

# 2. Dry Run（产物 → /data/uploads/ops/{{REPAIR_NAME}}/）
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py dry-run

# 3. 人工审阅 CSV / JSON

# 4. Apply（事务 + 行数断言）
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py apply

# 5. Verify
docker compose exec -T backend python3 /data/repo/$REPAIR/repair.py verify
```

或使用 SQL：`$REPAIR/repair.sql`（默认末尾 `ROLLBACK`，审阅后改 `COMMIT`）。

## 回滚

```bash
docker compose exec -T backend python3 /data/repo/db/ops/fixes/{{REPAIR_NAME}}/repair.py rollback
```

备份表：`_ops_backup_{{REPAIR_NAME}}`（Acceptance 关闭前勿删）。

## 审计

- 统一日志：`repair_log`（`repair_name='{{REPAIR_NAME}}'`）
- 备份：`_ops_backup_{{REPAIR_NAME}}`

## 验收

完成后填写 [`ACCEPTANCE.md`](./ACCEPTANCE.md)。

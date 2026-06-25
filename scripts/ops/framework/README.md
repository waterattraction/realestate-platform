# Repair Framework

生产数据修复统一 Python 框架。规范见 [`docs/engineering/production_data_repair_standard.md`](../../../docs/engineering/production_data_repair_standard.md)。

## 核心类型

### `RepairJob`（`base.py`）

抽象基类，子类实现五阶段：

| 方法 | 说明 |
|------|------|
| `check(ctx)` | 只读检查 |
| `dry_run(ctx)` | 导出对照 |
| `apply(ctx)` | 事务内 backup + UPDATE |
| `verify(ctx)` | 验收 |
| `rollback(ctx)` | 从备份恢复 |

类属性：

- `repair_name` — 与目录名一致
- `expected_rows` — Apply 行数断言（可选）
- `legacy_backup_table` — 历史非标准备份表名（仅参考案例）

### `RepairContext`（`base.py`）

| 成员 | 说明 |
|------|------|
| `conn` | SQLAlchemy Connection |
| `output_dir` | Dry-run 产物目录 |
| `backup_table` | `_ops_backup_<repair_name>` |
| `transaction()` | 上下文管理器，失败 ROLLBACK |
| `assert_rowcount(actual, expected)` | 行数断言 |
| `log(status, ...)` | 写入 `repair_log` |

### 审计（`audit.py`）

- `backup_table_name(repair_name)` → `_ops_backup_<repair_name>`
- `write_repair_log(...)` — 统一 `repair_log` 表
- DDL 与 `db/ops/schema/repair_log.sql` 一致

## 新建 Repair

```bash
cp -r db/ops/templates/* db/ops/fixes/my_repair_name/
# 从 repair_python_template.py 生成 repair.py，继承 RepairJob
docker compose exec -T backend python3 /data/repo/db/ops/fixes/my_repair_name/repair.py check
```

## 参考实现

[`db/ops/fixes/product3_repay_0612_custody/repair.py`](../../../db/ops/fixes/product3_repay_0612_custody/repair.py) — 首个完整案例（含 `legacy_backup_table` 兼容已执行备份）。

## CLI

```bash
python3 db/ops/fixes/<repair_name>/repair.py {check|dry-run|apply|verify|rollback}
```

或使用 `run_repair_cli(YourRepairJob)` 作为 `main()`。

# db/ops/fixes — 生产数据修复包

每个 Repair 使用**独立子目录** `db/ops/fixes/<repair_name>/`。

## 规范

- [`docs/engineering/production_data_repair_standard.md`](../../docs/engineering/production_data_repair_standard.md)
- 模板：[`../templates/`](../templates/)
- 审计 DDL：[`../schema/repair_log.sql`](../schema/repair_log.sql)
- Framework：[`../../scripts/ops/framework/`](../../scripts/ops/framework/)
- CI 检查：`python3 scripts/checks/check_repair_package.py`

## 已归档 Repair

| repair_name | 状态 | 目录 |
|-------------|------|------|
| `product3_repay_0612_custody` | 已验收（首个参考案例） | [`product3_repay_0612_custody/`](./product3_repay_0612_custody/) |

## 历史根级 SQL

`fixes/*.sql`（无子目录）为规范建立前的脚本，**新 Repair 不得再添加至此层级**。

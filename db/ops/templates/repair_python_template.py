#!/usr/bin/env python3
"""{{REPAIR_TITLE}} — Production Data Repair Job.

继承 RepairJob 标准生命周期：check → dry-run → apply → verify → rollback
规范：docs/engineering/production_data_repair_standard.md
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根目录 → 可导入 scripts.ops.framework
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.framework.base import RepairJob, RepairContext
from scripts.ops.framework.cli import run_repair_cli


class {{REPAIR_CLASS_NAME}}(RepairJob):
    repair_name = "{{REPAIR_NAME}}"
    expected_rows = {{EXPECTED_ROWS}}  # type: ignore[name-defined]

    def check(self, ctx: RepairContext) -> int:
        """只读检查 + 基线指标。"""
        # TODO: 实现检查逻辑
        print(f"check OK for {self.repair_name}")
        return 0

    def dry_run(self, ctx: RepairContext) -> int:
        """导出修正前后对照，不写库。"""
        # TODO: 查询并导出 CSV/JSON 到 ctx.output_dir
        print(f"dry_run OK for {self.repair_name}")
        return 0

    def apply(self, ctx: RepairContext) -> int:
        """事务内 backup + UPDATE + 行数断言 + repair_log。"""
        # TODO: 使用 ctx.transaction() 与 ctx.assert_rowcount()
        print(f"apply OK for {self.repair_name}")
        return 0

    def verify(self, ctx: RepairContext) -> int:
        """修正后验收。"""
        # TODO: 验收查询
        print(f"verify OK for {self.repair_name}")
        return 0

    def rollback(self, ctx: RepairContext) -> int:
        """从 _ops_backup_<repair_name> 恢复。"""
        # TODO: 从 ctx.backup_table 恢复
        print(f"rollback OK for {self.repair_name}")
        return 0


def main() -> int:
    return run_repair_cli({{REPAIR_CLASS_NAME}}())


if __name__ == "__main__":
    raise SystemExit(main())

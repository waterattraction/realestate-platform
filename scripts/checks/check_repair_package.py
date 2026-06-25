#!/usr/bin/env python3
"""校验生产数据修复包（Repair Package）目录结构 — 供 CI 使用。

规范：docs/engineering/production_data_repair_standard.md

用法：
  python3 scripts/checks/check_repair_package.py
  python3 scripts/checks/check_repair_package.py --repair product3_repay_0612_custody
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXES_ROOT = REPO_ROOT / "db" / "ops" / "fixes"

REQUIRED_FILES = ("README.md", "ACCEPTANCE.md", "repair.py", "check.sql")
ROLLBACK_ONE_OF = ("rollback.sql",)  # 或 repair.py 内 rollback 方法

REPAIR_PY_LIFECYCLE = ("def check", "def dry_run", "def apply", "def verify", "def rollback")
REPAIR_PY_INHERIT = "RepairJob"

# 参考案例：防复发测试在仓库 tests/ 下，ACCEPTANCE 或 README 须引用
UNIT_TEST_HINTS = ("tests/", "test_", "unittest")


def discover_repairs() -> list[Path]:
    if not FIXES_ROOT.is_dir():
        return []
    return sorted(
        p for p in FIXES_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def check_repair_dir(repair_dir: Path) -> list[str]:
    errors: list[str] = []
    name = repair_dir.name

    for fname in REQUIRED_FILES:
        if not (repair_dir / fname).is_file():
            errors.append(f"{name}: missing required file {fname}")

    repair_py = repair_dir / "repair.py"
    if repair_py.is_file():
        content = repair_py.read_text(encoding="utf-8")
        if REPAIR_PY_INHERIT not in content:
            errors.append(f"{name}: repair.py should inherit {REPAIR_PY_INHERIT}")
        for marker in REPAIR_PY_LIFECYCLE:
            if marker not in content:
                errors.append(f"{name}: repair.py missing {marker}")

    has_rollback_sql = (repair_dir / "rollback.sql").is_file()
    has_rollback_py = repair_py.is_file() and "def rollback" in repair_py.read_text(encoding="utf-8")
    if not has_rollback_sql and not has_rollback_py:
        errors.append(f"{name}: missing rollback (rollback.sql or repair.py rollback)")

    readme = (repair_dir / "README.md").read_text(encoding="utf-8") if (repair_dir / "README.md").is_file() else ""
    acceptance = (repair_dir / "ACCEPTANCE.md").read_text(encoding="utf-8") if (repair_dir / "ACCEPTANCE.md").is_file() else ""
    combined = readme + acceptance
    if not any(h in combined for h in UNIT_TEST_HINTS):
        errors.append(
            f"{name}: README or ACCEPTANCE must reference unit tests (tests/ or test_*)"
        )

    if repair_py.is_file():
        if "dry_run" not in repair_py.read_text(encoding="utf-8"):
            errors.append(f"{name}: repair.py must implement dry_run")
        if "def verify" not in repair_py.read_text(encoding="utf-8"):
            errors.append(f"{name}: repair.py must implement verify")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", help="只检查指定 repair_name 子目录")
    args = parser.parse_args()

    if args.repair:
        targets = [FIXES_ROOT / args.repair]
        if not targets[0].is_dir():
            print(f"ERROR: repair directory not found: {targets[0]}", file=sys.stderr)
            return 1
    else:
        targets = discover_repairs()

    if not targets:
        print("WARN: no repair packages under db/ops/fixes/<name>/", file=sys.stderr)
        return 0

    all_errors: list[str] = []
    for repair_dir in targets:
        all_errors.extend(check_repair_dir(repair_dir))

    if all_errors:
        print("Repair package check FAILED:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"Repair package check OK ({len(targets)} package(s))")
    for repair_dir in targets:
        print(f"  ✓ {repair_dir.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

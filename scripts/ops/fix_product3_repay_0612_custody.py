#!/usr/bin/env python3
"""向后兼容入口 — 委托至标准 Repair 包。

规范：docs/engineering/production_data_repair_standard.md
实现：db/ops/fixes/product3_repay_0612_custody/repair.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPAIR_PY = (
    Path(__file__).resolve().parents[2]
    / "db/ops/fixes/product3_repay_0612_custody/repair.py"
)


def main() -> int:
    spec = importlib.util.spec_from_file_location("product3_repair", _REPAIR_PY)
    if spec is None or spec.loader is None:
        raise SystemExit(f"repair module not found: {_REPAIR_PY}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(mod.main())


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate docs/canonical/ consistency with identifiers and alias mappings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _health import check_canonical, print_lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 on warnings")
    args = parser.parse_args()
    report = check_canonical()
    print_lines(report.lines)
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())

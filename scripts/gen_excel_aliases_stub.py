#!/usr/bin/env python3
"""Extract COL_ALIASES from cleanse modules; check docs/excel/*.md coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _health import check_excel_aliases, print_lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Not implemented; dry-run only")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on coverage warnings")
    args = parser.parse_args()
    if args.write:
        print("WARN: --write not implemented; running dry-run only.", file=sys.stderr)
    report = check_excel_aliases()
    print_lines(report.lines)
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())

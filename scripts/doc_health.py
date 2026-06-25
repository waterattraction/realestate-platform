#!/usr/bin/env python3
"""Unified documentation health check with coverage summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _health import print_lines, print_summary, run_full_health


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on documentation coverage warnings (for CI)",
    )
    args = parser.parse_args()

    report = run_full_health(strict=args.strict)
    print_lines(report.lines)
    print_summary(report.summary)
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())

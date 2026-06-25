#!/usr/bin/env python3
"""Compare db/manifest.txt SQL columns vs docs/data_dictionary/*.md coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    data_dictionary_table_map,
    fields_in_data_dictionary,
    load_sql_tables,
    manifest_sql_paths,
    repo_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    db_dir = repo_path("db")
    manifest = db_dir / "manifest.txt"
    if not manifest.is_file():
        print("ERROR: db/manifest.txt not found", file=sys.stderr)
        return 2

    sql_paths = manifest_sql_paths(manifest)
    tables = load_sql_tables(sql_paths)
    dd_map = data_dictionary_table_map(repo_path("docs", "data_dictionary"))

    print(f"manifest SQL files: {len(sql_paths)}")
    print(f"tables in SQL: {len(tables)}")
    print(f"data_dictionary table docs: {len(dd_map)}")
    print()

    report: list[str] = []
    for table in sorted(tables):
        cols = tables[table]
        md = dd_map.get(table)
        if not md:
            report.append(f"[NO DOC] {table} ({len(cols)} columns)")
            continue
        documented = fields_in_data_dictionary(md)
        missing = [c for c in cols if c not in documented]
        if missing:
            report.append(f"[MISSING] {table}: {', '.join(missing)}")

    if report:
        print("=== schema_diff report ===")
        for line in report:
            print(line)
        print(f"\nTotal issues: {len(report)}")
        return 1

    print("OK: all manifest tables documented with full column coverage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate or check data_dictionary field stubs from db/**/*.sql (dry-run by default)."""

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
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write stub rows (not implemented; always dry-run)",
    )
    args = parser.parse_args()
    if args.write:
        print("WARN: --write not implemented; running dry-run only.", file=sys.stderr)

    db_dir = repo_path("db")
    manifest = db_dir / "manifest.txt"
    sql_paths = list(db_dir.rglob("*.sql"))
    if manifest.is_file():
        sql_paths = manifest_sql_paths(manifest)

    tables = load_sql_tables(sql_paths)
    dd_dir = repo_path("docs", "data_dictionary")
    dd_map = data_dictionary_table_map(dd_dir)

    print(f"SQL tables parsed: {len(tables)}")
    print(f"data_dictionary files: {len(dd_map)}")
    print()

    missing_files: list[str] = []
    missing_fields: list[str] = []

    for table, cols in sorted(tables.items()):
        md = dd_map.get(table)
        if not md:
            missing_files.append(table)
            continue
        documented = fields_in_data_dictionary(md)
        for col in cols:
            if col not in documented:
                missing_fields.append(f"{table}.{col} (→ {md.name})")

    if missing_files:
        print("=== Tables without data_dictionary/*.md ===")
        for t in missing_files:
            print(f"  - {t}")
        print()

    if missing_fields:
        print("=== Columns missing from data_dictionary field tables ===")
        for item in missing_fields:
            print(f"  - {item}")
        print()
        print(f"Total missing field rows: {len(missing_fields)}")
    else:
        print("All manifest SQL columns appear documented (for mapped tables).")

    if missing_files:
        print(f"\nStub suggestion: create docs/data_dictionary/<module>.md for {len(missing_files)} table(s)")
        return 1
    return 1 if missing_fields else 0


if __name__ == "__main__":
    raise SystemExit(main())

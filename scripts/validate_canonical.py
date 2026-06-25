#!/usr/bin/env python3
"""Validate docs/canonical/ consistency with identifiers and internal cross-refs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    parse_alias_dictionary,
    parse_field_dictionary,
    parse_identifier_table,
    repo_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    field_dict = repo_path("docs", "canonical", "field_dictionary.md")
    alias_dict = repo_path("docs", "canonical", "alias_dictionary.md")
    identifiers = repo_path("docs", "standards", "identifiers.md")

    canonical_fields = parse_field_dictionary(field_dict)
    identifier_fields = parse_identifier_table(identifiers)
    aliases = parse_alias_dictionary(alias_dict)

    print(f"field_dictionary fields: {len(canonical_fields)}")
    print(f"identifiers.md key fields: {len(identifier_fields)}")
    print(f"alias_dictionary rows: {len(aliases)}")
    print()

    errors: list[str] = []

    missing_in_field_dict = identifier_fields - canonical_fields
    if missing_in_field_dict:
        print("=== identifiers.md fields missing from field_dictionary.md ===")
        for f in sorted(missing_in_field_dict):
            print(f"  - {f}")
            errors.append(f"missing canonical field: {f}")
        print()

    orphan_aliases: list[str] = []
    for alias, field in aliases:
        if field not in canonical_fields:
            orphan_aliases.append(f"「{alias}」→ `{field}`")
    if orphan_aliases:
        print("=== alias_dictionary → unknown canonical field ===")
        for item in orphan_aliases:
            print(f"  - {item}")
            errors.append(item)
        print()

    if errors:
        print(f"FAILED: {len(errors)} issue(s)")
        return 1

    print("OK: identifiers covered; all aliases map to canonical fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

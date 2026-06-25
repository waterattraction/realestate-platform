#!/usr/bin/env python3
"""Check glossary.md canonical fields appear in field_dictionary or identifiers."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import parse_field_dictionary, parse_identifier_table, read_text, repo_path


def glossary_canonical_fields(glossary_path) -> set[str]:
    fields: set[str] = set()
    for line in read_text(glossary_path).splitlines():
        m = re.search(r"`([a-z][a-z0-9_]*)`", line)
        if m:
            fields.add(m.group(1))
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    glossary = repo_path("docs", "glossary.md")
    field_dict = parse_field_dictionary(repo_path("docs", "canonical", "field_dictionary.md"))
    identifiers = parse_identifier_table(repo_path("docs", "standards", "identifiers.md"))
    covered = field_dict | identifiers

    terms = glossary_canonical_fields(glossary)
    print(f"glossary backtick fields: {len(terms)}")
    print(f"covered by field_dictionary ∪ identifiers: {len(terms & covered)}")
    print()

    missing = sorted(terms - covered)
    if missing:
        print("=== glossary fields not in field_dictionary or identifiers ===")
        for f in missing:
            print(f"  - {f}")
        print(f"\nFAILED: {len(missing)} field(s)")
        return 1

    print("OK: all glossary canonical fields documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

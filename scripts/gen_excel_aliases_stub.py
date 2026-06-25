#!/usr/bin/env python3
"""Extract COL_ALIASES from cleanse modules; check docs/excel/*.md coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import extract_col_aliases, read_text, repo_path


CLEANSE_FILES = (
    ("issuance", repo_path("backend", "app", "issuance_cleanse.py")),
    ("ingestion", repo_path("backend", "app", "ingestion_cleanse.py")),
)

EXCEL_DOCS = {
    "issuance": repo_path("docs", "excel", "issuance.md"),
    "monitor": repo_path("docs", "excel", "monitor.md"),
    "repayment": repo_path("docs", "excel", "repayment.md"),
    "overdue": repo_path("docs", "excel", "overdue.md"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Not implemented; dry-run only")
    args = parser.parse_args()
    if args.write:
        print("WARN: --write not implemented; running dry-run only.", file=sys.stderr)

    all_aliases: dict[str, dict[str, tuple[str, ...]]] = {}
    for module, path in CLEANSE_FILES:
        aliases = extract_col_aliases(path)
        all_aliases[module] = aliases
        print(f"=== {module} COL_ALIASES ({path.relative_to(repo_path())}) ===")
        for field, names in sorted(aliases.items()):
            print(f"  {field}: {', '.join(names)}")
        print()

    print("=== Markdown stub (for alias_dictionary cross-check) ===")
    for module, aliases in all_aliases.items():
        for field, names in sorted(aliases.items()):
            for alias in names:
                print(f"| {alias} | `{field}` | {module} cleanse | TODO | auto-extracted |")
    print()

    missing_in_docs: list[str] = []
    for module, aliases in all_aliases.items():
        doc_paths = [EXCEL_DOCS["issuance"]] if module == "issuance" else [EXCEL_DOCS["monitor"]]
        combined = "\n".join(read_text(p) for p in doc_paths if p.is_file())
        for field, names in aliases.items():
            if f"`{field}`" not in combined:
                missing_in_docs.append(f"{module}.{field} (field name not in excel docs)")
            for alias in names:
                if alias not in combined:
                    missing_in_docs.append(f"{module}.{field}: alias「{alias}」not in excel docs")

    if missing_in_docs:
        print("=== Aliases / fields not found in docs/excel/*.md ===")
        for item in missing_in_docs[:50]:
            print(f"  - {item}")
        if len(missing_in_docs) > 50:
            print(f"  ... and {len(missing_in_docs) - 50} more")
        print(f"\nTotal gaps: {len(missing_in_docs)}")
        return 1

    print("All COL_ALIASES fields and aliases found in relevant excel docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

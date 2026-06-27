"""Documentation health checks — shared logic for M2.6/M2.7 scripts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from _common import (
    data_dictionary_table_map,
    extract_col_aliases,
    fields_in_data_dictionary,
    load_sql_tables,
    manifest_sql_paths,
    parse_alias_dictionary,
    parse_field_dictionary,
    parse_identifier_table,
    read_text,
    repo_path,
)


class Level(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass
class HealthLine:
    level: Level
    check: str
    message: str
    missing: list[str] = field(default_factory=list)


@dataclass
class HealthReport:
    lines: list[HealthLine] = field(default_factory=list)
    summary: dict[str, str] = field(default_factory=dict)

    def add(self, level: Level, check: str, message: str, missing: list[str] | None = None) -> None:
        self.lines.append(HealthLine(level, check, message, missing or []))

    def has_fail(self) -> bool:
        return any(line.level == Level.FAIL for line in self.lines)

    def has_warning(self) -> bool:
        return any(line.level == Level.WARNING for line in self.lines)

    def exit_code(self, *, strict: bool = False) -> int:
        if self.has_fail():
            return 1
        if strict and self.has_warning():
            return 1
        return 0


def print_lines(lines: list[HealthLine]) -> None:
    for line in lines:
        print(f"{line.level.value:7} {line.check:24} {line.message}")
        for item in line.missing:
            print(f"         - {item}")


def print_summary(summary: dict[str, str]) -> None:
    print()
    print("Documentation Health Summary")
    print("-" * 40)
    for key, value in summary.items():
        print(f"{key:24} {value}")


def _manifest_tables() -> tuple[list[Path], dict[str, list[str]]]:
    manifest = repo_path("db", "manifest.txt")
    if not manifest.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest}")
    sql_paths = manifest_sql_paths(manifest)
    missing_files = [p for p in sql_paths if not p.is_file()]
    if missing_files:
        raise FileNotFoundError(
            "manifest SQL path(s) missing: " + ", ".join(str(p) for p in missing_files)
        )
    tables = load_sql_tables(sql_paths)
    if not tables:
        raise RuntimeError("SQL parse produced zero tables — check db/**/*.sql")
    return sql_paths, tables


def check_canonical() -> HealthReport:
    report = HealthReport()
    field_dict_path = repo_path("docs", "canonical", "field_dictionary.md")
    alias_dict_path = repo_path("docs", "canonical", "alias_dictionary.md")
    identifiers_path = repo_path("docs", "standards", "identifiers.md")

    if not field_dict_path.is_file():
        report.add(Level.FAIL, "Canonical Coverage", "field_dictionary.md missing")
        return report

    canonical_fields = parse_field_dictionary(field_dict_path)
    identifier_fields = parse_identifier_table(identifiers_path)
    aliases = parse_alias_dictionary(alias_dict_path)

    missing_ids = sorted(identifier_fields - canonical_fields)
    if missing_ids:
        report.add(
            Level.FAIL,
            "Canonical Coverage",
            f"{len(identifier_fields) - len(missing_ids)}/{len(identifier_fields)} identifier fields in field_dictionary",
            missing_ids,
        )
    else:
        report.add(
            Level.PASS,
            "Canonical Coverage",
            f"{len(canonical_fields)} canonical fields; {len(identifier_fields)}/{len(identifier_fields)} identifier fields covered",
        )

    orphan = [f"「{a}」→ `{f}`" for a, f in aliases if f not in canonical_fields]
    if orphan:
        report.add(
            Level.FAIL,
            "Alias Mapping",
            f"{len(aliases) - len(orphan)}/{len(aliases)} aliases mapped",
            orphan,
        )
    else:
        report.add(
            Level.PASS,
            "Alias Mapping",
            f"{len(aliases)}/{len(aliases)} aliases mapped to canonical fields",
        )

    report.summary["Canonical Fields"] = f"{len(canonical_fields)}/{len(canonical_fields)} 100%"
    report.summary["Alias Mapping"] = (
        f"{len(aliases) - len(orphan)}/{len(aliases)} "
        f"{100 if not orphan else int((len(aliases) - len(orphan)) / len(aliases) * 100)}%"
    )
    return report


def check_glossary() -> HealthReport:
    report = HealthReport()
    import re

    glossary_path = repo_path("docs", "glossary.md")
    field_dict = parse_field_dictionary(repo_path("docs", "canonical", "field_dictionary.md"))
    identifiers = parse_identifier_table(repo_path("docs", "standards", "identifiers.md"))
    covered = field_dict | identifiers

    terms: set[str] = set()
    for line in read_text(glossary_path).splitlines():
        m = re.search(r"`([a-z][a-z0-9_]*)`", line)
        if m:
            terms.add(m.group(1))

    missing = sorted(terms - covered)
    if missing:
        report.add(
            Level.FAIL,
            "Glossary",
            f"{len(terms) - len(missing)}/{len(terms)} terms covered",
            missing,
        )
    else:
        report.add(Level.PASS, "Glossary", f"{len(terms)}/{len(terms)} terms covered")

    report.summary["Glossary Terms"] = (
        f"{len(terms) - len(missing)}/{len(terms)} "
        f"{100 if not missing else int((len(terms) - len(missing)) / len(terms) * 100)}%"
    )
    return report


def check_data_dictionary() -> HealthReport:
    report = HealthReport()
    try:
        _, tables = _manifest_tables()
    except (FileNotFoundError, RuntimeError) as exc:
        report.add(Level.FAIL, "Data Dictionary", str(exc))
        return report

    dd_dir = repo_path("docs", "data_dictionary")
    dd_map = data_dictionary_table_map(dd_dir)
    missing_tables: list[str] = []
    missing_cols: list[str] = []

    for table, cols in sorted(tables.items()):
        md = dd_map.get(table)
        if not md:
            missing_tables.append(f"{table} ({len(cols)} columns)")
            continue
        documented = fields_in_data_dictionary(md)
        for col in cols:
            if col not in documented:
                missing_cols.append(f"{table}.{col}")

    documented_count = len(tables) - len(missing_tables)
    total = len(tables)
    pct = int(documented_count / total * 100) if total else 100

    issues = missing_tables + missing_cols
    if issues:
        report.add(
            Level.WARNING,
            "Data Dictionary",
            f"{documented_count}/{total} tables documented, {len(missing_tables)} missing, {len(missing_cols)} column gaps",
            issues,
        )
    else:
        report.add(
            Level.PASS,
            "Data Dictionary",
            f"{total}/{total} tables documented with full column coverage",
        )

    report.summary["Data Dictionary Tables"] = f"{documented_count}/{total} {pct}%"
    return report


def check_excel_aliases() -> HealthReport:
    report = HealthReport()
    issuance_doc = repo_path("docs", "excel", "issuance.md")
    monitor_doc = repo_path("docs", "excel", "monitor.md")

    if not issuance_doc.is_file():
        report.add(Level.FAIL, "Excel Alias Coverage", "docs/excel/issuance.md missing")
        return report

    issuance_text = read_text(issuance_doc)
    issuance_aliases = extract_col_aliases(repo_path("backend", "app", "issuance_cleanse.py"))
    assetinfo_aliases = extract_col_aliases(repo_path("backend", "app", "assetinfo_cleanse.py"))

    gaps: list[str] = []
    total_checks = 0
    passed = 0

    for field, names in issuance_aliases.items():
        total_checks += 1
        if f"`{field}`" not in issuance_text:
            gaps.append(f"issuance.{field}: canonical field not in issuance.md")
        else:
            passed += 1
        for alias in names:
            total_checks += 1
            if alias not in issuance_text:
                gaps.append(f"issuance.{field}: alias「{alias}」not in issuance.md")
            else:
                passed += 1

    if monitor_doc.is_file():
        monitor_text = read_text(monitor_doc)
        for field, names in assetinfo_aliases.items():
            total_checks += 1
            if f"`{field}`" not in monitor_text:
                gaps.append(f"assetinfo.{field}: field not in monitor.md")
            else:
                passed += 1
            for alias in names:
                total_checks += 1
                if alias not in monitor_text:
                    gaps.append(f"assetinfo.{field}: alias「{alias}」not in monitor.md")
                else:
                    passed += 1

    pct = int(passed / total_checks * 100) if total_checks else 100
    if gaps:
        report.add(
            Level.WARNING,
            "Excel Alias Coverage",
            f"{passed}/{total_checks} checks passed ({pct}%)",
            gaps,
        )
    else:
        report.add(
            Level.PASS,
            "Excel Alias Coverage",
            f"{passed}/{total_checks} checks passed (100%)",
        )

    report.summary["Excel Alias Coverage"] = f"{pct}%"
    return report


def run_full_health(*, strict: bool = False) -> HealthReport:
    combined = HealthReport()
    for part in (check_canonical(), check_glossary(), check_data_dictionary(), check_excel_aliases()):
        combined.lines.extend(part.lines)
        combined.summary.update(part.summary)
    return combined

"""Shared helpers for documentation scripts (read-only by default)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_create_tables(sql_text: str) -> dict[str, list[str]]:
    """Return {table_name: [column_names]} from CREATE TABLE statements."""
    tables: dict[str, list[str]] = {}
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql_text):
        table = match.group(1).lower()
        start = match.end()
        paren = sql_text.find("(", start)
        if paren < 0:
            continue
        depth = 1
        i = paren + 1
        while i < len(sql_text) and depth:
            if sql_text[i] == "(":
                depth += 1
            elif sql_text[i] == ")":
                depth -= 1
            i += 1
        body = sql_text[paren + 1 : i - 1]
        cols: list[str] = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(
                ("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "--")
            ):
                continue
            col_match = re.match(r"([a-z_][a-z0-9_]*)\s+", line, re.IGNORECASE)
            if col_match:
                cols.append(col_match.group(1).lower())
        if cols:
            tables[table] = cols
    return tables


def load_sql_tables(sql_paths: list[Path]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for path in sql_paths:
        if not path.is_file():
            continue
        for table, cols in parse_create_tables(read_text(path)).items():
            merged.setdefault(table, [])
            for col in cols:
                if col not in merged[table]:
                    merged[table].append(col)
    return merged


def manifest_sql_paths(manifest_path: Path) -> list[Path]:
    paths: list[Path] = []
    db_dir = manifest_path.parent
    for line in read_text(manifest_path).splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            paths.append(db_dir / line)
    return paths


def parse_backtick_fields(md_text: str) -> set[str]:
    return set(re.findall(r"`([a-z][a-z0-9_]*)`", md_text))


def parse_field_dictionary(md_path: Path) -> set[str]:
    text = read_text(md_path)
    fields: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|", line)
        if m:
            fields.add(m.group(1))
    return fields


def parse_alias_dictionary(md_path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in read_text(md_path).splitlines():
        m = re.match(r"^\|\s*([^|`]+?)\s*\|\s*`([a-z][a-z0-9_]*)`\s*\|", line)
        if m and not m.group(1).strip().startswith("-"):
            alias = m.group(1).strip()
            if alias.lower() not in ("alias", "名称"):
                pairs.append((alias, m.group(2)))
    return pairs


def parse_identifier_table(md_path: Path) -> set[str]:
    text = read_text(md_path)
    fields: set[str] = set()
    in_table = False
    for line in text.splitlines():
        if "## 标识符总表" in line:
            in_table = True
            continue
        if in_table and line.startswith("## ") and "标识符总表" not in line:
            break
        if in_table:
            m = re.match(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|", line)
            if m:
                fields.add(m.group(1))
    return fields


def extract_col_aliases(py_path: Path) -> dict[str, tuple[str, ...]]:
    tree = ast.parse(read_text(py_path))
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "COL_ALIASES":
                    value = node.value
                    break
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "COL_ALIASES":
                value = node.value
        if value is not None:
            return ast.literal_eval(value)
    return {}


def data_dictionary_table_map(dd_dir: Path) -> dict[str, Path]:
    """Map table name -> markdown file from data_dictionary docs."""
    mapping: dict[str, Path] = {}
    for md in dd_dir.glob("*.md"):
        if md.name == "README.md":
            continue
        text = read_text(md)
        m = re.search(r"`([a-z][a-z0-9_]*)`", text)
        if m:
            mapping[m.group(1)] = md
    return mapping


def fields_in_data_dictionary(md_path: Path) -> set[str]:
    fields: set[str] = set()
    for line in read_text(md_path).splitlines():
        m = re.match(r"^\|\s*([a-z][a-z0-9_]*)\s*\|", line)
        if m and m.group(1) not in ("field", "fields"):
            fields.add(m.group(1))
    return fields

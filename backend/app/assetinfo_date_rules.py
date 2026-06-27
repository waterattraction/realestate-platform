"""信托产品 Sheet 名日期解析 — 配置化年份规则."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# month -> year；由产品名称索引
TRUST_PRODUCT_DATE_RULES: dict[str, dict[int, list[int]]] = {
    "美好生活1号": {
        2025: [9, 10, 11, 12],
        2026: [1, 2, 3, 4, 5, 6, 7, 8],
    },
    "美好生活2号": {
        2025: [9, 10, 11, 12],
        2026: [1, 2, 3, 4, 5, 6, 7, 8],
    },
    "美好生活3号": {
        2025: [9, 10, 11, 12],
        2026: [1, 2, 3, 4, 5, 6, 7, 8],
    },
    "美润1号": {
        2025: [9, 10, 11, 12],
        2026: [1, 2, 3, 4, 5, 6, 7, 8],
    },
    # 与美好生活1号共用规则（历史 seed / 旧环境兜底，暂保留）
    "滨江公寓信托一期": {
        2025: [9, 10, 11, 12],
        2026: [1, 2, 3, 4, 5, 6, 7, 8],
    },
}

_SHEET_DATE_RE = re.compile(r"(\d{4})")


@dataclass
class ParsedSheetDate:
    ok: bool
    parsed_date: date | None = None
    rule_label: str | None = None
    error: str | None = None
    sheet_name: str = ""


def _invert_rules(rules: dict[int, list[int]]) -> dict[int, int]:
    month_to_year: dict[int, int] = {}
    for year, months in rules.items():
        for month in months:
            month_to_year[month] = year
    return month_to_year


def parse_sheet_repayment_date(sheet_name: str, product_name: str) -> ParsedSheetDate:
    """从 Sheet 名如「0612已还款」「0929已还款」解析还款日期."""
    result = ParsedSheetDate(ok=False, sheet_name=sheet_name)
    rules = TRUST_PRODUCT_DATE_RULES.get(product_name)
    if not rules:
        result.error = f"未配置产品日期规则: {product_name}"
        return result

    match = _SHEET_DATE_RE.search(sheet_name)
    if not match:
        result.error = f"无法从 Sheet 名解析 MMDD: {sheet_name}"
        return result

    mmdd = match.group(1)
    if len(mmdd) != 4 or not mmdd.isdigit():
        result.error = f"Sheet 名日期格式无效: {mmdd}"
        return result

    month = int(mmdd[:2])
    day = int(mmdd[2:])
    if month < 1 or month > 12 or day < 1 or day > 31:
        result.error = f"Sheet 名日期无效: {mmdd}"
        return result

    month_to_year = _invert_rules(rules)
    year = month_to_year.get(month)
    if year is None:
        result.error = f"月份 {month} 未匹配到年份规则（产品: {product_name}）"
        return result

    try:
        parsed = date(year, month, day)
    except ValueError:
        result.error = f"无效日期: {year}-{month:02d}-{day:02d}"
        return result

    result.ok = True
    result.parsed_date = parsed
    result.rule_label = f"{product_name}规则"
    return result


def parse_monitor_snapshot_date(
    file_name: str,
    sheet_name: str,
    product_name: str,
) -> ParsedSheetDate:
    """从文件名或 Sheet 名解析监控快照日期（如 _0612）。"""
    for source in (file_name, sheet_name):
        parsed = parse_sheet_repayment_date(source, product_name)
        if parsed.ok:
            return ParsedSheetDate(
                ok=True,
                parsed_date=parsed.parsed_date,
                rule_label=f"监控快照日期·{parsed.rule_label}",
                sheet_name=sheet_name,
            )
    return ParsedSheetDate(
        ok=False,
        error=f"无法从文件名/Sheet名解析监控快照日期: {file_name}",
        sheet_name=sheet_name,
    )
